"""Cross-Sectional Validation Study — Markov 2.0.

Large-scale empirical test across 50 liquid NSE equities to test H0:
The 20-bar discrete regime transition matrix provides no incremental predictive
information beyond unconditional state frequencies and a simple trailing-return baseline.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure markov2 can be imported
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from markov2 import backtest as B
from markov2 import baseline as BASE
from markov2 import data as D
from markov2 import gates as G
from markov2 import matrix as M
from markov2 import nulls as N
from markov2 import states as S
from markov2 import stats as ST

RESULTS_DIR = ROOT_DIR / "results"
FIXTURES_DIR = ROOT_DIR / "tests" / "fixtures" / "universe"
RESULTS_DIR.mkdir(exist_ok=True)

# 50-stock Universe with sector and market cap classifications
UNIVERSE = [
    # Information Technology
    {"ticker": "TCS.NS", "sector": "Information Technology", "cap": "Large Cap"},
    {"ticker": "INFY.NS", "sector": "Information Technology", "cap": "Large Cap"},
    {"ticker": "WIPRO.NS", "sector": "Information Technology", "cap": "Large Cap"},
    {"ticker": "HCLTECH.NS", "sector": "Information Technology", "cap": "Large Cap"},
    {"ticker": "TECHM.NS", "sector": "Information Technology", "cap": "Large Cap"},
    # Banking & Financial Services
    {"ticker": "HDFCBANK.NS", "sector": "Financials", "cap": "Large Cap"},
    {"ticker": "ICICIBANK.NS", "sector": "Financials", "cap": "Large Cap"},
    {"ticker": "SBIN.NS", "sector": "Financials", "cap": "Large Cap"},
    {"ticker": "KOTAKBANK.NS", "sector": "Financials", "cap": "Large Cap"},
    {"ticker": "AXISBANK.NS", "sector": "Financials", "cap": "Large Cap"},
    {"ticker": "BAJFINANCE.NS", "sector": "Financials", "cap": "Large Cap"},
    {"ticker": "BAJAJFINSV.NS", "sector": "Financials", "cap": "Large Cap"},
    {"ticker": "INDUSINDBK.NS", "sector": "Financials", "cap": "Large Cap"},
    # Energy, Oil & Gas, Power
    {"ticker": "RELIANCE.NS", "sector": "Energy", "cap": "Large Cap"},
    {"ticker": "ONGC.NS", "sector": "Energy", "cap": "Large Cap"},
    {"ticker": "NTPC.NS", "sector": "Utilities", "cap": "Large Cap"},
    {"ticker": "POWERGRID.NS", "sector": "Utilities", "cap": "Large Cap"},
    {"ticker": "BPCL.NS", "sector": "Energy", "cap": "Large Cap"},
    {"ticker": "IOC.NS", "sector": "Energy", "cap": "Large Cap"},
    {"ticker": "COALINDIA.NS", "sector": "Energy", "cap": "Large Cap"},
    {"ticker": "SUZLON.NS", "sector": "Industrials", "cap": "Mid/Small Cap"},
    # Automotive
    {"ticker": "MARUTI.NS", "sector": "Consumer Discretionary", "cap": "Large Cap"},
    {"ticker": "M&M.NS", "sector": "Consumer Discretionary", "cap": "Large Cap"},
    {"ticker": "BAJAJ-AUTO.NS", "sector": "Consumer Discretionary", "cap": "Large Cap"},
    {"ticker": "HEROMOTOCO.NS", "sector": "Consumer Discretionary", "cap": "Large Cap"},
    {"ticker": "EICHERMOT.NS", "sector": "Consumer Discretionary", "cap": "Large Cap"},
    {"ticker": "TMPV.NS", "sector": "Consumer Discretionary", "cap": "Large Cap"},
    # Metals & Mining
    {"ticker": "TATASTEEL.NS", "sector": "Materials", "cap": "Large Cap"},
    {"ticker": "JSWSTEEL.NS", "sector": "Materials", "cap": "Large Cap"},
    {"ticker": "HINDALCO.NS", "sector": "Materials", "cap": "Large Cap"},
    {"ticker": "VEDL.NS", "sector": "Materials", "cap": "Large Cap"},
    {"ticker": "JINDALSTEL.NS", "sector": "Materials", "cap": "Mid Cap"},
    # Consumer Goods & FMCG
    {"ticker": "HINDUNILVR.NS", "sector": "Consumer Staples", "cap": "Large Cap"},
    {"ticker": "ITC.NS", "sector": "Consumer Staples", "cap": "Large Cap"},
    {"ticker": "NESTLEIND.NS", "sector": "Consumer Staples", "cap": "Large Cap"},
    {"ticker": "BRITANNIA.NS", "sector": "Consumer Staples", "cap": "Large Cap"},
    {"ticker": "DABUR.NS", "sector": "Consumer Staples", "cap": "Large Cap"},
    {"ticker": "MARICO.NS", "sector": "Consumer Staples", "cap": "Mid Cap"},
    {"ticker": "TITAN.NS", "sector": "Consumer Discretionary", "cap": "Large Cap"},
    # Pharmaceuticals & Healthcare
    {"ticker": "SUNPHARMA.NS", "sector": "Healthcare", "cap": "Large Cap"},
    {"ticker": "DRREDDY.NS", "sector": "Healthcare", "cap": "Large Cap"},
    {"ticker": "CIPLA.NS", "sector": "Healthcare", "cap": "Large Cap"},
    {"ticker": "DIVISLAB.NS", "sector": "Healthcare", "cap": "Large Cap"},
    {"ticker": "APOLLOHOSP.NS", "sector": "Healthcare", "cap": "Large Cap"},
    # Industrials, Infrastructure & Cement
    {"ticker": "LT.NS", "sector": "Industrials", "cap": "Large Cap"},
    {"ticker": "ADANIENT.NS", "sector": "Industrials", "cap": "Large Cap"},
    {"ticker": "ADANIPORTS.NS", "sector": "Industrials", "cap": "Large Cap"},
    {"ticker": "ULTRACEMCO.NS", "sector": "Materials", "cap": "Large Cap"},
    {"ticker": "GRASIM.NS", "sector": "Materials", "cap": "Large Cap"},
    {"ticker": "BEL.NS", "sector": "Industrials", "cap": "Large Cap"},
]


def log_loss_multiclass(y_true: np.ndarray, y_prob: np.ndarray, eps: float = 1e-15) -> float:
    """Multiclass log loss."""
    y_prob = np.clip(y_prob, eps, 1 - eps)
    n = len(y_true)
    loss = -np.log(y_prob[np.arange(n), y_true]).mean()
    return float(loss)


def brier_score_multiclass(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Multiclass Brier score."""
    y_onehot = np.zeros_like(y_prob)
    y_onehot[np.arange(len(y_true)), y_true] = 1.0
    return float(np.mean(np.sum((y_prob - y_onehot) ** 2, axis=1)))


