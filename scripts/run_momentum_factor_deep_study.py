"""Deep Momentum Factor Study: Signal Formulations, Volatility Estimators, Hysteresis, Rebalance Frequencies, Short Decomposition, and Deflated Sharpe Ratio."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import math
import statistics

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
    """Computes Bailey & Lopez de Prado (2014) Deflated Sharpe Ratio."""
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


def calculate_volatility(
    rets_window: pd.DataFrame,
    vol_mode: str = "ROLLING_60D",  # "ROLLING_60D", "EWMA_94", "DOWNSIDE_SEMI"
) -> pd.Series:
    if vol_mode == "EWMA_94":
        # EWMA with lambda = 0.94
        span = int(2.0 / (1.0 - 0.94) - 1.0)  # span ~ 32
        ewma_var = (rets_window**2).ewm(span=span, adjust=False).mean().iloc[-1]
        vols = np.sqrt(ewma_var * 252.0)
    elif vol_mode == "DOWNSIDE_SEMI":
        # Downside semi-volatility (variance of negative returns only)
        downside_rets = rets_window.copy()
        downside_rets[downside_rets > 0] = 0.0
        vols = np.sqrt((downside_rets**2).mean() * 252.0)
    else:
        vols = rets_window.std(ddof=1) * np.sqrt(252.0)

    return vols.replace(0, np.nan).fillna(vols.mean()).fillna(0.15)


def run_momentum_simulation(
    df_close: pd.DataFrame,
    mom_mode: str = "MOM_126_RAW",  # "MOM_126_RAW", "MOM_SKIP_6_1", "MOM_SKIP_12_1", "MOM_RISK_ADJUSTED", "MOM_TIME_SERIES", "MOM_MULTI_HORIZON"
    vol_mode: str = "ROLLING_60D",  # "ROLLING_60D", "EWMA_94", "DOWNSIDE_SEMI"
    hysteresis_mode: str = "CONTROL",  # "NONE", "NARROW", "CONTROL", "WIDE"
    rebalance_freq: int = 21,
    long_short_mode: str = "LONG_SHORT",  # "LONG_SHORT", "LONG_ONLY", "SHORT_ONLY"
    cost_bps: float = 10.0,
    borrow_bps: float = 25.0,
    start_idx: int = 756,
) -> dict:
    rets = df_close.pct_change().fillna(0.0)
    n_bars, n_assets = df_close.shape
    rebalance_dates = [df_close.index[i] for i in range(start_idx, n_bars) if (i - start_idx) % rebalance_freq == 0]

    # Precalculate price series lookbacks
    p_now = df_close
    p_21 = df_close.shift(21)
    p_63 = df_close.shift(63)
    p_126 = df_close.shift(126)
    p_252 = df_close.shift(252)
    sma_200 = df_close.rolling(200).mean()

    target_w_df = pd.DataFrame(0.0, index=df_close.index, columns=df_close.columns)
    prev_long, prev_short = [], []

    for i in range(start_idx, n_bars):
        if (i - start_idx) % rebalance_freq == 0:
            past_rets = rets.iloc[max(0, i - 60):i]
            vols = calculate_volatility(past_rets, vol_mode=vol_mode)

            # Signal generation
            if mom_mode == "MOM_SKIP_6_1":
                sig_raw = (p_21.iloc[i] / p_126.iloc[i]) - 1.0
            elif mom_mode == "MOM_SKIP_12_1":
                sig_raw = (p_21.iloc[i] / p_252.iloc[i]) - 1.0
            elif mom_mode == "MOM_RISK_ADJUSTED":
                raw_m = (p_now.iloc[i] / p_126.iloc[i]) - 1.0
                sig_raw = raw_m / (vols + 1e-8)
            elif mom_mode == "MOM_MULTI_HORIZON":
                m21 = (p_now.iloc[i] / p_21.iloc[i]) - 1.0
                m63 = (p_now.iloc[i] / p_63.iloc[i]) - 1.0
                m126 = (p_now.iloc[i] / p_126.iloc[i]) - 1.0
                m252 = (p_now.iloc[i] / p_252.iloc[i]) - 1.0
                sig_raw = 0.40 * m126 + 0.30 * m63 + 0.20 * m252 + 0.10 * m21
            else:
                sig_raw = (p_now.iloc[i] / p_126.iloc[i]) - 1.0

            sig_clean = sig_raw.dropna()
            z_sig = (sig_clean - sig_clean.mean()) / (sig_clean.std() + 1e-8) if len(sig_clean) >= 4 else pd.Series(0.0, index=df_close.columns)

            sorted_sigs = z_sig.sort_values(ascending=False)
            rank_map = {asset: r + 1 for r, (asset, _) in enumerate(sorted_sigs.items())}

            # Hysteresis buffering
            if hysteresis_mode == "NONE":
                long_selected = list(sorted_sigs.index[:3])
                short_selected = list(sorted_sigs.index[-3:])
            elif hysteresis_mode == "NARROW":
                # Retain Long if rank <= 4, Short if rank >= 9
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
                # Retain Long if rank <= 8, Short if rank >= 5
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
                # CONTROL: Retain Long if rank <= 6, Short if rank >= 7
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

            if mom_mode == "MOM_TIME_SERIES":
                # Filter long by SMA200 trend filter
                long_selected = [a for a in long_selected if p_now[a].iloc[i] >= sma_200[a].iloc[i]]
                short_selected = [a for a in short_selected if p_now[a].iloc[i] < sma_200[a].iloc[i]]

            prev_long = long_selected
            prev_short = short_selected

            row_target = pd.Series(0.0, index=df_close.columns)

            if long_short_mode in ("LONG_SHORT", "LONG_ONLY") and long_selected:
                inv_v_long = 1.0 / (vols[long_selected] + 1e-8)
                w_long = inv_v_long / inv_v_long.sum()
                for a, w in w_long.items():
                    row_target[a] = float(w)

            if long_short_mode in ("LONG_SHORT", "SHORT_ONLY") and short_selected:
                inv_v_short = 1.0 / (vols[short_selected] + 1e-8)
                w_short = inv_v_short / inv_v_short.sum()
                for a, w in w_short.items():
                    row_target[a] = -float(w)

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


def run_full_study() -> dict:
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

    # 1. Momentum Signal Variations
    mom_signal_results = {}
    for m_mode in [
        "MOM_126_RAW",
        "MOM_SKIP_6_1",
        "MOM_SKIP_12_1",
        "MOM_RISK_ADJUSTED",
        "MOM_TIME_SERIES",
        "MOM_MULTI_HORIZON",
    ]:
        res = run_momentum_simulation(df_close, mom_mode=m_mode)
        mom_signal_results[m_mode] = {
            "sharpe": float(res["sharpe"]),
            "cagr": float(res["cagr"]),
            "volatility": float(res["annualized_volatility"]),
            "max_drawdown": float(res["max_drawdown"]),
            "sortino": float(res["sortino"]),
            "turnover": float(res["annualized_turnover"]),
            "walk_forward": eval_walk_forward(res["returns"]),
        }

    # 2. Volatility Estimator Comparison
    vol_results = {}
    for v_mode in ["ROLLING_60D", "EWMA_94", "DOWNSIDE_SEMI"]:
        res = run_momentum_simulation(df_close, vol_mode=v_mode)
        vol_results[v_mode] = {
            "sharpe": float(res["sharpe"]),
            "cagr": float(res["cagr"]),
            "max_drawdown": float(res["max_drawdown"]),
            "turnover": float(res["annualized_turnover"]),
            "walk_forward": eval_walk_forward(res["returns"]),
        }

    # 3. Rank Hysteresis Stress Test
    hyst_results = {}
    for h_mode in ["NONE", "NARROW", "CONTROL", "WIDE"]:
        res = run_momentum_simulation(df_close, hysteresis_mode=h_mode)
        hyst_results[h_mode] = {
            "sharpe": float(res["sharpe"]),
            "cagr": float(res["cagr"]),
            "max_drawdown": float(res["max_drawdown"]),
            "turnover": float(res["annualized_turnover"]),
            "walk_forward": eval_walk_forward(res["returns"]),
        }

    # 4. Rebalance Frequency Stress Test
    reb_results = {}
    for reb_f, name in [(5, "Weekly_5d"), (10, "BiWeekly_10d"), (21, "Monthly_21d"), (42, "BiMonthly_42d")]:
        res = run_momentum_simulation(df_close, rebalance_freq=reb_f)
        reb_results[name] = {
            "rebalance_freq": reb_f,
            "sharpe": float(res["sharpe"]),
            "cagr": float(res["cagr"]),
            "max_drawdown": float(res["max_drawdown"]),
            "turnover": float(res["annualized_turnover"]),
            "walk_forward": eval_walk_forward(res["returns"]),
        }

    # 5. Long / Short Asymmetry & Borrow Cost
    ls_results = {}
    for ls_mode in ["LONG_SHORT", "LONG_ONLY", "SHORT_ONLY"]:
        res = run_momentum_simulation(df_close, long_short_mode=ls_mode)
        ls_results[ls_mode] = {
            "sharpe": float(res["sharpe"]),
            "cagr": float(res["cagr"]),
            "volatility": float(res["annualized_volatility"]),
            "max_drawdown": float(res["max_drawdown"]),
            "turnover": float(res["annualized_turnover"]),
            "walk_forward": eval_walk_forward(res["returns"]),
        }

    borrow_cost_sweep = {}
    for b_bps in [0.0, 25.0, 50.0, 100.0, 200.0]:
        res = run_momentum_simulation(df_close, borrow_bps=b_bps)
        borrow_cost_sweep[f"{int(b_bps)} bps/yr"] = {
            "sharpe": float(res["sharpe"]),
            "cagr": float(res["cagr"]),
            "max_drawdown": float(res["max_drawdown"]),
        }

    # 6. Deflated Sharpe Ratio (DSR)
    all_sharpes = [v["sharpe"] for v in mom_signal_results.values()] + [v["sharpe"] for v in hyst_results.values()]
    var_trials = float(np.var(all_sharpes, ddof=1)) if len(all_sharpes) > 1 else 0.05
    cand001_ret = mom_signal_results["MOM_126_RAW"]
    daily_r = run_momentum_simulation(df_close)["returns"].to_numpy()
    skew_val = float(pd.Series(daily_r).skew())
    kurt_val = float(pd.Series(daily_r).kurtosis())
    n_obs = len(daily_r)

    dsr = compute_deflated_sharpe_ratio(
        observed_sharpe=float(cand001_ret["sharpe"]),
        n_trials=len(all_sharpes) + 15,
        var_trials=var_trials,
        skewness=skew_val,
        kurtosis=kurt_val,
        n_observations=n_obs,
    )

    study_payload = {
        "momentum_signal_variations": mom_signal_results,
        "volatility_estimator_comparison": vol_results,
        "rank_hysteresis_stress_test": hyst_results,
        "rebalance_frequency_stress_test": reb_results,
        "long_short_asymmetry": ls_results,
        "borrow_cost_sensitivity": borrow_cost_sweep,
        "deflated_sharpe_ratio": {
            "observed_annualized_sharpe": float(cand001_ret["sharpe"]),
            "n_trials": len(all_sharpes) + 15,
            "variance_of_trials": var_trials,
            "skewness": skew_val,
            "kurtosis": kurt_val,
            "n_observations": n_obs,
            "deflated_sharpe_ratio_p_value": dsr,
        },
    }

    out_file = Path(__file__).resolve().parent.parent / "results" / "momentum_factor_deep_study_results.json"
    with open(out_file, "w") as f:
        json.dump(study_payload, f, indent=2)

    return study_payload


if __name__ == "__main__":
    res = run_full_study()
    print("=" * 80)
    print(" MOMENTUM FACTOR DEEP STUDY COMPLETE")
    print("=" * 80)
    for k, v in res["momentum_signal_variations"].items():
        print(f"Signal {k:20s}: Sharpe={v['sharpe']:.4f} | CAGR={v['cagr']*100:.2f}% | MaxDD={v['max_drawdown']*100:.2f}% | OOS Sharpe={v['walk_forward']['TRUE_OOS (20%)']['sharpe']:.4f}")
    print("-" * 80)
    for k, v in res["rank_hysteresis_stress_test"].items():
        print(f"Hysteresis {k:15s}: Sharpe={v['sharpe']:.4f} | Turnover={v['turnover']*100:.1f}%/yr | MaxDD={v['max_drawdown']*100:.2f}%")
    print("-" * 80)
    for k, v in res["long_short_asymmetry"].items():
        print(f"Sleeve {k:15s}: Sharpe={v['sharpe']:.4f} | CAGR={v['cagr']*100:.2f}% | MaxDD={v['max_drawdown']*100:.2f}%")
    print("-" * 80)
    d = res["deflated_sharpe_ratio"]
    print(f"Deflated Sharpe Ratio: DSR={d['deflated_sharpe_ratio_p_value']:.4f} across {d['n_trials']} trials (Skew={d['skewness']:.2f}, Kurt={d['kurtosis']:.2f})")
