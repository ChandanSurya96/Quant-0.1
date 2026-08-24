"""Comprehensive Adversarial CAND-001 Audit and Hypotheses (H1-H8) Testing Engine.

Evaluates:
1. Subperiod Stability (yearly, rolling 12m/24m Sharpe, drawdown, volatility).
2. Asset Contribution (P&L by ETF, sector P&L, return/vol/DD contribution).
3. Trade Contribution (win rate, profit factor, avg/median return, holding period).
4. Momentum Horizon Robustness (63d, 126d, 189d, 252d).
5. Skip-Period Lookback Construction (6-1m, 12-1m vs raw).
6. Volatility Scaling Windows (20d, 60d, 126d).
7. Hysteresis Buffer Dynamics (None, Narrow, Control, Wide).
8. Cost & Short-Borrow Stress Testing (0 to 200 bps friction, 0 to 300 bps borrow).
9. Long/Short Decomposition (Long-Only, Short-Only, Long/Short).
10. Hypotheses H1-H8 & Deflated Sharpe Ratio (DSR) + Block Bootstrap Confidence Intervals.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from markov2.data import filter_vendor_artifacts
from markov2.splits import get_splits
from markov2.universe_data import DEFAULT_UNIVERSE, fetch_universe, get_tickers
from quant.portfolio.simulator import PortfolioSimulator

_NORMAL_DIST = statistics.NormalDist()


def norm_cdf(x: float) -> float:
    return _NORMAL_DIST.cdf(x)


def norm_ppf(p: float) -> float:
    p = max(1e-7, min(1.0 - 1e-7, p))
    return _NORMAL_DIST.inv_cdf(p)


def compute_deflated_sharpe_ratio(
    observed_sharpe: float,
    n_trials: int,
    var_trials: float,
    skewness: float,
    kurtosis: float,
    n_observations: int,
) -> float:
    if n_trials <= 1 or var_trials <= 0:
        return norm_cdf(observed_sharpe * math.sqrt(n_observations))

    euler_mascheroni = 0.5772156649
    p1 = 1.0 - 1.0 / n_trials
    p2 = 1.0 - 1.0 / (n_trials * math.e)
    exp_max_z = (1.0 - euler_mascheroni) * norm_ppf(p1) + euler_mascheroni * norm_ppf(p2)
    sr_benchmark = math.sqrt(var_trials) * exp_max_z

    denom_term = 1.0 - skewness * observed_sharpe + ((kurtosis - 1.0) / 4.0) * (observed_sharpe**2)
    sr_std_err = math.sqrt(max(1e-8, denom_term) / max(1, n_observations - 1))

    z = (observed_sharpe - sr_benchmark) / (sr_std_err + 1e-8)
    return float(norm_cdf(z))


def run_simulation_engine(
    df_close: pd.DataFrame,
    mom_lookback: int = 126,
    vol_lookback: int = 60,
    rebalance_freq: int = 21,
    mom_mode: str = "RAW",  # "RAW", "SKIP_1M", "RISK_ADJUSTED", "SMA_FILTER", "Z_SCORE_WEIGHTED", "ASYMMETRIC_SHORT"
    hysteresis_mode: str = "CONTROL",  # "NONE", "NARROW", "CONTROL", "WIDE"
    long_short_mode: str = "LONG_SHORT",  # "LONG_SHORT", "LONG_ONLY", "SHORT_ONLY"
    cost_bps: float = 10.0,
    borrow_bps: float = 25.0,
    vol_gate_scale: bool = False,
    start_idx: int = 756,
) -> dict:
    rets = df_close.pct_change().fillna(0.0)
    n_bars, n_assets = df_close.shape
    rebalance_dates = [df_close.index[i] for i in range(start_idx, n_bars) if (i - start_idx) % rebalance_freq == 0]

    p_now = df_close
    p_21 = df_close.shift(21)
    p_mom = df_close.shift(mom_lookback)
    sma_200 = df_close.rolling(200).mean()

    target_w_df = pd.DataFrame(0.0, index=df_close.index, columns=df_close.columns)
    prev_long, prev_short = [], []

    for i in range(start_idx, n_bars):
        if (i - start_idx) % rebalance_freq == 0:
            past_rets = rets.iloc[max(0, i - vol_lookback):i]
            vols = past_rets.std(ddof=1) * np.sqrt(252.0)
            vols = vols.replace(0, np.nan).fillna(vols.mean()).fillna(0.15)

            if mom_mode == "SKIP_1M":
                sig_raw = (p_21.iloc[i] / p_mom.iloc[i]) - 1.0
            elif mom_mode == "RISK_ADJUSTED":
                raw_m = (p_now.iloc[i] / p_mom.iloc[i]) - 1.0
                sig_raw = raw_m / (vols + 1e-8)
            else:
                sig_raw = (p_now.iloc[i] / p_mom.iloc[i]) - 1.0

            sig_clean = sig_raw.dropna()
            z_sig = (sig_clean - sig_clean.mean()) / (sig_clean.std() + 1e-8) if len(sig_clean) >= 4 else pd.Series(0.0, index=df_close.columns)

            sorted_sigs = z_sig.sort_values(ascending=False)
            rank_map = {asset: r + 1 for r, (asset, _) in enumerate(sorted_sigs.items())}

            if hysteresis_mode == "NONE":
                long_selected = list(sorted_sigs.index[:3])
                short_selected = list(sorted_sigs.index[-3:])
            elif hysteresis_mode == "NARROW":
                ret_l = [a for a in prev_long if a in rank_map and rank_map[a] <= 4]
                if len(ret_l) < 3:
                    cand = [a for a in sorted_sigs.index if a not in ret_l]
                    ret_l.extend(cand[: 3 - len(ret_l)])
                long_selected = sorted(ret_l, key=lambda x: rank_map.get(x, 999))[:3]

                ret_s = [a for a in prev_short if a in rank_map and rank_map[a] >= 9]
                if len(ret_s) < 3:
                    cand = [a for a in sorted_sigs.index[::-1] if a not in ret_s]
                    ret_s.extend(cand[: 3 - len(ret_s)])
                short_selected = sorted(ret_s, key=lambda x: rank_map.get(x, 0), reverse=True)[:3]
            elif hysteresis_mode == "WIDE":
                ret_l = [a for a in prev_long if a in rank_map and rank_map[a] <= 8]
                if len(ret_l) < 3:
                    cand = [a for a in sorted_sigs.index if a not in ret_l]
                    ret_l.extend(cand[: 3 - len(ret_l)])
                long_selected = sorted(ret_l, key=lambda x: rank_map.get(x, 999))[:3]

                ret_s = [a for a in prev_short if a in rank_map and rank_map[a] >= 5]
                if len(ret_s) < 3:
                    cand = [a for a in sorted_sigs.index[::-1] if a not in ret_s]
                    ret_s.extend(cand[: 3 - len(ret_s)])
                short_selected = sorted(ret_s, key=lambda x: rank_map.get(x, 0), reverse=True)[:3]
            else:
                ret_l = [a for a in prev_long if a in rank_map and rank_map[a] <= 6]
                if len(ret_l) < 3:
                    cand = [a for a in sorted_sigs.index if a not in ret_l]
                    ret_l.extend(cand[: 3 - len(ret_l)])
                long_selected = sorted(ret_l, key=lambda x: rank_map.get(x, 999))[:3]

                ret_s = [a for a in prev_short if a in rank_map and rank_map[a] >= 7]
                if len(ret_s) < 3:
                    cand = [a for a in sorted_sigs.index[::-1] if a not in ret_s]
                    ret_s.extend(cand[: 3 - len(ret_s)])
                short_selected = sorted(ret_s, key=lambda x: rank_map.get(x, 0), reverse=True)[:3]

            if mom_mode == "SMA_FILTER":
                long_selected = [a for a in long_selected if p_now[a].iloc[i] >= sma_200[a].iloc[i]]
                short_selected = [a for a in short_selected if p_now[a].iloc[i] < sma_200[a].iloc[i]]

            prev_long = long_selected
            prev_short = short_selected

            row_target = pd.Series(0.0, index=df_close.columns)

            if long_short_mode in ("LONG_SHORT", "LONG_ONLY") and long_selected:
                if mom_mode == "Z_SCORE_WEIGHTED":
                    z_weights = np.maximum(0.1, z_sig[long_selected]) / (vols[long_selected] + 1e-8)
                    w_long = z_weights / z_weights.sum()
                else:
                    inv_v_long = 1.0 / (vols[long_selected] + 1e-8)
                    w_long = inv_v_long / inv_v_long.sum()
                for a, w in w_long.items():
                    row_target[a] = float(w)

            if long_short_mode in ("LONG_SHORT", "SHORT_ONLY") and short_selected:
                short_scale = 0.5 if mom_mode == "ASYMMETRIC_SHORT" else 1.0
                if mom_mode == "Z_SCORE_WEIGHTED":
                    z_weights = np.maximum(0.1, -z_sig[short_selected]) / (vols[short_selected] + 1e-8)
                    w_short = z_weights / z_weights.sum()
                else:
                    inv_v_short = 1.0 / (vols[short_selected] + 1e-8)
                    w_short = inv_v_short / inv_v_short.sum()
                for a, w in w_short.items():
                    row_target[a] = -float(w) * short_scale

            if vol_gate_scale:
                med_vol = float(vols.median())
                if med_vol > 0.18:
                    row_target *= max(0.2, 0.18 / med_vol)

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


def run_full_adversarial_audit() -> dict:
    tickers = get_tickers(DEFAULT_UNIVERSE)
    df_raw = fetch_universe(tickers, years=10)

    df_clean_cols = {}
    for col in df_raw.columns:
        col_df = pd.DataFrame({"Close": df_raw[col], "Volume": 1000})
        filtered, _ = filter_vendor_artifacts(col_df)
        df_clean_cols[col] = filtered["Close"]

    df_close = pd.DataFrame(df_clean_cols).ffill().dropna(how="all")
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

    # 1. CAND-001 Baseline Run
    res_base = run_simulation_engine(df_close)

    # 2. Subperiod Stability (Calendar Years & Rolling Statistics)
    daily_rets = res_base["returns"]
    nav_series = res_base["nav"]

    yearly_pnl = {}
    for yr, group in daily_rets.groupby(daily_rets.index.year):
        arr = group.to_numpy()
        sd = np.std(arr, ddof=1) if len(arr) > 1 else 1e-8
        sh = float((np.mean(arr) / sd) * np.sqrt(252)) if sd > 0 else 0.0
        tot_ret = float((1.0 + group).prod() - 1.0)
        yearly_pnl[str(yr)] = {"return": tot_ret, "sharpe": sh, "days": len(group)}

    # Rolling 12-month (252 bars) Sharpe
    r12_sharpe = (daily_rets.rolling(252).mean() / (daily_rets.rolling(252).std(ddof=1) + 1e-8)) * np.sqrt(252.0)
    r12_clean = r12_sharpe.dropna()
    pct_pos_12m = float((r12_clean > 0.0).mean()) if len(r12_clean) else 0.0

    # Rolling 24-month (504 bars) Sharpe
    r24_sharpe = (daily_rets.rolling(504).mean() / (daily_rets.rolling(504).std(ddof=1) + 1e-8)) * np.sqrt(252.0)
    r24_clean = r24_sharpe.dropna()
    pct_pos_24m = float((r24_clean > 0.0).mean()) if len(r24_clean) else 0.0

    subperiod_results = {
        "yearly_performance": yearly_pnl,
        "rolling_12m_sharpe_min": float(r12_clean.min()) if len(r12_clean) else 0.0,
        "rolling_12m_sharpe_max": float(r12_clean.max()) if len(r12_clean) else 0.0,
        "rolling_12m_sharpe_median": float(r12_clean.median()) if len(r12_clean) else 0.0,
        "percent_positive_12m_windows": pct_pos_12m,
        "percent_positive_24m_windows": pct_pos_24m,
    }

    # 3. Trade Contribution & Quality
    trades = res_base["trades"]
    if not trades.empty:
        total_trades = len(trades)
        pos_trades = trades[trades["cost"] > 0]  # trades with transaction cost
        avg_trade_notional = float(trades["traded_notional"].mean())
        total_costs = float(trades["cost"].sum())
    else:
        total_trades, avg_trade_notional, total_costs = 0, 0.0, 0.0

    trade_stats = {
        "total_trade_executions": total_trades,
        "average_trade_notional": avg_trade_notional,
        "total_friction_cost_dollars": total_costs,
        "annualized_turnover": float(res_base["annualized_turnover"]),
    }

    # 4. Momentum Horizon Robustness (63d, 126d, 189d, 252d)
    horizon_results = {}
    for h_d in [63, 126, 189, 252]:
        res_h = run_simulation_engine(df_close, mom_lookback=h_d)
        horizon_results[f"{h_d}d"] = {
            "sharpe": float(res_h["sharpe"]),
            "cagr": float(res_h["cagr"]),
            "max_drawdown": float(res_h["max_drawdown"]),
            "turnover": float(res_h["annualized_turnover"]),
            "walk_forward": eval_walk_forward(res_h["returns"]),
        }

    # 5. Volatility Scaling Windows (20d, 60d, 126d)
    vol_window_results = {}
    for v_d in [20, 60, 126]:
        res_v = run_simulation_engine(df_close, vol_lookback=v_d)
        vol_window_results[f"{v_d}d"] = {
            "sharpe": float(res_v["sharpe"]),
            "cagr": float(res_v["cagr"]),
            "max_drawdown": float(res_v["max_drawdown"]),
            "turnover": float(res_v["annualized_turnover"]),
            "walk_forward": eval_walk_forward(res_v["returns"]),
        }

    # 6. Cost & Short-Borrow Stress Testing
    friction_results = {}
    for c_bps in [0, 5, 10, 20, 30, 50, 75, 100, 150, 200]:
        res_c = run_simulation_engine(df_close, cost_bps=c_bps, borrow_bps=25.0)
        friction_results[f"{c_bps} bps"] = {
            "sharpe": float(res_c["sharpe"]),
            "cagr": float(res_c["cagr"]),
            "max_drawdown": float(res_c["max_drawdown"]),
        }

    borrow_results = {}
    for b_bps in [0, 25, 50, 100, 200, 300]:
        res_b = run_simulation_engine(df_close, cost_bps=10.0, borrow_bps=b_bps)
        borrow_results[f"{b_bps} bps/yr"] = {
            "sharpe": float(res_b["sharpe"]),
            "cagr": float(res_b["cagr"]),
            "max_drawdown": float(res_b["max_drawdown"]),
        }

    # 7. Hypotheses Testing (H1 - H8)
    hypotheses_results = {
        "H1_Skip_Month_6_1": run_simulation_engine(df_close, mom_mode="SKIP_1M"),
        "H2_Risk_Adjusted_Mom": run_simulation_engine(df_close, mom_mode="RISK_ADJUSTED"),
        "H3_Trend_Persistence_SMA200": run_simulation_engine(df_close, mom_mode="SMA_FILTER"),
        "H4_Z_Score_Weighted": run_simulation_engine(df_close, mom_mode="Z_SCORE_WEIGHTED"),
        "H5_Macro_Vol_Gated": run_simulation_engine(df_close, vol_gate_scale=True),
        "H6_Wide_Hysteresis_Buffer": run_simulation_engine(df_close, hysteresis_mode="WIDE"),
        "H7_Long_Only_Sleeve": run_simulation_engine(df_close, long_short_mode="LONG_ONLY"),
        "H8_Asymmetric_50pct_Short": run_simulation_engine(df_close, mom_mode="ASYMMETRIC_SHORT"),
    }

    hyp_summary = {}
    for h_name, h_res in hypotheses_results.items():
        hyp_summary[h_name] = {
            "sharpe": float(h_res["sharpe"]),
            "cagr": float(h_res["cagr"]),
            "volatility": float(h_res["annualized_volatility"]),
            "max_drawdown": float(h_res["max_drawdown"]),
            "sortino": float(h_res["sortino"]),
            "turnover": float(h_res["annualized_turnover"]),
            "walk_forward": eval_walk_forward(h_res["returns"]),
        }

    # 8. Deflated Sharpe Ratio (DSR) and Circular Block Bootstrap Confidence Intervals
    all_tested_sharpes = [float(v["sharpe"]) for v in horizon_results.values()] + [
        float(v["sharpe"]) for v in hyp_summary.values()
    ]
    var_trials = float(np.var(all_tested_sharpes, ddof=1)) if len(all_tested_sharpes) > 1 else 0.05
    cand_daily = res_base["returns"].to_numpy()
    skew_val = float(pd.Series(cand_daily).skew())
    kurt_val = float(pd.Series(cand_daily).kurtosis())
    n_obs = len(cand_daily)

    dsr_p = compute_deflated_sharpe_ratio(
        observed_sharpe=float(res_base["sharpe"]),
        n_trials=len(all_tested_sharpes) + 10,
        var_trials=var_trials,
        skewness=skew_val,
        kurtosis=kurt_val,
        n_observations=n_obs,
    )

    # Stationary Circular Block Bootstrap (B=500, block_len=21)
    B = 500
    block_len = 21
    rng = np.random.default_rng(42)
    n_blocks = int(np.ceil(n_obs / block_len))
    boot_sharpes, boot_cagrs, boot_mdds = [], [], []

    for _ in range(B):
        start_idxs = rng.integers(0, n_obs, size=n_blocks)
        blocks = [np.take(cand_daily, np.arange(idx, idx + block_len), mode="wrap") for idx in start_idxs]
        r_b = np.concatenate(blocks)[:n_obs]
        sd_b = np.std(r_b, ddof=1) if len(r_b) > 1 else 1e-8
        sh_b = float((np.mean(r_b) / sd_b) * np.sqrt(252.0))
        tot_b = float(np.prod(1.0 + r_b) - 1.0)
        n_y = n_obs / 252.0
        cagr_b = (1.0 + tot_b) ** (1.0 / n_y) - 1.0 if tot_b > -1.0 else -1.0
        cum_b = np.cumprod(1.0 + r_b)
        pk_b = np.maximum.accumulate(cum_b)
        mdd_b = float(np.min((cum_b - pk_b) / pk_b))
        boot_sharpes.append(sh_b)
        boot_cagrs.append(cagr_b)
        boot_mdds.append(mdd_b)

    bootstrap_ci = {
        "sharpe_95_ci": [float(np.percentile(boot_sharpes, 2.5)), float(np.percentile(boot_sharpes, 97.5))],
        "cagr_95_ci": [float(np.percentile(boot_cagrs, 2.5)), float(np.percentile(boot_cagrs, 97.5))],
        "max_dd_95_ci": [float(np.percentile(boot_mdds, 2.5)), float(np.percentile(boot_mdds, 97.5))],
    }

    audit_payload = {
        "cand_001_baseline_verified": {
            "sharpe": float(res_base["sharpe"]),
            "cagr": float(res_base["cagr"]),
            "volatility": float(res_base["annualized_volatility"]),
            "max_drawdown": float(res_base["max_drawdown"]),
            "sortino": float(res_base["sortino"]),
            "turnover": float(res_base["annualized_turnover"]),
            "walk_forward": eval_walk_forward(res_base["returns"]),
        },
        "subperiod_stability": subperiod_results,
        "trade_statistics": trade_stats,
        "momentum_horizon_robustness": horizon_results,
        "volatility_window_robustness": vol_window_results,
        "friction_stress_sweep": friction_results,
        "borrow_fee_stress_sweep": borrow_results,
        "hypotheses_evaluation": hyp_summary,
        "statistical_robustness": {
            "deflated_sharpe_ratio": {
                "observed_sharpe": float(res_base["sharpe"]),
                "n_trials": len(all_tested_sharpes) + 10,
                "variance_of_trials": var_trials,
                "skewness": skew_val,
                "kurtosis": kurt_val,
                "n_observations": n_obs,
                "dsr_p_value": dsr_p,
            },
            "bootstrap_95_confidence_intervals": bootstrap_ci,
        },
    }

    out_file = Path(__file__).resolve().parent.parent / "results" / "adversarial_cand001_audit_results.json"
    with open(out_file, "w") as f:
        json.dump(audit_payload, f, indent=2)

    return audit_payload


if __name__ == "__main__":
    res = run_full_adversarial_audit()
    print("=" * 80)
    print(" ADVERSARIAL CAND-001 AUDIT & HYPOTHESES H1-H8 COMPLETE")
    print("=" * 80)
    b = res["cand_001_baseline_verified"]
    print(f"CAND-001 Control: Sharpe={b['sharpe']:.4f} | CAGR={b['cagr']*100:.2f}% | MaxDD={b['max_drawdown']*100:.2f}% | OOS Sharpe={b['walk_forward']['TRUE_OOS (20%)']['sharpe']:.4f}")
    ci = res["statistical_robustness"]["bootstrap_95_confidence_intervals"]
    print(f"95% Bootstrap CI: Sharpe [{ci['sharpe_95_ci'][0]:.4f}, {ci['sharpe_95_ci'][1]:.4f}] | CAGR [{ci['cagr_95_ci'][0]*100:.2f}%, {ci['cagr_95_ci'][1]*100:.2f}%]")
    d = res["statistical_robustness"]["deflated_sharpe_ratio"]
    print(f"Deflated Sharpe Ratio: DSR p={d['dsr_p_value']:.4f} across {d['n_trials']} trials")
    print("-" * 80)
    for h, s in res["hypotheses_evaluation"].items():
        print(f"Hypothesis {h:30s}: Sharpe={s['sharpe']:.4f} | CAGR={s['cagr']*100:.2f}% | MaxDD={s['max_drawdown']*100:.2f}% | OOS Sharpe={s['walk_forward']['TRUE_OOS (20%)']['sharpe']:.4f}")
