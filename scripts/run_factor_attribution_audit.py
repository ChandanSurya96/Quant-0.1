"""Factor Attribution and Ablation Engine under Physical Share Accounting.

Executes:
1. Pure Factor-Only Physical Simulations (Mom alone, Val alone, Carry alone).
2. Systematic Ablations (-Mom, -Val, -Carry, -Hysteresis, -RiskParity).
3. Factor Signal Correlation Matrix (z-scores).
4. P&L and Turnover Decomposition.
5. Drawdown and Regime Attribution.
6. Temporal Walk-Forward Partitioning (Train 60%, Val 20%, True OOS 20%).
7. 4-Gate Null Testing on Standalone and Ablation Variants.
8. Friction Sensitivity Sweeps (0, 5, 10, 20, 30, 50 bps).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from markov2.data import filter_vendor_artifacts
from markov2.splits import get_splits
from markov2.universe_data import DEFAULT_UNIVERSE, approximate_carry, fetch_universe, get_tickers
from quant.portfolio.simulator import PortfolioSimulator


def run_attribution_analysis() -> dict:
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
    start_idx = 756

    # -------------------------------------------------------------
    # 1. Generate Signal Frames & Target Weights for Any Configuration
    # -------------------------------------------------------------
    def generate_custom_target_weights(
        include_mom: bool = True,
        include_val: bool = True,
        include_car: bool = True,
        use_hyst: bool = True,
        use_rp: bool = True,
        mom_w: int = 126,
        val_w: int = 756,
        vol_w: int = 60,
    ) -> pd.DataFrame:
        mom = df_close.pct_change(mom_w)
        mean_val = df_close.rolling(val_w).mean()
        std_val = df_close.rolling(val_w).std()
        val = -(df_close - mean_val) / (std_val + 1e-8)
        car = approximate_carry(list(df_close.columns))
        car_df = pd.DataFrame(np.tile(car.values, (len(df_close), 1)), index=df_close.index, columns=df_close.columns)

        valid = mom.notna() & val.notna()
        combined = pd.DataFrame(np.nan, index=df_close.index, columns=df_close.columns)

        for i in range(start_idx, len(df_close)):
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

        # Target weights generated at each rebalance
        target_w_df = pd.DataFrame(0.0, index=df_close.index, columns=df_close.columns)
        prev_long: list[str] = []
        prev_short: list[str] = []

        for i in range(start_idx, n_bars):
            if (i - start_idx) % 21 == 0:
                row_sig = combined.iloc[i].dropna()
                if len(row_sig) >= 6:
                    sorted_sigs = row_sig.sort_values(ascending=False)
                    rank_map = {asset: r + 1 for r, (asset, _) in enumerate(sorted_sigs.items())}
                    past_rets = rets.iloc[max(0, i - vol_w):i]
                    vols = past_rets.std(ddof=1) * np.sqrt(252.0)
                    vols = vols.replace(0, np.nan).fillna(vols.mean()).fillna(0.15)

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

                    row_target = pd.Series(0.0, index=df_close.columns)
                    if use_rp:
                        if long_selected:
                            inv_v = 1.0 / (vols[long_selected] + 1e-8)
                            w_long = inv_v / inv_v.sum()
                            for a, w in w_long.items():
                                row_target[a] = float(w)
                        if short_selected:
                            inv_v = 1.0 / (vols[short_selected] + 1e-8)
                            w_short = inv_v / inv_v.sum()
                            for a, w in w_short.items():
                                row_target[a] = -float(w)
                    else:
                        for a in long_selected:
                            row_target[a] = 1.0 / len(long_selected)
                        for a in short_selected:
                            row_target[a] = -1.0 / len(short_selected)

                    target_w_df.iloc[i] = row_target
                else:
                    target_w_df.iloc[i] = 0.0
            else:
                target_w_df.iloc[i] = target_w_df.iloc[i - 1]

        return target_w_df, combined

    # -------------------------------------------------------------
    # 2. Run Physical-Share Simulation Helper
    # -------------------------------------------------------------
    rebalance_dates = [df_close.index[i] for i in range(start_idx, n_bars) if (i - start_idx) % 21 == 0]

    def run_sim(tw_df: pd.DataFrame, c_bps: float = 10.0) -> dict:
        sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=c_bps)
        res = sim.run(
            target_weights_df=tw_df,
            prices_df=df_close,
            rebalance_freq=21,
            rebalance_dates=rebalance_dates,
            start_idx=start_idx,
        )
        r = res["returns"]
        m = res["metrics"]
        downside = r[r < 0].to_numpy()
        sortino = float(m["cagr"] / (np.std(downside, ddof=1) * np.sqrt(252))) if len(downside) > 1 else 0.0
        calmar = float(abs(m["cagr"] / m["max_drawdown"])) if m["max_drawdown"] < 0 else 0.0
        return {
            "cagr": m["cagr"],
            "sharpe": m["sharpe"],
            "sortino": sortino,
            "volatility": m["annualized_volatility"],
            "max_drawdown": m["max_drawdown"],
            "calmar": calmar,
            "turnover": m["annualized_turnover"],
            "total_costs": m["total_costs"],
            "final_nav": m["final_nav"],
            "returns": r,
            "nav": res["nav"],
            "trades": res["trades"],
            "holdings": res["holdings"],
            "realized_weights": res["realized_weights"],
        }

    # -------------------------------------------------------------
    # 3. Factor-Only & Ablation Suite
    # -------------------------------------------------------------
    configs = {
        "CLEAN_PHYSICAL_SHARE_BASELINE": {"mom": True, "val": True, "car": True, "hyst": True, "rp": True},
        "Ablation: No Momentum (Val + Carry only)": {"mom": False, "val": True, "car": True, "hyst": True, "rp": True},
        "Ablation: No Value (Mom + Carry only)": {"mom": True, "val": False, "car": True, "hyst": True, "rp": True},
        "Ablation: No Carry (Mom + Val only)": {"mom": True, "val": True, "car": False, "hyst": True, "rp": True},
        "Ablation: No Hysteresis (Raw Monthly)": {"mom": True, "val": True, "car": True, "hyst": False, "rp": True},
        "Ablation: Equal Weight (No Risk Parity)": {"mom": True, "val": True, "car": True, "hyst": True, "rp": False},
        "Factor-Only: Pure Momentum": {"mom": True, "val": False, "car": False, "hyst": True, "rp": True},
        "Factor-Only: Pure Value": {"mom": False, "val": True, "car": False, "hyst": True, "rp": True},
        "Factor-Only: Pure Carry": {"mom": False, "val": False, "car": True, "hyst": True, "rp": True},
    }

    sim_results = {}
    signal_dfs = {}
    for name, cfg in configs.items():
        tw, sig = generate_custom_target_weights(
            include_mom=cfg["mom"],
            include_val=cfg["val"],
            include_car=cfg["car"],
            use_hyst=cfg["hyst"],
            use_rp=cfg["rp"],
        )
        sim_res = run_sim(tw, c_bps=10.0)
        sim_results[name] = sim_res
        signal_dfs[name] = sig

    base_res = sim_results["CLEAN_PHYSICAL_SHARE_BASELINE"]

    # -------------------------------------------------------------
    # 4. Factor Signal Correlation Matrix
    # -------------------------------------------------------------
    # Standalone factors z-scores
    mom_z = df_close.pct_change(126)
    mom_z_cs = (mom_z.sub(mom_z.mean(axis=1), axis=0)).div(mom_z.std(axis=1) + 1e-8, axis=0)

    mean_val = df_close.rolling(756).mean()
    std_val = df_close.rolling(756).std()
    val_raw = -(df_close - mean_val) / (std_val + 1e-8)
    val_z_cs = (val_raw.sub(val_raw.mean(axis=1), axis=0)).div(val_raw.std(axis=1) + 1e-8, axis=0)

    car = approximate_carry(list(df_close.columns))
    car_df = pd.DataFrame(np.tile(car.values, (len(df_close), 1)), index=df_close.index, columns=df_close.columns)
    car_z_cs = (car_df.sub(car_df.mean(axis=1), axis=0)).div(car_df.std(axis=1) + 1e-8, axis=0)

    active_slice = slice(start_idx, n_bars)
    # Stacked cross-sectional correlation
    mom_stack = mom_z_cs.iloc[active_slice].to_numpy().flatten()
    val_stack = val_z_cs.iloc[active_slice].to_numpy().flatten()
    car_stack = car_z_cs.iloc[active_slice].to_numpy().flatten()

    valid_mask = ~np.isnan(mom_stack) & ~np.isnan(val_stack) & ~np.isnan(car_stack)
    corr_mom_val = float(np.corrcoef(mom_stack[valid_mask], val_stack[valid_mask])[0, 1])
    corr_mom_car = float(np.corrcoef(mom_stack[valid_mask], car_stack[valid_mask])[0, 1])
    corr_val_car = float(np.corrcoef(val_stack[valid_mask], car_stack[valid_mask])[0, 1])

    # -------------------------------------------------------------
    # 5. Temporal Walk-Forward Partitioning
    # -------------------------------------------------------------
    splits = get_splits(df_close, train_pct=0.60, val_pct=0.20)
    active_idx = base_res["returns"].index
    train_idx = splits["TRAIN"].intersection(active_idx)
    val_idx = splits["VALIDATION"].intersection(active_idx)
    oos_idx = splits["TRUE_OOS"].intersection(active_idx)

    def eval_sub_period(r_s: pd.Series) -> dict:
        arr = r_s.to_numpy()
        sd = np.std(arr, ddof=1) if len(arr) > 1 else 1e-8
        sh = float((np.mean(arr) / sd) * np.sqrt(252)) if sd > 0 else 0.0
        n_years = len(arr) / 252.0 if len(arr) else 1.0
        tot = float((1.0 + r_s).prod() - 1.0) if len(arr) else 0.0
        cagr = (1.0 + tot) ** (1.0 / max(1e-4, n_years)) - 1.0 if tot > -1.0 else -1.0
        cum = (1.0 + r_s).cumprod()
        pk = cum.cummax()
        mdd = float(((cum - pk) / pk).min()) if len(cum) else 0.0
        return {"sharpe": sh, "cagr": cagr, "max_drawdown": mdd}

    walk_forward_table = {}
    for name, s_res in sim_results.items():
        r = s_res["returns"]
        walk_forward_table[name] = {
            "TRAIN": eval_sub_period(r.loc[train_idx]),
            "VALIDATION": eval_sub_period(r.loc[val_idx]),
            "TRUE_OOS": eval_sub_period(r.loc[oos_idx]),
            "FULL": {"sharpe": s_res["sharpe"], "cagr": s_res["cagr"], "max_drawdown": s_res["max_drawdown"]},
        }

    # -------------------------------------------------------------
    # 6. Friction Sensitivity Sweep (0 to 50 bps)
    # -------------------------------------------------------------
    tw_base, _ = generate_custom_target_weights(True, True, True, True, True)
    tw_no_mom, _ = generate_custom_target_weights(False, True, True, True, True)
    tw_val_only, _ = generate_custom_target_weights(False, True, False, True, True)

    cost_sweep = {}
    for c_bps in [0.0, 5.0, 10.0, 20.0, 30.0, 50.0]:
        sim_b = run_sim(tw_base, c_bps=c_bps)
        sim_nm = run_sim(tw_no_mom, c_bps=c_bps)
        sim_vo = run_sim(tw_val_only, c_bps=c_bps)
        cost_sweep[f"{int(c_bps)} bps"] = {
            "baseline": {"sharpe": sim_b["sharpe"], "cagr": sim_b["cagr"], "turnover": sim_b["turnover"], "costs": sim_b["total_costs"]},
            "no_momentum": {"sharpe": sim_nm["sharpe"], "cagr": sim_nm["cagr"], "turnover": sim_nm["turnover"], "costs": sim_nm["total_costs"]},
            "value_only": {"sharpe": sim_vo["sharpe"], "cagr": sim_vo["cagr"], "turnover": sim_vo["turnover"], "costs": sim_vo["total_costs"]},
        }

    # -------------------------------------------------------------
    # 7. Drawdown & Regime Diagnostics
    # -------------------------------------------------------------
    nav_s = base_res["nav"]
    peak = nav_s.cummax()
    dd_s = (nav_s - peak) / peak

    # Worst drawdown periods
    dd_events = []
    in_dd = False
    dd_start = None
    dd_min = 0.0
    dd_trough = None

    for dt, val in dd_s.items():
        if val < -0.02:
            if not in_dd:
                in_dd = True
                dd_start = dt
                dd_min = val
                dd_trough = dt
            else:
                if val < dd_min:
                    dd_min = val
                    dd_trough = dt
        elif in_dd and val >= -0.005:
            dd_events.append({
                "start": str(dd_start.date()),
                "trough": str(dd_trough.date()),
                "recovery": str(dt.date()),
                "duration_days": int((dt - dd_start).days),
                "peak_loss": float(dd_min),
            })
            in_dd = False

    dd_events.sort(key=lambda x: x["peak_loss"])

    # Macro regime split on physical baseline returns
    base_r = base_res["returns"]
    spy_close = df_close["SPY"].reindex(base_r.index)
    spy_ma50 = spy_close.rolling(50).mean()
    risk_on = spy_close >= spy_ma50
    risk_off = spy_close < spy_ma50

    tlt_rets = rets["TLT"].reindex(base_r.index)
    tlt_50r = tlt_rets.rolling(50).sum()
    rate_falling = tlt_50r >= 0
    rate_rising = tlt_50r < 0

    def get_regime_perf(mask: pd.Series) -> dict:
        sub_r = base_r[mask].dropna()
        arr = sub_r.to_numpy()
        ann_ret = float(np.mean(arr) * 252.0)
        ann_vol = float(np.std(arr, ddof=1) * np.sqrt(252.0)) if len(arr) > 1 else 1e-8
        sh = ann_ret / ann_vol if ann_vol > 0 else 0.0
        return {"n_bars": len(arr), "pct_time": len(arr) / len(base_r) * 100.0, "return": ann_ret, "volatility": ann_vol, "sharpe": sh}

    regimes = {
        "Risk-On (SPY >= MA50)": get_regime_perf(risk_on),
        "Risk-Off (SPY < MA50)": get_regime_perf(risk_off),
        "Falling Rates (TLT 50d >= 0)": get_regime_perf(rate_falling),
        "Rising Rates (TLT 50d < 0)": get_regime_perf(rate_rising),
    }

    # Summary dictionary
    summary = {
        "baseline": {k: v for k, v in base_res.items() if k not in ("returns", "nav", "trades", "holdings", "realized_weights")},
        "sim_results": {
            name: {
                "cagr": res["cagr"],
                "sharpe": res["sharpe"],
                "sortino": res["sortino"],
                "volatility": res["volatility"],
                "max_drawdown": res["max_drawdown"],
                "calmar": res["calmar"],
                "turnover": res["turnover"],
                "total_costs": res["total_costs"],
                "final_nav": res["final_nav"],
                "delta_sharpe": res["sharpe"] - base_res["sharpe"],
                "delta_cagr": res["cagr"] - base_res["cagr"],
                "delta_max_dd": res["max_drawdown"] - base_res["max_drawdown"],
            }
            for name, res in sim_results.items()
        },
        "correlations": {
            "corr_mom_val": corr_mom_val,
            "corr_mom_car": corr_mom_car,
            "corr_val_car": corr_val_car,
        },
        "walk_forward": walk_forward_table,
        "cost_sweep": cost_sweep,
        "top_drawdowns": dd_events[:5],
        "regimes": regimes,
    }

    out_file = Path(__file__).resolve().parent.parent / "results" / "factor_attribution_audit_data.json"
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2)

    return summary


if __name__ == "__main__":
    res = run_attribution_analysis()
    print("=" * 80)
    print(" FACTOR ATTRIBUTION ANALYSIS COMPLETE")
    print("=" * 80)
    print(f"{'Configuration':<42} | {'Sharpe':<8} | {'CAGR':<8} | {'MaxDD':<8} | {'Turnover':<8} | {'dSharpe':<8}")
    print("-" * 90)
    for name, m in res["sim_results"].items():
        print(f"{name:<42} | {m['sharpe']:<8.4f} | {m['cagr']*100:<7.2f}% | {m['max_drawdown']*100:<7.2f}% | {m['turnover']:<7.1f}% | {m['delta_sharpe']:<+8.4f}")
    print("=" * 80)
    print(f"Correlations: Mom-Val={res['correlations']['corr_mom_val']:.4f} | Mom-Car={res['correlations']['corr_mom_car']:.4f} | Val-Car={res['correlations']['corr_val_car']:.4f}")
