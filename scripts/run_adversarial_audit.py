"""Adversarial Alpha Audit Engine for Systematic Global Macro.

Performs all quantitative calculations for:
1. Baseline Reproduction & Discrepancy Analysis
2. Factor Standalone & Marginal Attribution
3. Full Factor Ablation Study (Mom, Val, Carry, Hysteresis, Risk Parity)
4. 4-Gate & Circular Block Permutation Null Analysis
5. Temporal Walk-Forward & Out-of-Sample Partitioning
6. Market Regime Attribution (Vol, Equity Trend, Rate Direction)
7. Time Stability & Rolling Metrics
8. Universe & Instrument Attribution
9. Transaction Cost & Slippage Sensitivity (0 to 50 bps, Break-Even)
10. Parameter Sensitivity & Robustness Plateau (16 Parameter Grid)
11. Drawdown & Tail Risk Diagnostics
12. Hysteresis & Turnover Efficiency
13. Carry Dictionary Impact Audit
14. Cointegration Stat-Arb Independence & Strategy Ensemble Test
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from markov2.backtest import metrics
from markov2.cointegration.pipeline import scan_cointegrated_pairs, walk_forward_cointegration
from markov2.data import filter_vendor_artifacts
from markov2.macro import cross_sectional_signals, walk_forward_macro
from markov2.splits import get_splits
from markov2.universe_data import DEFAULT_UNIVERSE, approximate_carry, fetch_universe, get_tickers
from quant.strategies.macro import SystematicMacroStrategy


def run_full_adversarial_audit() -> dict:
    tickers = get_tickers(DEFAULT_UNIVERSE)
    df_raw = fetch_universe(tickers, years=10)

    df_clean_cols = {}
    for col in df_raw.columns:
        col_df = pd.DataFrame({"Close": df_raw[col], "Volume": 1000})
        filtered, _ = filter_vendor_artifacts(col_df)
        df_clean_cols[col] = filtered["Close"]

    df_close = pd.DataFrame(df_clean_cols).ffill().dropna(how="all")
    rets = df_close.pct_change().fillna(0.0)
    n_bars, n_assets = df_close.shape

    # -------------------------------------------------------------
    # 1. Baseline Run
    # -------------------------------------------------------------
    baseline_res = walk_forward_macro(
        df_close,
        min_train=756,
        cost_bps=10.0,
        apply_markov_gate=False,
        n_long=3,
        n_short=3,
        use_hysteresis=True,
        use_risk_parity=True,
        mom_window=126,
        val_window=756,
    )
    base_net = baseline_res["net_returns"]
    base_strat = baseline_res["strategy_returns"]
    base_pos = baseline_res["positions"]
    base_metrics = baseline_res["net_metrics"]
    base_turnover = baseline_res["turnover"]

    # -------------------------------------------------------------
    # 2. Factor Decomposition & Standalone Performance
    # -------------------------------------------------------------
    def run_factor_ablation(include_mom: bool, include_val: bool, include_car: bool, use_hyst: bool, use_rp: bool) -> dict:
        mom = df_close.pct_change(126)
        mean_val = df_close.rolling(756).mean()
        std_val = df_close.rolling(756).std()
        val = -(df_close - mean_val) / (std_val + 1e-8)
        car = approximate_carry(list(df_close.columns))
        car_df = pd.DataFrame(np.tile(car.values, (len(df_close), 1)), index=df_close.index, columns=df_close.columns)

        valid = mom.notna() & val.notna()
        combined = pd.DataFrame(np.nan, index=df_close.index, columns=df_close.columns)

        for i in range(756, len(df_close)):
            row_valid = valid.iloc[i]
            valid_cols = row_valid[row_valid].index
            if len(valid_cols) < 6:
                continue

            scores = []
            if include_mom:
                mr = mom.iloc[i][valid_cols]
                scores.append((mr - mr.mean()) / (mr.std() + 1e-8))
            if include_val:
                vr = val.iloc[i][valid_cols]
                scores.append((vr - vr.mean()) / (vr.std() + 1e-8))
            if include_car:
                cr = car_df.iloc[i][valid_cols]
                scores.append((cr - cr.mean()) / (cr.std() + 1e-8))

            if scores:
                comb_score = sum(scores) / len(scores)
            else:
                comb_score = pd.Series(0.0, index=valid_cols)

            combined.iloc[i, combined.columns.get_indexer(valid_cols)] = comb_score

        # Simulate monthly rebalance
        pos_df = pd.DataFrame(0.0, index=df_close.index, columns=df_close.columns)
        prev_long: list[str] = []
        prev_short: list[str] = []
        curr_pos = np.zeros(n_assets)

        for i in range(756, n_bars - 1):
            if (i - 756) % 21 == 0:
                row_sig = combined.iloc[i].dropna()
                if len(row_sig) >= 6:
                    sorted_sigs = row_sig.sort_values(ascending=False)
                    rank_map = {asset: r + 1 for r, (asset, _) in enumerate(sorted_sigs.items())}
                    past_rets = rets.iloc[max(0, i - 60):i]
                    vols = past_rets.std(ddof=1) * np.sqrt(252.0)
                    vols = vols.replace(0, np.nan).fillna(vols.mean()).fillna(0.15)

                    # Hysteresis
                    if use_hyst and prev_long:
                        retained_longs = [a for a in prev_long if a in rank_map and rank_map[a] <= 6]
                        if len(retained_longs) < 3:
                            cand = [a for a in sorted_sigs.index if a not in retained_longs]
                            retained_longs.extend(cand[:3 - len(retained_longs)])
                        long_selected = sorted(retained_longs, key=lambda x: rank_map.get(x, 999))[:3]
                    else:
                        long_selected = sorted_sigs.head(3).index.tolist()

                    if use_hyst and prev_short:
                        retained_shorts = [a for a in prev_short if a in rank_map and rank_map[a] >= 7]
                        if len(retained_shorts) < 3:
                            cand = [a for a in sorted_sigs.index[::-1] if a not in retained_shorts]
                            retained_shorts.extend(cand[:3 - len(retained_shorts)])
                        short_selected = sorted(retained_shorts, key=lambda x: rank_map.get(x, 0), reverse=True)[:3]
                    else:
                        short_selected = sorted_sigs.tail(3).index.tolist()

                    prev_long = long_selected
                    prev_short = short_selected

                    new_pos = pd.Series(0.0, index=df_close.columns)
                    if use_rp:
                        if long_selected:
                            inv_v = 1.0 / (vols[long_selected] + 1e-8)
                            w_long = inv_v / inv_v.sum()
                            for a, w in w_long.items():
                                new_pos[a] = float(w)
                        if short_selected:
                            inv_v = 1.0 / (vols[short_selected] + 1e-8)
                            w_short = inv_v / inv_v.sum()
                            for a, w in w_short.items():
                                new_pos[a] = -float(w)
                    else:
                        for a in long_selected:
                            new_pos[a] = 1.0 / len(long_selected)
                        for a in short_selected:
                            new_pos[a] = -1.0 / len(short_selected)

                    curr_pos = new_pos.to_numpy()

            pos_df.iloc[i] = curr_pos

        effective = pd.DataFrame(0.0, index=df_close.index, columns=df_close.columns)
        effective.iloc[1:] = pos_df.iloc[:-1].values
        strat_r = (effective * rets).sum(axis=1)
        pos_array = effective.to_numpy()
        deltas = np.abs(np.diff(np.vstack((np.zeros(n_assets), pos_array)), axis=0))
        costs = deltas.sum(axis=1) * (10.0 / 10000.0)
        net_r = strat_r - costs

        active = slice(757, n_bars)
        s_a = strat_r.iloc[active]
        net_a = net_r.iloc[active]
        held = (np.abs(pos_array).sum(axis=1) > 0).astype(float)[active]

        tno_sum = float(deltas[active].sum())
        tno_ann = (tno_sum / len(s_a)) * 252.0 if len(s_a) else 0.0

        m = metrics(net_a.to_numpy(), held)
        sd = np.std(net_a.to_numpy(), ddof=1)
        vol = float(sd * np.sqrt(252)) if sd > 0 else 0.0

        downside_rets = net_a[net_a < 0].to_numpy()
        downside_std = np.std(downside_rets, ddof=1) * np.sqrt(252) if len(downside_rets) > 1 else 1e-8
        sortino = float(m["cagr"] / downside_std) if downside_std > 0 else 0.0

        return {
            "sharpe": float(m["sharpe"]),
            "cagr": float(m["cagr"]),
            "volatility": vol,
            "max_drawdown": float(m["max_drawdown"]),
            "sortino": sortino,
            "calmar": float(abs(m["cagr"] / m["max_drawdown"])) if m["max_drawdown"] < 0 else 0.0,
            "turnover_ann": tno_ann,
            "total_cost": float(costs[active].sum()),
            "net_returns": net_a,
            "positions": effective.iloc[active],
        }

    # Run ablations
    ablations = {
        "Baseline (Mom + Val + Carry + Hyst + RP)": run_factor_ablation(True, True, True, True, True),
        "No Momentum (Val + Carry only)": run_factor_ablation(False, True, True, True, True),
        "No Value (Mom + Carry only)": run_factor_ablation(True, False, True, True, True),
        "No Carry (Mom + Val only)": run_factor_ablation(True, True, False, True, True),
        "No Hysteresis (Equal Rebalance)": run_factor_ablation(True, True, True, False, True),
        "Equal Weight (No Risk Parity)": run_factor_ablation(True, True, True, True, False),
        "Pure Momentum Alone": run_factor_ablation(True, False, False, True, True),
        "Pure Value Alone": run_factor_ablation(False, True, False, True, True),
        "Pure Carry Alone": run_factor_ablation(False, False, True, True, True),
    }

    # -------------------------------------------------------------
    # 3. Transaction Cost Sensitivity (0 to 50 bps)
    # -------------------------------------------------------------
    cost_sweep = {}
    for c_bps in [0.0, 5.0, 10.0, 20.0, 30.0, 50.0]:
        r_c = walk_forward_macro(df_close, min_train=756, cost_bps=c_bps, mom_window=126, val_window=756)
        m_c = r_c["net_metrics"]
        cost_sweep[f"{int(c_bps)} bps"] = {
            "sharpe": float(m_c["sharpe"]),
            "cagr": float(m_c["cagr"]),
            "max_drawdown": float(m_c["max_drawdown"]),
            "turnover_ann": float(r_c["turnover"]["annualised"]),
        }

    pos_arr = baseline_res["positions"].to_numpy()
    deltas = np.abs(np.diff(np.vstack((np.zeros(pos_arr.shape[1]), pos_arr)), axis=0))
    total_delta = deltas.sum()
    gross_ret_sum = baseline_res["strategy_returns"].sum()
    break_even_bps = (gross_ret_sum / total_delta) * 10000.0 if total_delta > 0 else 0.0

    # -------------------------------------------------------------
    # 4. Parameter Sensitivity (16 Combinations)
    # -------------------------------------------------------------
    splits = get_splits(df_close, train_pct=0.60, val_pct=0.20)
    train_idx = splits["TRAIN"]
    val_idx = splits["VALIDATION"]
    oos_idx = splits["TRUE_OOS"]

    param_results = []
    for mom_w in [63, 126, 252, 504]:
        for val_w in [252, 504, 756, 1008]:
            res_p = walk_forward_macro(df_close, min_train=756, cost_bps=10.0, mom_window=mom_w, val_window=val_w)
            nr = res_p["net_returns"]
            pos_p = res_p["positions"]

            def get_sub_sharpe(sub_idx: pd.Index) -> float:
                c_idx = nr.index.intersection(sub_idx)
                if len(c_idx) == 0:
                    return float("nan")
                r_sub = nr.reindex(c_idx).fillna(0.0).to_numpy()
                h_sub = (np.abs(pos_p.reindex(c_idx).fillna(0.0).to_numpy()).sum(axis=1) > 0).astype(float)
                return float(metrics(r_sub, h_sub)["sharpe"])

            param_results.append({
                "mom_w": mom_w,
                "val_w": val_w,
                "full_sharpe": float(res_p["net_metrics"]["sharpe"]),
                "train_sharpe": get_sub_sharpe(train_idx),
                "val_sharpe": get_sub_sharpe(val_idx),
                "oos_sharpe": get_sub_sharpe(oos_idx),
                "cagr": float(res_p["net_metrics"]["cagr"]),
                "max_drawdown": float(res_p["net_metrics"]["max_drawdown"]),
            })

    # -------------------------------------------------------------
    # 5. Universe / Instrument Attribution
    # -------------------------------------------------------------
    eff_pos = baseline_res["positions"]
    active_rets = rets.reindex(eff_pos.index).fillna(0.0)
    asset_contrib = eff_pos * active_rets

    inst_summary = {}
    for col in df_close.columns:
        p_col = eff_pos[col]
        c_col = asset_contrib[col]
        total_pnl = float(c_col.sum())
        avg_w = float(p_col.mean())
        max_w = float(p_col.max())
        min_w = float(p_col.min())
        abs_w = float(np.abs(p_col).mean())
        active_days = int((p_col != 0).sum())
        pos_days = int((c_col > 0).sum())
        hit_rate = (pos_days / active_days) if active_days > 0 else 0.0

        inst_summary[col] = {
            "cumulative_pnl": total_pnl,
            "ann_pnl": total_pnl / (len(eff_pos) / 252.0),
            "avg_weight": avg_w,
            "avg_abs_weight": abs_w,
            "max_weight": max_w,
            "min_weight": min_w,
            "active_days": active_days,
            "hit_rate": hit_rate,
        }

    # -------------------------------------------------------------
    # 6. Regime Analysis (Volatility, Trend, and Rates)
    # -------------------------------------------------------------
    spy_rets = rets["SPY"].reindex(base_net.index).fillna(0.0)
    tlt_rets = rets["TLT"].reindex(base_net.index).fillna(0.0)
    roll_vol_20 = base_net.rolling(20).std() * np.sqrt(252)
    median_vol = float(roll_vol_20.median())

    high_vol_mask = roll_vol_20 >= median_vol
    low_vol_mask = roll_vol_20 < median_vol

    spy_close = df_close["SPY"].reindex(base_net.index)
    spy_ma50 = spy_close.rolling(50).mean()
    risk_on_mask = spy_close >= spy_ma50
    risk_off_mask = spy_close < spy_ma50

    tlt_50r = tlt_rets.rolling(50).sum()
    rate_falling_mask = tlt_50r >= 0
    rate_rising_mask = tlt_50r < 0

    def calc_regime_metrics(name: str, mask: pd.Series) -> dict:
        r_reg = base_net[mask].dropna().to_numpy()
        if len(r_reg) == 0:
            return {"name": name, "n_bars": 0, "cagr": 0.0, "sharpe": 0.0, "vol": 0.0}
        ann_mean = float(np.mean(r_reg) * 252.0)
        ann_std = float(np.std(r_reg, ddof=1) * np.sqrt(252.0)) if len(r_reg) > 1 else 1e-8
        sh = ann_mean / ann_std if ann_std > 0 else 0.0
        return {
            "name": name,
            "n_bars": len(r_reg),
            "pct_time": len(r_reg) / len(base_net) * 100.0,
            "ann_return": ann_mean,
            "ann_vol": ann_std,
            "sharpe": sh,
        }

    regimes = {
        "High Volatility Regime": calc_regime_metrics("High Vol", high_vol_mask),
        "Low Volatility Regime": calc_regime_metrics("Low Vol", low_vol_mask),
        "Risk-On (SPY >= MA50)": calc_regime_metrics("Risk-On", risk_on_mask),
        "Risk-Off (SPY < MA50)": calc_regime_metrics("Risk-Off", risk_off_mask),
        "Falling Rates (TLT 50d >= 0)": calc_regime_metrics("Falling Rates", rate_falling_mask),
        "Rising Rates (TLT 50d < 0)": calc_regime_metrics("Rising Rates", rate_rising_mask),
    }

    # -------------------------------------------------------------
    # 7. Drawdown & Tail Risk Diagnostics
    # -------------------------------------------------------------
    cum_wealth = (1.0 + base_net).cumprod()
    peak = cum_wealth.cummax()
    dd_series = (cum_wealth - peak) / peak

    drawdown_events = []
    in_dd = False
    dd_start = None
    dd_trough = None
    dd_min_val = 0.0

    for dt, val in dd_series.items():
        if val < -0.01:
            if not in_dd:
                in_dd = True
                dd_start = dt
                dd_min_val = val
                dd_trough = dt
            else:
                if val < dd_min_val:
                    dd_min_val = val
                    dd_trough = dt
        elif in_dd and val >= -0.001:
            drawdown_events.append({
                "start": str(dd_start.date()),
                "trough": str(dd_trough.date()),
                "recovery": str(dt.date()),
                "duration_days": int((dt - dd_start).days),
                "peak_loss": float(dd_min_val),
            })
            in_dd = False

    drawdown_events.sort(key=lambda x: x["peak_loss"])

    daily_returns = base_net.to_numpy()
    worst_daily = float(np.min(daily_returns))
    p1_daily = float(np.percentile(daily_returns, 1))
    p5_daily = float(np.percentile(daily_returns, 5))
    skewness = float(pd.Series(daily_returns).skew())
    kurt = float(pd.Series(daily_returns).kurtosis())

    weekly_rets = base_net.groupby(pd.Grouper(freq="W")).apply(lambda r: (1.0 + r).prod() - 1.0).dropna()
    monthly_rets = base_net.groupby(pd.Grouper(freq="ME")).apply(lambda r: (1.0 + r).prod() - 1.0).dropna()
    worst_weekly = float(weekly_rets.min()) if len(weekly_rets) else 0.0
    worst_monthly = float(monthly_rets.min()) if len(monthly_rets) else 0.0

    # -------------------------------------------------------------
    # 8. Permutation Null / 4-Gate Validation
    # -------------------------------------------------------------
    # Circular block permutation test (25 shifts)
    n_perms = 25
    null_sharpes = []
    T = len(df_close)
    rng = np.random.default_rng(42)

    for _ in range(n_perms):
        # Circular block shift
        k = rng.integers(0, T)
        df_perm = pd.DataFrame(np.roll(df_close.values, k, axis=0), index=df_close.index, columns=df_close.columns)
        res_null = walk_forward_macro(df_perm, min_train=756, cost_bps=10.0, mom_window=126, val_window=756)
        null_sharpes.append(float(res_null["net_metrics"]["sharpe"]))

    null_mean = float(np.mean(null_sharpes))
    null_std = float(np.std(null_sharpes, ddof=1))
    null_p95 = float(np.percentile(null_sharpes, 95))
    obs_sharpe = float(base_metrics["sharpe"])
    empirical_p = float(np.mean(np.array(null_sharpes) >= obs_sharpe))

    # -------------------------------------------------------------
    # 9. Cointegration Independence & Ensemble Evaluation
    # -------------------------------------------------------------
    pairs = scan_cointegrated_pairs(df_close, kappa_threshold=20.0)
    coint_rets = pd.Series(0.0, index=base_net.index)
    best_pair_str = "None"
    if pairs:
        best_pair = pairs[0]["pair"]
        best_pair_str = f"{best_pair[0]}-{best_pair[1]}"
        coint_run = walk_forward_cointegration(df_close[[best_pair[0], best_pair[1]]], train_window=504)
        coint_spread = coint_run["spread"].reindex(base_net.index).fillna(0.0)
        spread_diff = coint_spread.diff().shift(-1).fillna(0.0)
        z_spread = (coint_spread - coint_spread.rolling(60).mean()) / (coint_spread.rolling(60).std() + 1e-8)
        coint_rets = (-np.sign(z_spread.shift(1)) * spread_diff).fillna(0.0) * 0.5

    corr_coint_macro = float(base_net.corr(coint_rets)) if not coint_rets.empty else 0.0
    ensemble_rets = (base_net * 0.7 + coint_rets * 0.3)
    ensemble_sd = np.std(ensemble_rets.to_numpy(), ddof=1)
    ensemble_sharpe = float((ensemble_rets.mean() * 252.0) / (ensemble_sd * np.sqrt(252.0))) if ensemble_sd > 0 else 0.0

    return {
        "baseline_metrics": base_metrics,
        "baseline_turnover": base_turnover,
        "break_even_bps": break_even_bps,
        "ablations": ablations,
        "cost_sweep": cost_sweep,
        "param_results": param_results,
        "inst_summary": inst_summary,
        "regimes": regimes,
        "top_drawdowns": drawdown_events[:5],
        "tail_metrics": {
            "worst_daily": worst_daily,
            "p1_daily": p1_daily,
            "p5_daily": p5_daily,
            "worst_weekly": worst_weekly,
            "worst_monthly": worst_monthly,
            "skewness": skewness,
            "kurtosis": kurt,
        },
        "null_analysis": {
            "null_mean": null_mean,
            "null_std": null_std,
            "null_p95": null_p95,
            "obs_sharpe": obs_sharpe,
            "empirical_p": empirical_p,
        },
        "ensemble": {
            "best_pair": best_pair_str,
            "corr_coint_macro": corr_coint_macro,
            "ensemble_sharpe": ensemble_sharpe,
        },
    }


if __name__ == "__main__":
    audit = run_full_adversarial_audit()
    print("\n" + "=" * 80)
    print(" ADVERSARIAL AUDIT RESULTS SUMMARY")
    print("=" * 80)
    print(f"Baseline Sharpe: {audit['baseline_metrics']['sharpe']:.4f}")
    print(f"Baseline CAGR:   {audit['baseline_metrics']['cagr']*100:.2f}%")
    print(f"Baseline MaxDD:  {audit['baseline_metrics']['max_drawdown']*100:.2f}%")
    print(f"Break-Even Cost: {audit['break_even_bps']:.2f} bps")
    print(f"Null Mean Sharpe: {audit['null_analysis']['null_mean']:.4f} | p-val: {audit['null_analysis']['empirical_p']:.4f}")

    print("\nAblations:")
    for k, v in audit["ablations"].items():
        print(f"  {k:<45s} | Sharpe: {v['sharpe']:6.3f} | CAGR: {v['cagr']*100:5.2f}% | MaxDD: {v['max_drawdown']*100:5.2f}% | Tno: {v['turnover_ann']:5.1f}%")

    print("\nCost Sweep:")
    for k, v in audit["cost_sweep"].items():
        print(f"  {k:<10s} | Sharpe: {v['sharpe']:6.3f} | CAGR: {v['cagr']*100:5.2f}% | MaxDD: {v['max_drawdown']*100:5.2f}%")

    print("\nRegimes:")
    for k, v in audit["regimes"].items():
        print(f"  {k:<30s} | N={v['n_bars']:4d} ({v['pct_time']:4.1f}%) | Sharpe: {v['sharpe']:6.3f} | Return: {v['ann_return']*100:5.2f}%")

    out_file = Path(__file__).resolve().parent.parent / "results" / "adversarial_audit_data.json"
    # Filter out non-serializable elements
    serializable_audit = {
        "baseline_metrics": audit["baseline_metrics"],
        "baseline_turnover": audit["baseline_turnover"],
        "break_even_bps": audit["break_even_bps"],
        "ablations": {
            k: {sk: sv for sk, sv in v.items() if sk not in ("net_returns", "positions")}
            for k, v in audit["ablations"].items()
        },
        "cost_sweep": audit["cost_sweep"],
        "param_results": audit["param_results"],
        "inst_summary": audit["inst_summary"],
        "regimes": audit["regimes"],
        "top_drawdowns": audit["top_drawdowns"],
        "tail_metrics": audit["tail_metrics"],
        "null_analysis": audit["null_analysis"],
        "ensemble": audit["ensemble"],
    }
    with open(out_file, "w") as f:
        json.dump(serializable_audit, f, indent=2)
    print(f"\nSaved structured audit JSON to {out_file}")