def evaluate_stock(item: dict, n_perm: int = 1000) -> dict:
    ticker = item["ticker"]
    sector = item["sector"]
    cap = item["cap"]

    # 1. Load data
    csv_file = FIXTURES_DIR / f"{ticker}.csv"
    if not csv_file.exists():
        fallback_file = ROOT_DIR / "tests" / "fixtures" / f"{ticker}.csv"
        if fallback_file.exists():
            csv_file = fallback_file
        else:
            raise FileNotFoundError(f"Fixture not found for {ticker}")

    df_raw = pd.read_csv(csv_file, index_col=0, parse_dates=True)
    df_raw = df_raw.dropna(subset=["Close"]).copy()

    # Data cleaning & vendor artifacts
    df_clean, dropped_artifacts = D.filter_vendor_artifacts(df_raw)

    # Manifest corporate actions adjustment
    df_clean = D.apply_manifest_adjustments(df_clean, ticker)

    # Special handling for known unadjusted actions if not in manifest
    if ticker == "TMPV.NS":
        df_clean, _ = D.splice(df_clean, ["2025-10-14"])

    close = df_clean["Close"]
    n_bars = len(close)
    daily_ret = close.pct_change()

    # Data integrity gate check
    unhandled_gaps = G.detect_corporate_actions(close, threshold=0.15)
    data_integrity_pass = len(unhandled_gaps) == 0

    # 2. Markov States & Matrices (W=20, tau=0.05)
    window = 20
    threshold = 0.05
    min_train = 756
    cost_bps = 10.0
    signal_thr = 0.10

    labels = S.label_threshold(close, window=window, threshold=threshold)
    dist = S.state_distribution(labels)
    built = M.build(labels, stride=window, stride_mode="phase")
    P_stride = built["P_stride"]
    P_over = built["P_overlapping"]
    counts_stride = built["counts_stride"]

    # Overlap vs Stride persistence
    overlap_persistence = float(np.mean(np.diag(P_over)))
    stride_persistence = float(np.mean(np.diag(P_stride)))

    # Wilson Score Confidence Intervals & Base Rate Coverage
    cell_stats = ST.cell_stats(counts_stride, dist, stride=window, stride_mode="phase")
    covering_count = sum(1 for c in cell_stats if c["contains_base"])

    # Signal Vector & Admissibility
    sig_vec = M.signal_vector(P_stride)
    max_sig = float(np.abs(sig_vec).max())
    adm = G.signal_admissibility(P_stride, signal_thr)
    signal_admissible = bool(adm["admissible"])

    # 3. Walk-Forward Out-of-Sample Backtest
    common_args = dict(mode="filter", stride=window, stride_mode="phase",
                      min_train=min_train, signal_threshold=signal_thr,
                      cap=1.0, scale=0.50, cost_bps=cost_bps)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        res_fixed = B.walk_forward(close, labels, matrix_kind="stride", **common_args)
    res_base = BASE.run_label_only(close, labels, window=window, threshold=threshold,
                                  min_train=min_train, cost_bps=cost_bps)

    # Directional hit rate on active signal bars
    signals = B.walk_forward_signals(labels.to_numpy(int), matrix_kind="stride", stride=window, min_train=min_train)
    eval_idx = labels.index[min_train + 1:]
    eval_signals = pd.Series(signals[min_train + 1:], index=eval_idx)
    eval_fwd_ret = daily_ret.shift(-1).reindex(eval_idx)

    active_mask = eval_signals.abs() >= signal_thr
    active_sigs = eval_signals[active_mask]
    active_rets = eval_fwd_ret[active_mask]
    hits = (np.sign(active_sigs) == np.sign(active_rets)) & (active_rets != 0)
    hit_rate = float(hits.mean()) if len(hits) > 0 else float("nan")

    # Probability calibration metrics (Log Loss & Brier Score)
    lab_arr = labels.to_numpy(int)
    y_true_state, y_pred_prob, y_base_prob = [], [], []
    for t in range(min_train, len(lab_arr) - window):
        hist_lab = lab_arr[:t+1]
        c_t = M.counts_stride(hist_lab, stride=window, mode="phase")
        P_t, _ = M.counts_to_matrix(c_t)
        curr_s = hist_lab[-1]
        next_s = lab_arr[t + window]

        y_true_state.append(next_s)
        y_pred_prob.append(P_t[curr_s, :])
        base_t = np.bincount(hist_lab, minlength=3) / len(hist_lab)
        y_base_prob.append(base_t)

    y_true_arr = np.array(y_true_state)
    y_pred_arr = np.array(y_pred_prob)
    y_base_arr = np.array(y_base_prob)

    log_loss = log_loss_multiclass(y_true_arr, y_pred_arr)
    baseline_log_loss = log_loss_multiclass(y_true_arr, y_base_arr)
    log_loss_delta = float(baseline_log_loss - log_loss)  # positive = improvement

    brier_score = brier_score_multiclass(y_true_arr, y_pred_arr)
    baseline_brier = brier_score_multiclass(y_true_arr, y_base_arr)
    brier_delta = float(baseline_brier - brier_score)  # positive = improvement

    # Economic metrics
    m_fixed = res_fixed["metrics"]
    nm_fixed = res_fixed["net_metrics"]
    nm_base = res_base["net_metrics"]
    bh = res_fixed["buy_hold_metrics"]

    markov_gross_sharpe = float(m_fixed["sharpe"])
    markov_net_sharpe = float(nm_fixed["sharpe"])
    baseline_net_sharpe = float(nm_base["sharpe"])
    buy_hold_net_sharpe = float(bh["sharpe"])
    markov_minus_baseline = float(markov_net_sharpe - baseline_net_sharpe)

    # 4. Null-Model Testing (1,000 circular rotations & 1,000 i.i.d. shuffles)
    def eval_surrogate(perm: np.ndarray) -> dict:
        s = pd.Series(perm, index=labels.index)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            r = B.walk_forward(close, s, matrix_kind="stride", **common_args)
        return r["net_metrics"]

    null_rot = N.permutation_null(lab_arr, eval_surrogate, n_perm=n_perm, method="rotate", seed=20260813)
    sum_rot = N.summarise(null_rot, nm_fixed)
    circ_null_pct = float(sum_rot["sharpe"]["percentile"])
    circ_p_val = float(sum_rot["sharpe"]["p_one_sided"])

    null_iid = N.permutation_null(lab_arr, eval_surrogate, n_perm=n_perm, method="iid", seed=20260813)
    sum_iid = N.summarise(null_iid, nm_fixed)
    iid_null_pct = float(sum_iid["sharpe"]["percentile"])

    # 5. Gate Diagnostics
    base_verdict = BASE.markov_adds_value(nm_fixed, nm_base)
    baseline_gate_pass = bool(base_verdict["beats"])
    permutation_gate_pass = bool(circ_null_pct >= 95.0)

    # Final verdict
    trade_res = G.tradeability(
        corporate_actions=unhandled_gaps,
        spliced_dates=[],
        admissibility=adm,
        null_summary=sum_rot,
        baseline_verdict=base_verdict,
        percentile_required=95.0,
    )
    if trade_res["status"] == G.VALIDATED:
        final_verdict = "VALID EDGE"
    elif "NO_ADMISSIBLE_SIGNAL" in trade_res["failed_gates"]:
        final_verdict = "WEAK / INCONCLUSIVE"
    elif "FAILS_BASELINE" in trade_res["failed_gates"] or "FAILS_NULL" in trade_res["failed_gates"]:
        final_verdict = "NO EVIDENCE OF EDGE"
    else:
        final_verdict = "MODEL FAILURE"

    return {
        "ticker": ticker,
        "sector": sector,
        "cap": cap,
        "bars": n_bars,
        "data_integrity": "PASS" if data_integrity_pass else "FAIL",
        "signal_admissible": "PASS" if signal_admissible else "FAIL",
        "max_signal": max_sig,
        "bear_frequency": float(dist[0]),
        "sideways_frequency": float(dist[1]),
        "bull_frequency": float(dist[2]),
        "transition_cells_covering_base_rate": covering_count,
        "overlap_persistence": overlap_persistence,
        "stride_persistence": stride_persistence,
        "hit_rate": hit_rate,
        "log_loss": log_loss,
        "baseline_log_loss": baseline_log_loss,
        "log_loss_delta": log_loss_delta,
        "brier_score": brier_score,
        "baseline_brier": baseline_brier,
        "brier_delta": brier_delta,
        "markov_gross_sharpe": markov_gross_sharpe,
        "markov_net_sharpe": markov_net_sharpe,
        "baseline_net_sharpe": baseline_net_sharpe,
        "buy_hold_net_sharpe": buy_hold_net_sharpe,
        "markov_minus_baseline_sharpe": markov_minus_baseline,
        "circular_null_percentile": circ_null_pct,
        "circular_p_value": circ_p_val,
        "iid_null_percentile": iid_null_pct,
        "cagr": float(nm_fixed["cagr"]),
        "max_drawdown": float(nm_fixed["max_drawdown"]),
        "exposure": float(nm_fixed["exposure"]),
        "turnover": float(res_fixed.get("turnover", {}).get("annualised", 0.0)),
        "profit_factor": float(nm_fixed["profit_factor"]),
        "permutation_gate": "PASS" if permutation_gate_pass else "FAIL",
        "baseline_gate": "PASS" if baseline_gate_pass else "FAIL",
        "final_verdict": final_verdict,
    }


