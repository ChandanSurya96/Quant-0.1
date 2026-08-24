"""Deep Adversarial Alpha Audit, Parameter Stability, Universe LOO, Regimes & Candidate Validations."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from markov2.data import filter_vendor_artifacts
from markov2.splits import get_splits
from markov2.universe_data import DEFAULT_UNIVERSE, fetch_universe, get_tickers
from quant.portfolio.simulator import PortfolioSimulator


def run_strategy_simulation(
    df_close: pd.DataFrame,
    mom_lookback: int = 126,
    vol_lookback: int = 60,
    rebalance_freq: int = 21,
    cost_bps: float = 10.0,
    borrow_bps: float = 25.0,
    strategy_mode: str = "CAND_001",  # "CAND_001", "CAND_003_MULTI_HORIZON", "CAND_004_DEMARCATED", "CAND_005_VOL_GATED"
    asset_class_map: dict[str, str] | None = None,
) -> dict:
    rets = df_close.pct_change().fillna(0.0)
    n_bars, n_assets = df_close.shape
    start_idx = 756
    rebalance_dates = [df_close.index[i] for i in range(start_idx, n_bars) if (i - start_idx) % rebalance_freq == 0]

    # Precalculate signals
    if strategy_mode == "CAND_003_MULTI_HORIZON":
        m21 = df_close.pct_change(21)
        m63 = df_close.pct_change(63)
        m126 = df_close.pct_change(126)
    else:
        mom = df_close.pct_change(mom_lookback)

    target_w_df = pd.DataFrame(0.0, index=df_close.index, columns=df_close.columns)
    prev_long, prev_short = [], []

    for i in range(start_idx, n_bars):
        if (i - start_idx) % rebalance_freq == 0:
            past_rets = rets.iloc[max(0, i - vol_lookback):i]
            vols = past_rets.std(ddof=1) * np.sqrt(252.0)
            vols = vols.replace(0, np.nan).fillna(vols.mean()).fillna(0.15)

            if strategy_mode == "CAND_003_MULTI_HORIZON":
                # Multi-horizon trend blend: 40% 126d + 35% 63d + 25% 21d (vol-standardized)
                z21 = (m21.iloc[i] - m21.iloc[i].mean()) / (m21.iloc[i].std() + 1e-8)
                z63 = (m63.iloc[i] - m63.iloc[i].mean()) / (m63.iloc[i].std() + 1e-8)
                z126 = (m126.iloc[i] - m126.iloc[i].mean()) / (m126.iloc[i].std() + 1e-8)
                sig = 0.40 * z126 + 0.35 * z63 + 0.25 * z21
            else:
                mr = mom.iloc[i].dropna()
                sig = (mr - mr.mean()) / (mr.std() + 1e-8) if len(mr) >= 4 else pd.Series(0.0, index=df_close.columns)

            sorted_sigs = sig.sort_values(ascending=False)
            rank_map = {asset: r + 1 for r, (asset, _) in enumerate(sorted_sigs.items())}

            if strategy_mode == "CAND_004_DEMARCATED" and asset_class_map:
                # 1 Long / 1 Short per macro asset class
                long_selected, short_selected = [], []
                for ac in set(asset_class_map.values()):
                    ac_tickers = [t for t, c in asset_class_map.items() if c == ac and t in sig.index]
                    if len(ac_tickers) >= 2:
                        ac_sorted = sig[ac_tickers].sort_values(ascending=False)
                        long_selected.append(ac_sorted.index[0])
                        short_selected.append(ac_sorted.index[-1])
            else:
                # Standard CAND-001 rank hysteresis
                retained_longs = [a for a in prev_long if a in rank_map and rank_map[a] <= 6]
                if len(retained_longs) < 3:
                    cand = [a for a in sorted_sigs.index if a not in retained_longs]
                    retained_longs.extend(cand[:3 - len(retained_longs)])
                long_selected = sorted(retained_longs, key=lambda x: rank_map.get(x, 999))[:3]

                retained_shorts = [a for a in prev_short if a in rank_map and rank_map[a] >= 7]
                if len(retained_shorts) < 3:
                    cand = [a for a in sorted_sigs.index[::-1] if a not in retained_shorts]
                    retained_shorts.extend(cand[:3 - len(retained_shorts)])
                short_selected = sorted(retained_shorts, key=lambda x: rank_map.get(x, 0), reverse=True)[:3]

            prev_long = long_selected
            prev_short = short_selected

            row_target = pd.Series(0.0, index=df_close.columns)
            if long_selected and short_selected:
                inv_v_long = 1.0 / (vols[long_selected] + 1e-8)
                w_long = inv_v_long / inv_v_long.sum()
                for a, w in w_long.items():
                    row_target[a] = float(w)

                inv_v_short = 1.0 / (vols[short_selected] + 1e-8)
                w_short = inv_v_short / inv_v_short.sum()
                for a, w in w_short.items():
                    row_target[a] = -float(w)

                if strategy_mode == "CAND_005_VOL_GATED":
                    # Dynamic deleverage: if median 60d realized vol > 18%, scale down gross leverage
                    med_vol = float(vols.median())
                    if med_vol > 0.18:
                        scale = max(0.2, 0.18 / med_vol)
                        row_target *= scale

            target_w_df.iloc[i] = row_target
        else:
            target_w_df.iloc[i] = target_w_df.iloc[i - 1]

    sim = PortfolioSimulator(
        initial_cash=100_000.0,
        cost_bps=cost_bps,
        borrow_cost_annual_bps=borrow_bps,
    )
    res = sim.run(target_w_df, df_close, rebalance_freq=rebalance_freq, rebalance_dates=rebalance_dates, start_idx=start_idx)
    out = {**res["metrics"], **res}
    out["target_weights"] = target_w_df
    downside = res["returns"][res["returns"] < 0].to_numpy()
    sd_down = np.std(downside, ddof=1) * np.sqrt(252.0) if len(downside) > 1 else 1e-8
    out["sortino"] = float(out["cagr"] / sd_down) if sd_down > 0 else 0.0
    return out


def run_full_deep_audit() -> dict:
    tickers = get_tickers(DEFAULT_UNIVERSE)
    df_raw = fetch_universe(tickers, years=10)

    df_clean_cols = {}
    for col in df_raw.columns:
        col_df = pd.DataFrame({"Close": df_raw[col], "Volume": 1000})
        filtered, _ = filter_vendor_artifacts(col_df)
        df_clean_cols[col] = filtered["Close"]

    df_close = pd.DataFrame(df_clean_cols).ffill().dropna(how="all")

    # Map tickers to asset classes
    asset_class_map = {}
    for ac, t_list in DEFAULT_UNIVERSE.items():
        for t in t_list:
            if t in df_close.columns:
                asset_class_map[t] = ac

    # 1. CAND-001 Baseline Run
    res_base = run_strategy_simulation(df_close, mom_lookback=126, vol_lookback=60, rebalance_freq=21, cost_bps=10.0)

    # 2. Parameter Perturbation Grid
    param_grid_results = {}
    for m_look in [63, 84, 126, 168, 252]:
        for v_look in [40, 60, 90]:
            for reb_f in [10, 21, 42]:
                tag = f"mom{m_look}_vol{v_look}_reb{reb_f}"
                r_sim = run_strategy_simulation(df_close, mom_lookback=m_look, vol_lookback=v_look, rebalance_freq=reb_f, cost_bps=10.0)
                param_grid_results[tag] = {
                    "mom_lookback": m_look,
                    "vol_lookback": v_look,
                    "rebalance_freq": reb_f,
                    "sharpe": float(r_sim["sharpe"]),
                    "cagr": float(r_sim["cagr"]),
                    "max_drawdown": float(r_sim["max_drawdown"]),
                    "turnover": float(r_sim["annualized_turnover"]),
                }

    # 3. Universe Robustness & Leave-One-Out (LOO)
    loo_results = {}
    # Leave-One-ETF-Out
    for drop_t in df_close.columns:
        sub_df = df_close.drop(columns=[drop_t])
        r_loo = run_strategy_simulation(sub_df, mom_lookback=126, vol_lookback=60, rebalance_freq=21)
        loo_results[f"minus_{drop_t}"] = {
            "dropped_ticker": drop_t,
            "sharpe": float(r_loo["sharpe"]),
            "cagr": float(r_loo["cagr"]),
            "max_drawdown": float(r_loo["max_drawdown"]),
        }

    # Leave-One-Asset-Class-Out
    for ac in set(asset_class_map.values()):
        ac_tickers = [t for t, c in asset_class_map.items() if c == ac]
        sub_df = df_close.drop(columns=[t for t in ac_tickers if t in df_close.columns])
        r_ac = run_strategy_simulation(sub_df, mom_lookback=126, vol_lookback=60, rebalance_freq=21)
        loo_results[f"minus_sector_{ac}"] = {
            "dropped_sector": ac,
            "sharpe": float(r_ac["sharpe"]),
            "cagr": float(r_ac["cagr"]),
            "max_drawdown": float(r_ac["max_drawdown"]),
        }

    # 4. Asset Contribution Decomposition
    weights_df = res_base["target_weights"]
    rets_df = df_close.pct_change().fillna(0.0)
    asset_contributions = {}
    for t in df_close.columns:
        w_t = weights_df[t]
        r_t = rets_df[t]
        pnl_series = w_t.shift(1).fillna(0.0) * r_t
        total_pnl_bps = float(pnl_series.sum() * 10000.0)
        avg_long_w = float(w_t[w_t > 0].mean()) if np.sum(w_t > 0) > 0 else 0.0
        avg_short_w = float(w_t[w_t < 0].mean()) if np.sum(w_t < 0) > 0 else 0.0
        pct_time_held = float(np.mean(w_t != 0.0))
        asset_contributions[t] = {
            "total_return_contribution_bps": total_pnl_bps,
            "percent_time_held": pct_time_held,
            "avg_long_weight": avg_long_w,
            "avg_short_weight": avg_short_w,
        }

    # 5. Macroeconomic Regime Analysis
    daily_r = res_base["returns"]
    spy_p = df_close["SPY"] if "SPY" in df_close.columns else df_close.iloc[:, 0]
    spy_sma200 = spy_p.rolling(200).mean()
    risk_on = spy_p >= spy_sma200
    risk_off = spy_p < spy_sma200

    def calc_sub_metrics(mask: pd.Series) -> dict:
        sub_r = daily_r.loc[mask.reindex(daily_r.index).fillna(False)]
        arr = sub_r.to_numpy()
        sd = np.std(arr, ddof=1) if len(arr) > 1 else 1e-8
        sh = float((np.mean(arr) / sd) * np.sqrt(252.0)) if sd > 0 else 0.0
        tot = float((1.0 + sub_r).prod() - 1.0) if len(arr) else 0.0
        n_y = len(arr) / 252.0 if len(arr) else 1.0
        cagr = (1.0 + tot) ** (1.0 / max(1e-4, n_y)) - 1.0 if tot > -1.0 else -1.0
        return {"sharpe": sh, "cagr": cagr, "days": len(arr)}

    regime_results = {
        "risk_on_bull": calc_sub_metrics(risk_on),
        "risk_off_bear": calc_sub_metrics(risk_off),
    }

    # 6. Realistic Friction & Borrow Sensitivity
    friction_sweep = {}
    for c_bps in [0.0, 5.0, 10.0, 20.0, 30.0, 50.0, 100.0, 150.0, 200.0]:
        r_f = run_strategy_simulation(df_close, cost_bps=c_bps, borrow_bps=25.0)
        friction_sweep[f"{int(c_bps)} bps"] = {
            "sharpe": float(r_f["sharpe"]),
            "cagr": float(r_f["cagr"]),
            "max_drawdown": float(r_f["max_drawdown"]),
        }

    borrow_sweep = {}
    for b_bps in [0.0, 25.0, 50.0, 100.0, 200.0]:
        r_b = run_strategy_simulation(df_close, cost_bps=10.0, borrow_bps=b_bps)
        borrow_sweep[f"{int(b_bps)} bps/yr"] = {
            "sharpe": float(r_b["sharpe"]),
            "cagr": float(r_b["cagr"]),
            "max_drawdown": float(r_b["max_drawdown"]),
        }

    # 7. Candidate Alpha Formulations (CAND-003, CAND-004, CAND-005)
    cand003_res = run_strategy_simulation(df_close, strategy_mode="CAND_003_MULTI_HORIZON")
    cand004_res = run_strategy_simulation(df_close, strategy_mode="CAND_004_DEMARCATED", asset_class_map=asset_class_map)
    cand005_res = run_strategy_simulation(df_close, strategy_mode="CAND_005_VOL_GATED")

    splits = get_splits(df_close, train_pct=0.60, val_pct=0.20)

    def eval_walk_forward(r_s: pd.Series) -> dict:
        train_r = r_s.loc[splits["TRAIN"].intersection(r_s.index)]
        val_r = r_s.loc[splits["VALIDATION"].intersection(r_s.index)]
        oos_r = r_s.loc[splits["TRUE_OOS"].intersection(r_s.index)]

        def sub_eval(sub: pd.Series) -> dict:
            arr = sub.to_numpy()
            sd = np.std(arr, ddof=1) if len(arr) > 1 else 1e-8
            sh = float((np.mean(arr) / sd) * np.sqrt(252)) if sd > 0 else 0.0
            tot = float((1.0 + sub).prod() - 1.0) if len(arr) else 0.0
            n_y = len(arr) / 252.0 if len(arr) else 1.0
            cagr = (1.0 + tot) ** (1.0 / max(1e-4, n_y)) - 1.0 if tot > -1.0 else -1.0
            cum = (1.0 + sub).cumprod()
            pk = cum.cummax()
            mdd = float(((cum - pk) / pk).min()) if len(cum) else 0.0
            return {"sharpe": sh, "cagr": cagr, "max_drawdown": mdd}

        return {
            "TRAIN (60%)": sub_eval(train_r),
            "VALIDATION (20%)": sub_eval(val_r),
            "TRUE_OOS (20%)": sub_eval(oos_r),
        }

    # 8. High-Count Circular Block Permutation Null (B=500)
    B = 500
    rng = np.random.default_rng(42)
    t_vals = daily_r.to_numpy()
    T_len = len(t_vals)
    block_len = 21
    n_blocks = int(np.ceil(T_len / block_len))
    null_sharpes = []

    for _ in range(B):
        start_idxs = rng.integers(0, T_len, size=n_blocks)
        perm_blocks = [np.take(t_vals, np.arange(idx, idx + block_len), mode="wrap") for idx in start_idxs]
        r_perm = np.concatenate(perm_blocks)[:T_len]
        sd_p = np.std(r_perm, ddof=1) if len(r_perm) > 1 else 1e-8
        sh_p = float((np.mean(r_perm) / sd_p) * np.sqrt(252.0))
        null_sharpes.append(sh_p)

    obs_sh = float(res_base["sharpe"])
    k_exceed = int(np.sum(np.array(null_sharpes) >= obs_sh))
    corrected_p = float((k_exceed + 1.0) / (B + 1.0))

    audit_payload = {
        "cand_001_control_reproduced": {
            "sharpe": float(res_base["sharpe"]),
            "cagr": float(res_base["cagr"]),
            "volatility": float(res_base["annualized_volatility"]),
            "max_drawdown": float(res_base["max_drawdown"]),
            "sortino": float(res_base["sortino"]),
            "turnover": float(res_base["annualized_turnover"]),
            "total_costs": float(res_base["total_costs"]),
            "final_nav": float(res_base["final_nav"]),
            "walk_forward": eval_walk_forward(res_base["returns"]),
        },
        "parameter_perturbation_grid": param_grid_results,
        "leave_one_out_robustness": loo_results,
        "asset_contributions": asset_contributions,
        "regime_analysis": regime_results,
        "friction_sensitivity": friction_sweep,
        "borrow_sensitivity": borrow_sweep,
        "candidates": {
            "CAND-003 (Multi-Horizon Blend)": {
                "sharpe": float(cand003_res["sharpe"]),
                "cagr": float(cand003_res["cagr"]),
                "max_drawdown": float(cand003_res["max_drawdown"]),
                "turnover": float(cand003_res["annualized_turnover"]),
                "walk_forward": eval_walk_forward(cand003_res["returns"]),
            },
            "CAND-004 (Demarcated Asset Allocation)": {
                "sharpe": float(cand004_res["sharpe"]),
                "cagr": float(cand004_res["cagr"]),
                "max_drawdown": float(cand004_res["max_drawdown"]),
                "turnover": float(cand004_res["annualized_turnover"]),
                "walk_forward": eval_walk_forward(cand004_res["returns"]),
            },
            "CAND-005 (Macro Volatility Gated)": {
                "sharpe": float(cand005_res["sharpe"]),
                "cagr": float(cand005_res["cagr"]),
                "max_drawdown": float(cand005_res["max_drawdown"]),
                "turnover": float(cand005_res["annualized_turnover"]),
                "walk_forward": eval_walk_forward(cand005_res["returns"]),
            },
        },
        "permutation_null_gate3": {
            "permutations_B": B,
            "null_exceedances_k": k_exceed,
            "corrected_p_value": corrected_p,
            "formula": "p = (k + 1) / (B + 1)",
            "passed": bool(corrected_p <= 0.05),
        },
    }

    out_file = Path(__file__).resolve().parent.parent / "results" / "cand001_deep_audit_results.json"
    with open(out_file, "w") as f:
        json.dump(audit_payload, f, indent=2)

    return audit_payload


if __name__ == "__main__":
    res = run_full_deep_audit()
    print("=" * 80)
    print(" CAND-001 DEEP ADVERSARIAL AUDIT COMPLETE")
    print("=" * 80)
    b = res["cand_001_control_reproduced"]
    print(f"CAND-001 Control: Sharpe={b['sharpe']:.4f} | CAGR={b['cagr']*100:.2f}% | MaxDD={b['max_drawdown']*100:.2f}% | OOS Sharpe={b['walk_forward']['TRUE_OOS (20%)']['sharpe']:.4f}")
    c3 = res["candidates"]["CAND-003 (Multi-Horizon Blend)"]
    print(f"CAND-003 Multi-Hz: Sharpe={c3['sharpe']:.4f} | CAGR={c3['cagr']*100:.2f}% | MaxDD={c3['max_drawdown']*100:.2f}% | OOS Sharpe={c3['walk_forward']['TRUE_OOS (20%)']['sharpe']:.4f}")
    c4 = res["candidates"]["CAND-004 (Demarcated Asset Allocation)"]
    print(f"CAND-004 Demarc:  Sharpe={c4['sharpe']:.4f} | CAGR={c4['cagr']*100:.2f}% | MaxDD={c4['max_drawdown']*100:.2f}% | OOS Sharpe={c4['walk_forward']['TRUE_OOS (20%)']['sharpe']:.4f}")
    c5 = res["candidates"]["CAND-005 (Macro Volatility Gated)"]
    print(f"CAND-005 Vol-Gate: Sharpe={c5['sharpe']:.4f} | CAGR={c5['cagr']*100:.2f}% | MaxDD={c5['max_drawdown']*100:.2f}% | OOS Sharpe={c5['walk_forward']['TRUE_OOS (20%)']['sharpe']:.4f}")
    p = res["permutation_null_gate3"]
    print(f"Gate 3 Permutations (B={p['permutations_B']}): k={p['null_exceedances_k']} | Corrected p={p['corrected_p_value']:.4f} | Passed={p['passed']}")
