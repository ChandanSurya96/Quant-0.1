"""Macro Strategy Baseline & Execution Optimization Evaluation Script.

Compares Raw Unoptimized Factor Baseline vs Optimized Strategy (Rank Hysteresis + Risk Parity).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from markov2.backtest import metrics, turnover
from markov2.data import filter_vendor_artifacts
from markov2.macro import walk_forward_macro
from markov2.splits import get_splits
from markov2.universe_data import DEFAULT_UNIVERSE, fetch_universe, get_tickers

MIN_TRAIN = 756
COST_BPS = 10.0


def evaluate_macro_variant(df_close: pd.DataFrame, use_hysteresis: bool, use_risk_parity: bool, n_long: int = 3, n_short: int = 3) -> dict:
    splits = get_splits(df_close, train_pct=0.60, val_pct=0.20)
    train_idx = splits["TRAIN"]
    val_idx = splits["VALIDATION"]
    oos_idx = splits["TRUE_OOS"]

    res = walk_forward_macro(
        df_close,
        min_train=MIN_TRAIN,
        cost_bps=COST_BPS,
        apply_markov_gate=False,  # Unfiltered cross-sectional ranking alpha
        n_long=n_long,
        n_short=n_short,
        use_hysteresis=use_hysteresis,
        use_risk_parity=use_risk_parity,
    )

    net_rets = res["net_returns"]
    positions = res["positions"]

    def calc_partition(name: str, part_idx: pd.Index) -> dict:
        common_idx = net_rets.index.intersection(part_idx)
        if len(common_idx) == 0:
            return {"name": name, "sharpe": float("nan"), "cagr": float("nan"), "volatility": float("nan"), "max_drawdown": float("nan"), "turnover": float("nan")}
        
        r_part = net_rets.reindex(common_idx).fillna(0.0).to_numpy()
        pos_part = positions.reindex(common_idx).fillna(0.0).to_numpy()
        
        total_gross = np.abs(pos_part).sum(axis=1)
        held_days = (total_gross > 0).astype(float)
        
        m = metrics(r_part, held_days)
        
        deltas = np.abs(np.diff(np.vstack((np.zeros(pos_part.shape[1]), pos_part)), axis=0))
        tno_sum = float(deltas.sum())
        tno_ann = (tno_sum / len(r_part)) * 252.0 if len(r_part) else 0.0
        
        sd = np.std(r_part, ddof=1)
        vol = float(sd * np.sqrt(252)) if sd > 0 else float("nan")
        
        return {
            "name": name,
            "sharpe": m["sharpe"],
            "cagr": m["cagr"],
            "volatility": vol,
            "max_drawdown": m["max_drawdown"],
            "turnover": tno_ann,
        }

    return {
        "TRAIN": calc_partition("TRAIN (60%)", train_idx),
        "VALIDATION": calc_partition("VALIDATION (20%)", val_idx),
        "TRUE_OOS": calc_partition("TRUE_OOS (20%)", oos_idx),
        "FULL": calc_partition("FULL EVALUATION", net_rets.index),
    }


def main():
    print("=" * 95, flush=True)
    print(" MACRO STRATEGY EXECUTION OPTIMIZATION: RANK HYSTERESIS & RISK PARITY REPORT", flush=True)
    print("=" * 95, flush=True)

    tickers = get_tickers(DEFAULT_UNIVERSE)
    print(f"Asset Universe ({len(tickers)} ETFs):", flush=True)
    for category, t_list in DEFAULT_UNIVERSE.items():
        print(f"  {category.capitalize():<12s}: {', '.join(t_list)}", flush=True)

    print("\nFetching & Sanitizing Multi-Asset Close Series (10 years)...", flush=True)
    df_raw = fetch_universe(tickers, years=10)

    df_clean_cols = {}
    for col in df_raw.columns:
        col_df = pd.DataFrame({"Close": df_raw[col], "Volume": 1000})
        filtered, _ = filter_vendor_artifacts(col_df)
        df_clean_cols[col] = filtered["Close"]

    df_close = pd.DataFrame(df_clean_cols).ffill().dropna(how="all")
    print(f"Dataset Size: {len(df_close)} daily bars | Date Range: {df_close.index.min().date()} to {df_close.index.max().date()}\n", flush=True)

    # Evaluate Raw Unoptimized Baseline
    raw_res = evaluate_macro_variant(df_close, use_hysteresis=False, use_risk_parity=False)

    # Evaluate Optimized Execution Strategy (Rank Hysteresis + Risk Parity)
    opt_res = evaluate_macro_variant(df_close, use_hysteresis=True, use_risk_parity=True)

    print("-" * 95, flush=True)
    print(" COMPARATIVE EXECUTION REPORT: RAW BASELINE VS. OPTIMIZED (HYSTERESIS + RISK PARITY)", flush=True)
    print("-" * 95, flush=True)
    print(f"  {'Partition':<18s} | {'Old Sharpe':>10s} | {'New Sharpe':>10s} | {'Old Turnover':>13s} | {'New Turnover':>13s} | {'Turnover Reduction':>18s}", flush=True)
    print("  " + "-" * 91, flush=True)

    for part_key in ["TRAIN", "VALIDATION", "TRUE_OOS", "FULL"]:
        old_p = raw_res[part_key]
        new_p = opt_res[part_key]
        tno_diff = old_p["turnover"] - new_p["turnover"]
        tno_pct = (tno_diff / old_p["turnover"] * 100.0) if old_p["turnover"] > 0 else 0.0
        
        print(f"  {old_p['name']:<18s} | {old_p['sharpe']:10.4f} | {new_p['sharpe']:10.4f} | {old_p['turnover']*100:12.2f}% | {new_p['turnover']*100:12.2f}% | {-tno_pct:+17.1f}%", flush=True)

    print("-" * 95, flush=True)
    print("\nDETAILED OPTIMIZED METRICS (RANK HYSTERESIS + INVERSE VOLATILITY RISK PARITY):", flush=True)
    print(f"  {'Partition':<18s} | {'Sharpe':>8s} | {'CAGR':>8s} | {'Vol':>8s} | {'MaxDD':>8s} | {'Turnover (Ann)':>14s}", flush=True)
    print("  " + "-" * 73, flush=True)
    for part_key in ["TRAIN", "VALIDATION", "TRUE_OOS", "FULL"]:
        p = opt_res[part_key]
        print(f"  {p['name']:<18s} | {p['sharpe']:8.4f} | {p['cagr']*100:7.2f}% | {p['volatility']*100:7.2f}% | {p['max_drawdown']*100:7.2f}% | {p['turnover']*100:13.2f}%", flush=True)

    print("=" * 95 + "\n", flush=True)


if __name__ == "__main__":
    main()