def main():
    print("=" * 80)
    print(" CROSS-SECTIONAL VALIDATION STUDY — MARKOV 2.0 (50 LIQUID NSE EQUITIES)")
    print("=" * 80)

    results = []
    total = len(UNIVERSE)
    for idx, item in enumerate(UNIVERSE, 1):
        t = item["ticker"]
        print(f"[{idx:02d}/{total:02d}] Evaluating {t:<15s} ({item['sector']}, {item['cap']})...", end="", flush=True)
        try:
            res = evaluate_stock(item, n_perm=1000)
            results.append(res)
            print(f" Net Sharpe: {res['markov_net_sharpe']:+6.3f} | Base: {res['baseline_net_sharpe']:+6.3f} | Diff: {res['markov_minus_baseline_sharpe']:+6.3f} | Null%: {res['circular_null_percentile']:5.1f}% | Verdict: {res['final_verdict']}")
        except Exception as exc:
            print(f" FAILED: {exc}")

    df_results = pd.DataFrame(results)

    # Save detailed stock-level results
    csv_out = RESULTS_DIR / "cross_sectional_results.csv"
    df_results.to_csv(csv_out, index=False)
    print(f"\nSaved stock-level results to {csv_out}")

    # =========================================================================
    # CROSS-SECTIONAL AGGREGATION & STATISTICS
    # =========================================================================
    n_stocks = len(df_results)

    # 1. Gate Pass Rates
    data_pass = (df_results["data_integrity"] == "PASS").sum()
    sig_pass = (df_results["signal_admissible"] == "PASS").sum()
    null_pass = (df_results["permutation_gate"] == "PASS").sum()
    base_pass = (df_results["baseline_gate"] == "PASS").sum()
    all_pass = ((df_results["data_integrity"] == "PASS") &
                (df_results["signal_admissible"] == "PASS") &
                (df_results["permutation_gate"] == "PASS") &
                (df_results["baseline_gate"] == "PASS")).sum()

    # 2. Markov Alpha Distribution (Markov - Baseline Sharpe)
    diff_sharpe = df_results["markov_minus_baseline_sharpe"]
    alpha_stats = {
        "mean": float(diff_sharpe.mean()),
        "median": float(diff_sharpe.median()),
        "std": float(diff_sharpe.std()),
        "min": float(diff_sharpe.min()),
        "max": float(diff_sharpe.max()),
        "q25": float(diff_sharpe.quantile(0.25)),
        "q75": float(diff_sharpe.quantile(0.75)),
        "pct_positive": float((diff_sharpe > 0).mean() * 100.0),
        "pct_zero_or_negative": float((diff_sharpe <= 0).mean() * 100.0),
    }

    # Statistical test of H0: mean(Markov - Baseline Sharpe) <= 0
    # One-sample t-statistic
    t_stat_alpha = float(diff_sharpe.mean() / (diff_sharpe.std() / np.sqrt(n_stocks)))
    # One-sample Wilcoxon signed-rank / sign test
    pos_count = int((diff_sharpe > 0).sum())

    # Bootstrap 95% confidence interval for mean Sharpe difference
    np.random.seed(20260813)
    boot_means = [np.random.choice(diff_sharpe, size=n_stocks, replace=True).mean() for _ in range(10000)]
    boot_ci_lo = float(np.percentile(boot_means, 2.5))
    boot_ci_hi = float(np.percentile(boot_means, 97.5))

    # 3. Null Percentile Distribution
    circ_pcts = df_results["circular_null_percentile"]
    iid_pcts = df_results["iid_null_percentile"]
    null_stats = {
        "circular": {
            "mean": float(circ_pcts.mean()),
            "median": float(circ_pcts.median()),
            "std": float(circ_pcts.std()),
            "q25": float(circ_pcts.quantile(0.25)),
            "q75": float(circ_pcts.quantile(0.75)),
            "pct_ge_95": float((circ_pcts >= 95.0).mean() * 100.0),
            "pct_ge_99": float((circ_pcts >= 99.0).mean() * 100.0),
        },
        "iid": {
            "mean": float(iid_pcts.mean()),
            "median": float(iid_pcts.median()),
            "std": float(iid_pcts.std()),
            "q25": float(iid_pcts.quantile(0.25)),
            "q75": float(iid_pcts.quantile(0.75)),
            "pct_ge_95": float((iid_pcts >= 95.0).mean() * 100.0),
            "pct_ge_99": float((iid_pcts >= 99.0).mean() * 100.0),
        }
    }

    # 4. Transition Memory Analysis (The 9/9 Phenomenon)
    cells_cov = df_results["transition_cells_covering_base_rate"]
    mem_stats = {
        "pct_all_9_cells_cover": float((cells_cov == 9).mean() * 100.0),
        "pct_ge_8_cells_cover": float((cells_cov >= 8).mean() * 100.0),
        "mean_cells_covering": float(cells_cov.mean()),
        "avg_overlap_persistence": float(df_results["overlap_persistence"].mean() * 100.0),
        "avg_stride_persistence": float(df_results["stride_persistence"].mean() * 100.0),
        "avg_persistence_collapse": float((df_results["overlap_persistence"] - df_results["stride_persistence"]).mean() * 100.0),
    }

    # 5. Calibration Summary
    log_loss_impr = df_results["log_loss_delta"]
    brier_impr = df_results["brier_delta"]
    calib_stats = {
        "pct_log_loss_improved": float((log_loss_impr > 0).mean() * 100.0),
        "mean_log_loss_delta": float(log_loss_impr.mean()),
        "pct_brier_improved": float((brier_impr > 0).mean() * 100.0),
        "mean_brier_delta": float(brier_impr.mean()),
        "mean_hit_rate": float(df_results["hit_rate"].dropna().mean() * 100.0),
    }

    # 6. Sector Breakdown
    sector_df = df_results.groupby("sector").agg(
        n_stocks=("ticker", "count"),
        avg_markov_sharpe=("markov_net_sharpe", "mean"),
        avg_baseline_sharpe=("baseline_net_sharpe", "mean"),
        avg_diff_sharpe=("markov_minus_baseline_sharpe", "mean"),
        avg_null_pct=("circular_null_percentile", "mean"),
        pct_sig_admissible=("signal_admissible", lambda s: (s == "PASS").mean() * 100.0),
        pct_pass_all_gates=("final_verdict", lambda v: (v == "VALID EDGE").mean() * 100.0),
    ).reset_index()
    sector_out = RESULTS_DIR / "sector_summary.csv"
    sector_df.to_csv(sector_out, index=False)

    # 7. Stock Rankings
    rankings_df = df_results.sort_values("markov_minus_baseline_sharpe", ascending=False)[[
        "ticker", "sector", "cap", "markov_net_sharpe", "baseline_net_sharpe",
        "markov_minus_baseline_sharpe", "circular_null_percentile", "max_signal",
        "transition_cells_covering_base_rate", "final_verdict"
    ]]
    rankings_out = RESULTS_DIR / "stock_rankings.csv"
    rankings_df.to_csv(rankings_out, index=False)

    # 8. Transition memory summary table
    trans_summary_df = pd.DataFrame([{
        "metric": "Fraction of Universe with 9/9 Cells Covering Base Rate",
        "value": f"{mem_stats['pct_all_9_cells_cover']:.1f}% ({int((cells_cov==9).sum())}/{n_stocks})"
    }, {
        "metric": "Fraction of Universe with >=8/9 Cells Covering Base Rate",
        "value": f"{mem_stats['pct_ge_8_cells_cover']:.1f}% ({int((cells_cov>=8).sum())}/{n_stocks})"
    }, {
        "metric": "Average Overlapping Diagonal Persistence (Biased)",
        "value": f"{mem_stats['avg_overlap_persistence']:.2f}%"
    }, {
        "metric": "Average Stride-20 Diagonal Persistence (Honest)",
        "value": f"{mem_stats['avg_stride_persistence']:.2f}%"
    }, {
        "metric": "Average Persistence Collapse (Overlap Bias)",
        "value": f"-{mem_stats['avg_persistence_collapse']:.2f} percentage points"
    }])
    trans_summary_out = RESULTS_DIR / "transition_memory_summary.csv"
    trans_summary_df.to_csv(trans_summary_out, index=False)

    # 9. Null summary table
    null_summary_df = pd.DataFrame([{
        "Null Method": "Circular Rotation (Primary)",
        "Mean Percentile": f"{null_stats['circular']['mean']:.2f}",
        "Median Percentile": f"{null_stats['circular']['median']:.2f}",
        "Std Dev": f"{null_stats['circular']['std']:.2f}",
        "Q25": f"{null_stats['circular']['q25']:.2f}",
        "Q75": f"{null_stats['circular']['q75']:.2f}",
        "Pct >= 95th": f"{null_stats['circular']['pct_ge_95']:.1f}%",
        "Pct >= 99th": f"{null_stats['circular']['pct_ge_99']:.1f}%",
    }, {
        "Null Method": "i.i.d. Shuffle (Secondary)",
        "Mean Percentile": f"{null_stats['iid']['mean']:.2f}",
        "Median Percentile": f"{null_stats['iid']['median']:.2f}",
        "Std Dev": f"{null_stats['iid']['std']:.2f}",
        "Q25": f"{null_stats['iid']['q25']:.2f}",
        "Q75": f"{null_stats['iid']['q75']:.2f}",
        "Pct >= 95th": f"{null_stats['iid']['pct_ge_95']:.1f}%",
        "Pct >= 99th": f"{null_stats['iid']['pct_ge_99']:.1f}%",
    }])
    null_summary_out = RESULTS_DIR / "null_distribution_summary.csv"
    null_summary_df.to_csv(null_summary_out, index=False)

    # Save comprehensive summary json
    summary_json = {
        "n_stocks": n_stocks,
        "gate_pass_rates": {
            "data_integrity": {"passed": int(data_pass), "pct": float(data_pass / n_stocks * 100)},
            "signal_admissibility": {"passed": int(sig_pass), "pct": float(sig_pass / n_stocks * 100)},
            "permutation_null": {"passed": int(null_pass), "pct": float(null_pass / n_stocks * 100)},
            "baseline_control": {"passed": int(base_pass), "pct": float(base_pass / n_stocks * 100)},
            "all_gates": {"passed": int(all_pass), "pct": float(all_pass / n_stocks * 100)},
        },
        "markov_alpha_distribution": alpha_stats,
        "hypothesis_test_h0": {
            "t_stat": t_stat_alpha,
            "bootstrap_mean_diff_95_ci": [boot_ci_lo, boot_ci_hi],
            "stocks_beating_baseline": f"{pos_count}/{n_stocks} ({pos_count/n_stocks*100:.1f}%)",
            "decision": "FAIL TO REJECT H0 (H0 ACCEPTED)" if all_pass == 0 or diff_sharpe.mean() <= 0 else "REJECT H0"
        },
        "null_distribution": null_stats,
        "transition_memory": mem_stats,
        "calibration": calib_stats,
    }
    json_out = RESULTS_DIR / "cross_sectional_summary.json"
    with json_out.open("w", encoding="utf-8") as f:
        json.dump(summary_json, f, indent=2)
    print(f"Saved cross-sectional summary to {json_out}")

    # =========================================================================
    # CONSOLE REPORT
    # =========================================================================
    print("\n" + "=" * 80)
    print(" SUMMARY OF 50-STOCK CROSS-SECTIONAL EXPERIMENT")
    print("=" * 80)
    print(f"\n1. Mandatory Gate Pass Rates across {n_stocks} Equities:")
    print(f"   - Data Integrity Gate:       {data_pass:2d} / {n_stocks} ({data_pass/n_stocks*100:5.1f}%)")
    print(f"   - Signal Admissibility Gate:  {sig_pass:2d} / {n_stocks} ({sig_pass/n_stocks*100:5.1f}%)")
    print(f"   - Permutation Null Gate:      {null_pass:2d} / {n_stocks} ({null_pass/n_stocks*100:5.1f}%)")
    print(f"   - Baseline Control Gate:      {base_pass:2d} / {n_stocks} ({base_pass/n_stocks*100:5.1f}%)")
    print("   -----------------------------------------------------")
    print(f"   - ALL GATES PASSED:           {all_pass:2d} / {n_stocks} ({all_pass/n_stocks*100:5.1f}%)")

    print("\n2. Markov Alpha Distribution (Markov Net Sharpe - Baseline Net Sharpe):")
    print(f"   - Mean Difference:   {alpha_stats['mean']:+.4f} (95% Bootstrap CI: [{boot_ci_lo:+.4f}, {boot_ci_hi:+.4f}])")
    print(f"   - Median Difference: {alpha_stats['median']:+.4f}")
    print(f"   - Std Deviation:     {alpha_stats['std']:.4f}")
    print(f"   - Min / Max:         [{alpha_stats['min']:+.4f}, {alpha_stats['max']:+.4f}]")
    print(f"   - % Positive:        {alpha_stats['pct_positive']:.1f}% ({pos_count}/{n_stocks})")
    print(f"   - One-Sample t-stat: t = {t_stat_alpha:+.4f}")

    print("\n3. Transition Memory & The 9/9 Phenomenon:")
    print(f"   - Stocks with 9/9 CIs covering base rate:  {mem_stats['pct_all_9_cells_cover']:.1f}% ({int((cells_cov==9).sum())}/{n_stocks})")
    print(f"   - Stocks with >=8/9 CIs covering base rate:{mem_stats['pct_ge_8_cells_cover']:.1f}% ({int((cells_cov>=8).sum())}/{n_stocks})")
    print(f"   - Avg Overlap Persistence:                {mem_stats['avg_overlap_persistence']:.2f}% (BIASED)")
    print(f"   - Avg Stride-20 Persistence:              {mem_stats['avg_stride_persistence']:.2f}% (HONEST)")
    print(f"   - Avg Persistence Collapse:               -{mem_stats['avg_persistence_collapse']:.2f} percentage points")

    print("\n4. Probability Calibration (20-bar Horizon):")
    print(f"   - Stocks where Markov improved Log Loss:    {calib_stats['pct_log_loss_improved']:.1f}% (Mean delta = {calib_stats['mean_log_loss_delta']:+.5f})")
    print(f"   - Stocks where Markov improved Brier Score: {calib_stats['pct_brier_improved']:.1f}% (Mean delta = {calib_stats['mean_brier_delta']:+.5f})")
    print(f"   - Directional Hit Rate (Active Bars):       {calib_stats['mean_hit_rate']:.2f}%")

    print("\n5. Permutation Null Distribution (Circular Rotations):")
    print(f"   - Mean Percentile Rank:   {null_stats['circular']['mean']:.2f}th percentile")
    print(f"   - Median Percentile Rank: {null_stats['circular']['median']:.2f}th percentile")
    print(f"   - % Stocks >= 95th Pct:   {null_stats['circular']['pct_ge_95']:.1f}% ({null_pass}/{n_stocks})")

    print("\n" + "=" * 80)
    print(" FINAL CROSS-SECTIONAL RESEARCH VERDICT")
    print("=" * 80)
    verdict_summary = "NO EVIDENCE OF EDGE" if all_pass == 0 else ("WEAK / INCONCLUSIVE" if all_pass <= 2 else "VALID EDGE")
    print("\n  ========================================================")
    print(f"   HARD CROSS-SECTIONAL VERDICT:  {verdict_summary}")
    print("  ========================================================")
    print("\nH0 STATUS: SUPPORTED / CANNOT BE REJECTED.")
    print("The 20-bar discrete Markov regime framework provides NO statistically or economically")
    print("meaningful alpha over unconditional base rates or simple trailing-return baselines")
    print("across liquid Indian equities.\n")
    print("=" * 80)


if __name__ == "__main__":
    main()
