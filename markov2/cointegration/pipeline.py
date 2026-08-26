"""Multivariate Cointegration Screening Pipeline & Walk-Forward Leakage Protection.

Provides:
1. `scan_cointegrated_pairs(prices_df, kappa_threshold, epsilon)`: Preselects asset pairs
   using fast condition-number screening, then runs the fast Engle-Granger test.
2. `walk_forward_cointegration(prices_df, train_window)`: Walk-forward estimation of
   spreads enforcing t_train <= t to strictly prevent future data leakage.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from .condition_number import estimate_condition_number
from .engle_granger import fast_engle_granger_test


def scan_cointegrated_pairs(
    prices: pd.DataFrame,
    *,
    kappa_threshold: float = 100.0,
    epsilon: float = 1e-6,
    alpha_significance: float = 0.05,
) -> list[dict]:
    """Scan a multivariate stock universe for cointegrated pairs.

    Uses Tool Algorithm 1 (Condition Number Estimation) to filter out non-multicollinear
    candidates first, eliminating wasteful ADF tests. Then applies Tool Algorithm 2
    (Engle-Granger Cointegration Test) on candidate pairs.

    Returns a list of cointegrated pair dicts sorted by test statistic significance.
    """
    df = prices.dropna(how="all").ffill()
    tickers = list(df.columns)
    d = len(tickers)

    if d < 2:
        raise ValueError("Need at least 2 stock series to scan for cointegrated pairs.")

    results = []
    pair_candidates = list(itertools.combinations(tickers, 2))

    for t1, t2 in pair_candidates:
        p1 = df[t1].to_numpy(dtype=float)
        p2 = df[t2].to_numpy(dtype=float)

        # Build pair matrix X = [p1, p2]
        X = np.column_stack([p1, p2])
        if not np.all(np.isfinite(X)):
            continue

        # Tool 1: Fast Condition Number Preselection
        cond_res = estimate_condition_number(X, epsilon=epsilon)
        kappa = cond_res["estimated_condition_number"]

        # If condition number is too low, the series lack sufficient collinearity/comovement
        if kappa < kappa_threshold and not np.isinf(kappa):
            continue

        # Tool 2: Fast Cointegration Test (regress p1 on p2)
        eg_res = fast_engle_granger_test(p1, p2, epsilon=epsilon)

        if eg_res["cointegrated"]:
            results.append({
                "pair": (t1, t2),
                "asset_y": t1,
                "asset_x": t2,
                "condition_number": kappa,
                "test_statistic": eg_res["test_statistic"],
                "p_value": eg_res["p_value"],
                "hedge_ratio": float(eg_res["hedge_ratio"][0]),
                "intercept": float(eg_res["intercept"]),
                "r_squared": eg_res["diagnostics"]["r_squared"],
            })

    # Sort by test statistic ascending (more negative = stronger cointegration)
    results.sort(key=lambda item: item["test_statistic"])
    return results


def walk_forward_cointegration(
    prices: pd.DataFrame,
    *,
    train_window: int = 504,
    rebalance_freq: int = 21,
    kappa_threshold: float = 50.0,
    epsilon: float = 1e-6,
) -> dict:
    """Walk-forward cointegration estimation with strict zero data leakage.

    At each bar t, the hedge ratio and cointegration decision use ONLY data <= t.
    Returns daily spread series, rolling hedge ratios, and cointegration state flags.
    """
    df = prices.dropna(how="all").ffill()
    N, d = df.shape

    if N < train_window + 30:
        raise ValueError(f"Need at least {train_window + 30} bars for walk-forward, got {N}.")

    # Storage for walk-forward series
    active_index = df.index[train_window:]
    spread_series = pd.Series(0.0, index=active_index)
    active_pair_series = pd.Series("", index=active_index)
    is_cointegrated_series = pd.Series(False, index=active_index)

    current_pair = None
    current_beta = 0.0
    current_alpha = 0.0
    current_active = False

    for t in range(train_window, N):
        # Re-estimate model strictly on past window: df.iloc[t - train_window : t]
        if (t - train_window) % rebalance_freq == 0:
            past_data = df.iloc[t - train_window : t]
            candidates = scan_cointegrated_pairs(
                past_data,
                kappa_threshold=kappa_threshold,
                epsilon=epsilon,
            )

            if len(candidates) > 0:
                best = candidates[0]
                current_pair = best["pair"]
                current_beta = best["hedge_ratio"]
                current_alpha = best["intercept"]
                current_active = True
            else:
                current_active = False

        idx_val = df.index[t]
        if current_active and current_pair is not None:
            t1, t2 = current_pair
            y_val = df.loc[idx_val, t1]
            x_val = df.loc[idx_val, t2]
            # Spread = y - (alpha + beta * x)
            spread_series.loc[idx_val] = float(y_val - (current_alpha + current_beta * x_val))
            active_pair_series.loc[idx_val] = f"{t1}/{t2}"
            is_cointegrated_series.loc[idx_val] = True
        else:
            spread_series.loc[idx_val] = 0.0
            active_pair_series.loc[idx_val] = "NONE"
            is_cointegrated_series.loc[idx_val] = False

    return {
        "index": active_index,
        "spread": spread_series,
        "active_pair": active_pair_series,
        "is_cointegrated": is_cointegrated_series,
        "train_window": train_window,
        "rebalance_freq": rebalance_freq,
    }
