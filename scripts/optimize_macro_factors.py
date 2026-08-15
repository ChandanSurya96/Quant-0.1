"""Macro Factor Optimization & Decay Analysis Harness.

Sweeps Momentum (63, 126, 252, 504) and Value (252, 504, 756, 1008) windows across 16 parameter pairs.
Measures TRAIN, VALIDATION, TRUE_OOS Net Sharpe ratios and OOS Degradation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from markov2.backtest import metrics
from markov2.data import filter_vendor_artifacts
from markov2.macro import walk_forward_macro
from markov2.splits import get_splits
from markov2.universe_data import DEFAULT_UNIVERSE, fetch_universe, get_tickers

MIN_TRAIN = 756
COST_BPS = 10.0

MOM_WINDOWS = [63, 126, 252, 504]
VAL_WINDOWS = [252, 504, 756, 1008]

MOM_LABELS = {63: "3M", 126: "6M", 252: "12M", 504: "24M"}
VAL_LABELS = {252: "1Y", 504: "2Y", 756: "3Y", 1008: "4Y"}


def evaluate_param_set(df_close: pd.DataFrame, mom_win: int, val_win: int, splits: dict) -> dict:
    train_idx = splits["TRAIN"]
    val_idx = splits["VALIDATION"]
    oos_idx = splits["TRUE_OOS"]

    res = walk_forward_macro(
        df_close,
        min_train=MIN_TRAIN,
        cost_bps=COST_BPS,
        apply_markov_gate=False,
        n_long=3,
        n_short=3,
        use_hysteresis=True,
        use_risk_parity=True,
        mom_window=mom_win,
        val_window=val_win,
    )

    net_rets = res["net_returns"]
    positions = res["positions"]

    def calc_sharpe(part_idx: pd.Index) -> float:
        common_idx = net_rets.index.intersection(part_idx)
        if len(common_idx) == 0:
            return float("nan")
        r_part = net_rets.reindex(common_idx).fillna(0.0).to_numpy()
        pos_part = positions.reindex(common_idx).fillna(0.0).to_numpy()
        total_gross = np.abs(pos_part).sum(axis=1)
        held_days = (total_gross > 0).astype(float)
        m = metrics(r_part, held_days)
        return float(m["sharpe"])

    train_sharpe = calc_sharpe(train_idx)
    val_sharpe = calc_sharpe(val_idx)
    oos_sharpe = calc_sharpe(oos_idx)
    degradation = val_sharpe - oos_sharpe

    return {
        "mom_win": mom_win,
        "val_win": val_win,
        "mom_label": MOM_LABELS[mom_win],
        "val_label": VAL_LABELS[val_win],
        "train_sharpe": train_sharpe,
        "val_sharpe": val_sharpe,
        "oos_sharpe": oos_sharpe,
        "degradation": degradation,
    }


def main():
    print("=" * 105, flush=True)
    print(" MACRO FACTOR OPTIMIZATION & DECAY ANALYSIS HARNESS (16 COMBINATIONS)", flush=True)
    print("=" * 105, flush=True)

    tickers = get_tickers(DEFAULT_UNIVERSE)
    print(f"Asset Universe ({len(tickers)} ETFs):", flush=True)
    for category, t_list in DEFAULT_UNIVERSE.items():
        print(f"  {category.capitalize():<12s}: {', '.join(t_list)}", flush=True)

    print("\nFetching & Sanitizing Multi-Asset Close Series...", flush=True)
    df_raw = fetch_universe(tickers, years=10)

    df_clean_cols = {}
    for col in df_raw.columns:
        col_df = pd.DataFrame({"Close": df_raw[col], "Volume": 1000})
        filtered, _ = filter_vendor_artifacts(col_df)
        df_clean_cols[col] = filtered["Close"]

    df_close = pd.DataFrame(df_clean_cols).ffill().dropna(how="all")
    splits = get_splits(df_close, train_pct=0.60, val_pct=0.20)
    print(f"Dataset Size: {len(df_close)} daily bars | Date Range: {df_close.index.min().date()} to {df_close.index.max().date()}\n", flush=True)

    results = []
    print("Executing 16-Parameter Sweep across TRAIN, VALIDATION, and TRUE_OOS partitions...", flush=True)
    count = 0
    for mom_win in MOM_WINDOWS:
        for val_win in VAL_WINDOWS:
            count += 1
            res = evaluate_param_set(df_close, mom_win, val_win, splits)
            print(f"  [{count:02d}/16] Evaluated Mom={mom_win:<3d} ({MOM_LABELS[mom_win]:<3s}) + Val={val_win:<4d} ({VAL_LABELS[val_win]:<2s}) -> Val Sharpe={res['val_sharpe']:.4f}, OOS Sharpe={res['oos_sharpe']:.4f}", flush=True)
            results.append(res)

    # Sort results descending by VALIDATION Sharpe
    results.sort(key=lambda x: x["val_sharpe"], reverse=True)

    print("\n" + "-" * 105, flush=True)
    print(" PARAMETER SWEEP RESULTS TABLE (SORTED BY VALIDATION SHARPE)", flush=True)
    print("-" * 105, flush=True)
    print(f"  {'Rank':<5s} | {'Mom Window':<12s} | {'Val Window':<12s} | {'TRAIN Sharpe':>14s} | {'VAL Sharpe':>14s} | {'TRUE_OOS Sharpe':>16s} | {'OOS Degradation':>16s}", flush=True)
    print("  " + "-" * 101, flush=True)

    survived_oos = 0
    for idx, r in enumerate(results, 1):
        is_pos = r["oos_sharpe"] > 0
        if is_pos:
            survived_oos += 1
        pos_flag = " [POSITIVE OOS]" if is_pos else ""
        m_str = f"{r['mom_win']} ({r['mom_label']})"
        v_str = f"{r['val_win']} ({r['val_label']})"
        print(
            f"  {idx:<5d} | {m_str:<12s} | {v_str:<12s} | "
            f"{r['train_sharpe']:14.4f} | {r['val_sharpe']:14.4f} | {r['oos_sharpe']:16.4f} | {r['degradation']:16.4f}{pos_flag}",
            flush=True,
        )

    print("-" * 105, flush=True)
    print("\nFACTOR DECAY & REGIME SHIFT ANALYSIS:", flush=True)
    print(f"  1. Combinations with Positive TRUE_OOS Sharpe: {survived_oos} / 16 ({survived_oos/16*100:.1f}%)", flush=True)
    
    top_comb = results[0]
    print(f"  2. Top Validation Parameter Set: Mom={top_comb['mom_win']} ({top_comb['mom_label']}) + Val={top_comb['val_win']} ({top_comb['val_label']})", flush=True)
    print(f"     Achieves Validation Sharpe={top_comb['val_sharpe']:.4f}, but TRUE_OOS Sharpe={top_comb['oos_sharpe']:.4f} (Degradation={top_comb['degradation']:.4f}).", flush=True)

    # Check if shorter momentum windows (e.g. 63 or 126) perform better OOS
    short_mom_res = [r for r in results if r["mom_win"] in [63, 126]]
    best_short_mom = max(short_mom_res, key=lambda x: x["oos_sharpe"])
    print(f"  3. Best Short-Term Momentum Parameter Set: Mom={best_short_mom['mom_win']} ({best_short_mom['mom_label']}) + Val={best_short_mom['val_win']} ({best_short_mom['val_label']})", flush=True)
    print(f"     Achieves TRUE_OOS Sharpe={best_short_mom['oos_sharpe']:.4f} vs Validation Sharpe={best_short_mom['val_sharpe']:.4f}.", flush=True)

    print("\nVERDICT:", flush=True)
    if survived_oos > 0:
        print("  -> Factor alpha SURVIVES in TRUE_OOS under specific parameter configurations!", flush=True)
    else:
        print("  -> Cross-sectional factor ranking suffers REGIME SHIFT DECAY across ALL parameter sets in TRUE_OOS.", flush=True)
    print("=" * 105 + "\n", flush=True)


if __name__ == "__main__":
    main()
