"""Markov 2.0 CLI.

    python -m markov2.run --ticker TCS.NS
    python -m markov2.run --ticker TMPV.NS --splice 2025-10-14

The report is split into DATA / REGIME / STRATEGY / NULL. A result is only
described as tradeable when every gate in `gates.py` passes; otherwise it is
still printed in full and labelled RESEARCH_ONLY.
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from . import matrix as M
from . import report as R
from . import verify as V
from .backtest import walk_forward
from .baseline import LABEL_ONLY_NAME, markov_adds_value, run_label_only
from .data import fetch
from .gates import (
    CORP_ACTION_THRESHOLD,
    NULL_PERCENTILE_REQUIRED,
    detect_corporate_actions,
    signal_admissibility,
    tradeability,
)
from .nulls import DEFAULT_N_PERM, PRIMARY_NULL, permutation_null, summarise
from .states import N_STATES, STATE_NAMES, label_threshold, state_distribution, window_return
from .stats import cell_stats

OUT_DIR = Path(__file__).resolve().parent.parent / "output"
DEFAULT_COST_BPS = 10.0


def _row(name: str, res: dict) -> dict:
    m, nm = res["metrics"], res.get("net_metrics", res["metrics"])
    return {
        "name": name,
        "gross_sharpe": m["sharpe"],
        "net_sharpe": nm["sharpe"],
        "cagr": nm["cagr"],
        "max_drawdown": nm["max_drawdown"],
        "profit_factor": nm["profit_factor"],
        "exposure": nm["exposure"],
        "turnover_annualised": res.get("turnover", {}).get("annualised", float("nan")),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="markov2")
    p.add_argument("--ticker", default="SPY")
    p.add_argument("--years", type=int, default=10)
    p.add_argument("--window", type=int, default=20)
    p.add_argument("--threshold", type=float, default=0.05)
    p.add_argument("--stride", type=int, default=None, help="defaults to --window")
    p.add_argument("--stride-mode", choices=("phase", "single"), default="phase")
    p.add_argument("--mode", choices=("filter", "standalone"), default="filter",
                   help="standalone is DEPRECATED and not a recommended trading mode")
    p.add_argument("--signal-threshold", type=float, default=0.10)
    p.add_argument("--cap", type=float, default=1.0)
    p.add_argument("--scale", type=float, default=0.50)
    p.add_argument("--min-train", type=int, default=756)
    p.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS,
                   help=f"per unit |position change| (default {DEFAULT_COST_BPS}; 0 = legacy)")
    p.add_argument("--permutations", type=int, default=DEFAULT_N_PERM)
    p.add_argument("--null-method", choices=("rotate", "iid"), default=PRIMARY_NULL,
                   help="rotate is primary; iid is anti-conservative and never a gate")
    p.add_argument("--no-null", action="store_true", help="skip the null (research only)")
    p.add_argument("--corp-action-threshold", type=float, default=CORP_ACTION_THRESHOLD)
    p.add_argument("--splice", default="", help="comma-separated dates to back-adjust")
    p.add_argument("--csv", default="", help="load OHLCV from a CSV instead of yfinance")
    p.add_argument("--enhanced", action="store_true")
    p.add_argument("--hmm", action="store_true")
    p.add_argument("--no-plot", action="store_true")
    p.add_argument("--macro", action="store_true", help="Run multi-asset macro strategy with Markov gating")
    p.add_argument("--cointegration", action="store_true", help="Run cointegration subsystem screening")
    p.add_argument("--benchmark-cointegration", action="store_true", help="Run condition-number & cointegration benchmark suite")
    args = p.parse_args(argv)
    stride = args.stride if args.stride is not None else args.window

    print(R.header(f"MARKOV 2.0 - {args.ticker}  |  window={args.window} "
                   f"thr=+/-{args.threshold*100:.0f}%  |  mode={args.mode.upper()}"))

    if args.mode == "standalone":
        print("\n  " + "!" * 72)
        print("  DEPRECATED: standalone mode is not a recommended trading mode.")
        print("  Permutation testing placed it at the 1st percentile of the null on")
        print("  TCS.NS (Sharpe 0.024) and at -0.798 on TMPV.NS - worse than randomly")
        print("  rotated labels. It is retained for reproducibility and research only.")
        print("  " + "!" * 72)

    if args.macro:
        from .macro import walk_forward_macro
        from .universe_data import fetch_universe, get_tickers
        print(R.header("MARKOV 2.0 MACRO STRATEGY"))
        tickers = get_tickers()
        print(f"Fetching data for {len(tickers)} assets...")
        df_close = fetch_universe(tickers, years=args.years)

        print("\nRunning Baseline Macro Strategy (No Markov Gating)...")
        res_base = walk_forward_macro(
            df_close, window=args.window, threshold=args.threshold,
            matrix_kind="stride", stride=stride, stride_mode=args.stride_mode,
            min_train=args.min_train, signal_threshold=args.signal_threshold,
            cost_bps=args.cost_bps, apply_markov_gate=False
        )

        print("Running Markov-Gated Macro Strategy...")
        res_markov = walk_forward_macro(
            df_close, window=args.window, threshold=args.threshold,
            matrix_kind="stride", stride=stride, stride_mode=args.stride_mode,
            min_train=args.min_train, signal_threshold=args.signal_threshold,
            cost_bps=args.cost_bps, apply_markov_gate=True
        )

        rows = [
            _row("Baseline Macro", res_base),
            _row("Markov-Gated Macro", res_markov),
        ]
        verdict = markov_adds_value(res_markov["net_metrics"], res_base["net_metrics"])
        print(R.render_strategy(rows, args.cost_bps, verdict))

        if not args.no_plot:
            try:
                from .plot import plot_equity
                OUT_DIR.mkdir(exist_ok=True)
                out = OUT_DIR / "macro_strategy_equity.png"
                plot_equity({
                    "Baseline Macro": res_base["net_returns"],
                    "Markov-Gated Macro": res_markov["net_returns"],
                }, out, f"Macro Strategy - net of {args.cost_bps:.0f}bps")
                print(f"\n  equity curve -> {out}")
            except Exception as exc:
                print(f"\n  ! plot skipped: {exc}")

    if args.benchmark_cointegration:
        from .cointegration.benchmark import (
            benchmark_condition_number_estimator,
            benchmark_precision_scaling,
            benchmark_scaling,
            run_synthetic_validation,
        )
        print(R.header("COINTEGRATION BENCHMARK & SYNTHETIC VALIDATION SUITE"))

        print("\n1. Synthetic Test Cases (Cases A-E):")
        df_syn = run_synthetic_validation()
        print(df_syn.to_string(index=False))

        print("\n2. Condition Number Estimator Benchmark (Exact SVD vs Fast Power Iteration):")
        cond_bench = benchmark_condition_number_estimator(matrices_count=20)
        for k, v in cond_bench.items():
            print(f"  {k:<30s}: {v}")

        print("\n3. Precision Scaling Experiment (Epsilon Sensitivity):")
        df_prec = benchmark_precision_scaling()
        print(df_prec.to_string(index=False))

        print("\n4. Empirical Scaling Benchmark (N vs d):")
        df_scale = benchmark_scaling(N_list=[1000, 2000, 5000], d_list=[2, 5, 10])
        print(df_scale.to_string(index=False))
        print(f"\n  Empirical Scaling Fit: {df_scale.attrs.get('empirical_scaling', 'N/A')}")
        return 0

    if args.cointegration:
        from .cointegration.integration import run_cointegration_markov_hybrid
        from .cointegration.pipeline import scan_cointegrated_pairs
        from .universe_data import fetch_universe, get_tickers
        print(R.header("MARKOV 2.0 COINTEGRATION SUBSYSTEM"))

        tickers = get_tickers()
        print(f"Fetching data for {len(tickers)} assets...")
        df_close = fetch_universe(tickers, years=args.years)

        print("\nScanning for cointegrated pairs (Condition threshold kappa >= 10.0)...")
        pairs = scan_cointegrated_pairs(df_close, kappa_threshold=10.0)
        print(f"Found {len(pairs)} cointegrated pairs:")
        for p in pairs[:5]:
            print(f"  Pair {p['asset_y']}/{p['asset_x']:<8s} | stat: {p['test_statistic']:+.4f} | "
                  f"kappa: {p['condition_number']:6.1f} | hedge ratio: {p['hedge_ratio']:+.4f}")

        print("\nRunning Cointegration + Markov 2.0 Hybrid Backtest...")
        hyb_res = run_cointegration_markov_hybrid(df_close, cost_bps=args.cost_bps)
        print(f"  Net Sharpe: {hyb_res['net_gated_metrics']['sharpe']:.4f}")
        print(f"  CAGR:       {hyb_res['net_gated_metrics']['cagr']*100:.2f}%")
        print(f"  Max DD:     {hyb_res['net_gated_metrics']['max_drawdown']*100:.2f}%")
        return 0

    # ------------------------------------------------------------- 1. DATA
    if args.csv:
        df = pd.read_csv(args.csv, index_col=0, parse_dates=True)
    else:
        df = fetch(args.ticker, args.years)
    raw_close = df["Close"]
    corp = detect_corporate_actions(raw_close, args.corp_action_threshold)

    applied = []
    if args.splice.strip():
        from .data import splice as _splice
        dates = [d.strip() for d in args.splice.split(",") if d.strip()]
        df, applied = _splice(df, dates)

    close = df["Close"]
    labels = label_threshold(close, args.window, args.threshold)
    wret = window_return(close, args.window)
    n_lab = len(labels)
    if n_lab < args.min_train + 30:
        print(f"\n  insufficient history: {n_lab} labelled bars, need {args.min_train + 30}")
        return 2
    eval_index = labels.index[args.min_train + 1:]

    print(R.render_data(args.ticker, close, len(close), corp, applied,
                        eval_index.min().date(), eval_index.max().date(),
                        len(eval_index), int(df["Close"].isna().sum())))

    # ----------------------------------------------------------- 2. REGIME
    built = M.build(labels, stride=stride, stride_mode=args.stride_mode)
    ok, results = V.check_all(labels, wret, built["P_stride"])
    print("\n  label verification (FIX 2)")
    print("\n".join("  " + ln for ln in V.render_results(results).splitlines()))
    if not ok:
        print("\n  LABEL VERIFICATION FAILED - refusing to render a matrix that")
        print("  disagrees with the data. This is the 1.0 bull/bear swap guard.")
        return 2

    dist = state_distribution(labels)
    cells = cell_stats(built["counts_stride"], dist, stride, args.stride_mode)
    admissibility = signal_admissibility(built["P_stride"], args.signal_threshold)
    print(R.render_regime(dist, cells, built["counts_stride"], stride, args.stride_mode,
                          admissibility, M.signal_vector(built["P_stride"]),
                          M.convergence_profile(built["P_stride"])))

    # --------------------------------------------------------- 3. STRATEGY
    common = dict(mode=args.mode, stride=stride, stride_mode=args.stride_mode,
                  min_train=args.min_train, signal_threshold=args.signal_threshold,
                  cap=args.cap, scale=args.scale, cost_bps=args.cost_bps)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)  # already announced above
        res_legacy = walk_forward(close, labels, matrix_kind="overlapping", **common)
        res_fixed = walk_forward(close, labels, matrix_kind="stride", **common)
    res_base = run_label_only(close, labels, window=args.window, threshold=args.threshold,
                              min_train=args.min_train, cost_bps=args.cost_bps)

    bh = {"metrics": res_fixed["buy_hold_metrics"], "net_metrics": res_fixed["buy_hold_metrics"],
          "turnover": {"annualised": 0.0}}
    rows = [
        _row("Buy & hold", bh),
        _row(LABEL_ONLY_NAME, res_base),
        _row("Legacy Markov (overlapping matrix)", res_legacy),
        _row(f"Markov 2.0 ({args.mode}, stride matrix)", res_fixed),
    ]
    verdict = markov_adds_value(res_fixed["net_metrics"], res_base["net_metrics"])
    print(R.render_strategy(rows, args.cost_bps, verdict))

    # ------------------------------------------------------------- 4. NULL
    summary, n_perm_run = {}, 0
    if not args.no_null:
        lab_arr = labels.to_numpy(int)

        def evaluate(perm: np.ndarray) -> dict:
            s = pd.Series(perm, index=labels.index)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                r = walk_forward(close, s, matrix_kind="stride", **common)
            return r["net_metrics"]

        print(f"\n  running {args.permutations} {args.null_method} permutations ...")
        null_df = permutation_null(lab_arr, evaluate, n_perm=args.permutations,
                                   method=args.null_method)
        n_perm_run = len(null_df)
        summary = summarise(null_df, res_fixed["net_metrics"])

    trade = tradeability(
        corporate_actions=corp,
        spliced_dates=[a["date"] for a in applied if a.get("ok")],
        admissibility=admissibility,
        null_summary=summary or None,
        baseline_verdict=verdict,
        percentile_required=NULL_PERCENTILE_REQUIRED,
    )
    print(R.render_null(summary, n_perm_run, args.null_method, trade))

    # ------------------------------------------------------- optional extras
    if args.enhanced or args.hmm:
        print(R.header("APPENDIX - research diagnostics (not gated, not tradeable claims)"))
    if args.enhanced:
        from .states import label_enhanced
        elabels, feats = label_enhanced(df, args.window)
        em = M.build(elabels, stride=stride, stride_mode=args.stride_mode)
        eok, eres = V.check_all(elabels, wret, em["P_stride"])
        print("\n  ENHANCED STATES (KMeans on return / ATR% / relative volume)")
        print("\n".join("  " + ln for ln in V.render_results(eres).splitlines()))
        if eok:
            for s in range(N_STATES):
                sel = feats[elabels == s]
                print(f"    {STATE_NAMES[s]:>10s}  ret {sel['ret'].mean()*100:+6.2f}%   "
                      f"ATR {sel['atr_pct'].mean()*100:5.2f}%   relVol {sel['rel_vol'].mean():4.2f}")
    if args.hmm:
        from .hmm_mode import agreement, fit_hmm
        model, hlabels, info = fit_hmm(close.pct_change().dropna())
        print("\n  HIDDEN MARKOV (unsupervised)")
        if model is None:
            print(f"    skipped: {info}")
        else:
            ag = agreement(labels, hlabels)
            print(f"    agreement with threshold labels: {ag['overall']*100:.1f}% of {ag['n']} bars")

    if not args.no_plot:
        try:
            from .plot import plot_equity
            OUT_DIR.mkdir(exist_ok=True)
            out = OUT_DIR / f"{args.ticker}_{args.mode}_equity.png"
            plot_equity({
                "Buy & hold": res_fixed["buy_hold_returns"],
                LABEL_ONLY_NAME: res_base["net_returns"],
                "Legacy (overlapping)": res_legacy["net_returns"],
                f"Markov 2.0 ({args.mode})": res_fixed["net_returns"],
            }, out, f"{args.ticker} - walk-forward, {args.mode.upper()}, net of "
                    f"{args.cost_bps:.0f}bps")
            print(f"\n  equity curve -> {out}")
        except Exception as exc:  # noqa: BLE001
            print(f"\n  ! plot skipped: {exc}")

    print("\n" + R.RULE)
    print(f" FINAL: {trade['status']}")
    print(R.RULE + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
