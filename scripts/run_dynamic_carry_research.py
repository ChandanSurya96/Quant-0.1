"""Dynamic Carry Research Runner & 4-Gate Econometric Validation Engine.

Evaluates CAND-010A through CAND-010E against CANONICAL CONTROL (CAND-001-FROZEN-CONTROL-V2).
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
from quant.factors.dynamic_carry import DynamicCarryEngine
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


def run_carry_simulation(
    df_close: pd.DataFrame,
    carry_matrix: pd.DataFrame,
    mode: str = "CONTROL_CAND001",  # "CONTROL_CAND001", "CAND_010A", "CAND_010B", "CAND_010C", "CAND_010D", "CAND_010E"
    rebalance_freq: int = 21,
    cost_bps: float = 10.0,
    borrow_bps: float = 25.0,
    start_idx: int = 756,
) -> dict:
    rets = df_close.pct_change().fillna(0.0)
    n_bars, n_assets = df_close.shape
    rebalance_dates = [df_close.index[i] for i in range(start_idx, n_bars) if (i - start_idx) % rebalance_freq == 0]

    p_now = df_close
    p_21 = df_close.shift(21)
    p_126 = df_close.shift(126)

    target_w_df = pd.DataFrame(0.0, index=df_close.index, columns=df_close.columns)
    prev_long, prev_short = [], []

    for i in range(start_idx, n_bars):
        if (i - start_idx) % rebalance_freq == 0:
            past_rets = rets.iloc[max(0, i - 60):i]
            vols = past_rets.std(ddof=1) * np.sqrt(252.0)
            vols = vols.replace(0, np.nan).fillna(vols.mean()).fillna(0.15)

            # 1. Momentum Signal
            if mode == "CAND_010C":
                # Skip-Month 6-1
                raw_mom = (p_21.iloc[i] / p_126.iloc[i]) - 1.0
            else:
                raw_mom = (p_now.iloc[i] / p_126.iloc[i]) - 1.0
            z_mom = (raw_mom - raw_mom.mean()) / (raw_mom.std(ddof=1) + 1e-8)

            # 2. Dynamic Carry Signal
            z_carry = DynamicCarryEngine.get_cross_sectional_z_scores(carry_matrix, i)

            # 3. Composite Scoring
            if mode == "CONTROL_CAND001":
                comb_sig = z_mom
            elif mode == "CAND_010A":
                comb_sig = z_carry
            elif mode == "CAND_010B":
                comb_sig = 0.50 * z_mom + 0.50 * z_carry
            elif mode == "CAND_010C":
                comb_sig = 0.70 * z_mom + 0.30 * z_carry
            elif mode == "CAND_010D":
                comb_sig = 0.70 * z_mom + 0.30 * z_carry
            elif mode == "CAND_010E":
                # Regime filter: only take positive momentum when carry is not severely negative
                comb_sig = z_mom.copy()
                comb_sig[z_carry < -1.0] = -999.0
            else:
                comb_sig = z_mom

            sorted_sigs = comb_sig.sort_values(ascending=False)
            rank_map = {asset: r + 1 for r, (asset, _) in enumerate(sorted_sigs.items())}

            # Rank Hysteresis
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

            prev_long = long_selected
            prev_short = short_selected

            row_target = pd.Series(0.0, index=df_close.columns)

            if long_selected:
                inv_v_long = 1.0 / (vols[long_selected] + 1e-8)
                w_long = inv_v_long / inv_v_long.sum()
                for a, w in w_long.items():
                    row_target[a] = float(w)

            if short_selected:
                short_scale = 0.50 if mode == "CAND_010D" else 1.0
                inv_v_short = 1.0 / (vols[short_selected] + 1e-8)
                w_short = inv_v_short / inv_v_short.sum()
                for a, w in w_short.items():
                    row_target[a] = -float(w) * short_scale

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


def run_full_carry_research() -> dict:
    tickers = get_tickers(DEFAULT_UNIVERSE)
    df_raw = fetch_universe(tickers, years=10)

    df_clean_cols = {}
    for col in df_raw.columns:
        col_df = pd.DataFrame({"Close": df_raw[col], "Volume": 1000})
        filtered, _ = filter_vendor_artifacts(col_df)
        df_clean_cols[col] = filtered["Close"]

    df_close = pd.DataFrame(df_clean_cols).ffill().dropna(how="all")
    splits = get_splits(df_close, train_pct=0.60, val_pct=0.20)

    carry_matrix = DynamicCarryEngine.compute_dynamic_carry_matrix(df_close)

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

    modes = [
        ("CONTROL_CAND001", "CAND-001-FROZEN-CONTROL-V2"),
        ("CAND_010A", "CAND-010A (Dynamic Carry Alone)"),
        ("CAND_010B", "CAND-010B (50/50 Mom + Dynamic Carry)"),
        ("CAND_010C", "CAND-010C (70/30 Skip-Mom + Dynamic Carry)"),
        ("CAND_010D", "CAND-010D (Asymmetric Short + Dynamic Carry)"),
        ("CAND_010E", "CAND-010E (Dynamic Carry Regime Filter)"),
    ]

    candidate_results = {}
    for m_code, m_name in modes:
        res = run_carry_simulation(df_close, carry_matrix, mode=m_code)
        candidate_results[m_name] = {
            "code": m_code,
            "sharpe": float(res["sharpe"]),
            "cagr": float(res["cagr"]),
            "volatility": float(res["annualized_volatility"]),
            "max_drawdown": float(res["max_drawdown"]),
            "sortino": float(res["sortino"]),
            "turnover": float(res["annualized_turnover"]),
            "walk_forward": eval_walk_forward(res["returns"]),
        }

    # Friction sweep for best dynamic carry candidate vs control
    friction_sweep = {}
    for c_bps in [0, 5, 10, 20, 30, 50, 75, 100, 150, 200]:
        r_ctrl = run_carry_simulation(df_close, carry_matrix, mode="CONTROL_CAND001", cost_bps=c_bps)
        r_10c = run_carry_simulation(df_close, carry_matrix, mode="CAND_010C", cost_bps=c_bps)
        friction_sweep[f"{c_bps} bps"] = {
            "control_sharpe": float(r_ctrl["sharpe"]),
            "cand_010c_sharpe": float(r_10c["sharpe"]),
        }

    # Deflated Sharpe Ratio
    all_sharpes = [v["sharpe"] for v in candidate_results.values()]
    var_trials = float(np.var(all_sharpes, ddof=1)) if len(all_sharpes) > 1 else 0.05
    cand_daily = run_carry_simulation(df_close, carry_matrix, mode="CAND_010C")["returns"].to_numpy()
    skew_val = float(pd.Series(cand_daily).skew())
    kurt_val = float(pd.Series(cand_daily).kurtosis())
    n_obs = len(cand_daily)

    dsr = compute_deflated_sharpe_ratio(
        observed_sharpe=float(candidate_results["CAND-010C (70/30 Skip-Mom + Dynamic Carry)"]["sharpe"]),
        n_trials=len(all_sharpes) + 15,
        var_trials=var_trials,
        skewness=skew_val,
        kurtosis=kurt_val,
        n_observations=n_obs,
    )

    research_payload = {
        "candidate_evaluations": candidate_results,
        "friction_sensitivity": friction_sweep,
        "deflated_sharpe_ratio": {
            "observed_sharpe": float(candidate_results["CAND-010C (70/30 Skip-Mom + Dynamic Carry)"]["sharpe"]),
            "n_trials": len(all_sharpes) + 15,
            "variance_of_trials": var_trials,
            "skewness": skew_val,
            "kurtosis": kurt_val,
            "n_observations": n_obs,
            "dsr_p_value": dsr,
        },
    }

    out_file = Path(__file__).resolve().parent.parent / "results" / "dynamic_carry_research_results.json"
    with open(out_file, "w") as f:
        json.dump(research_payload, f, indent=2)

    return research_payload


if __name__ == "__main__":
    res = run_full_carry_research()
    print("=" * 80)
    print(" DYNAMIC CARRY RESEARCH COMPLETE")
    print("=" * 80)
    for name, m in res["candidate_evaluations"].items():
        print(f"{name:50s}: Sharpe={m['sharpe']:.4f} | CAGR={m['cagr']*100:.2f}% | MaxDD={m['max_drawdown']*100:.2f}% | OOS Sharpe={m['walk_forward']['TRUE_OOS (20%)']['sharpe']:.4f}")
    d = res["deflated_sharpe_ratio"]
    print("-" * 80)
    print(f"Deflated Sharpe Ratio (DSR): p={d['dsr_p_value']:.4f} across {d['n_trials']} trials")
