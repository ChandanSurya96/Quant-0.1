"""Euclidean Distance and Spread Variance calculations per Gatev et al. (2006)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def calculate_pairwise_distances(
    normalized_prices: pd.DataFrame,
) -> dict[tuple[str, str], float]:
    """Calculates sum of squared differences (SSD) / Euclidean distance between all pairs.

    Formula:
        D_{i,j} = (1/T) * sum_{t=1}^T (P_{i,t} - P_{j,t})^2
        Vectorized: mean(P_i^2) + mean(P_j^2) - 2 * (P^T P / T)_{i,j}
    """
    cols = list(normalized_prices.columns)
    T = len(normalized_prices)
    if T == 0 or len(cols) < 2:
        return {}

    vals = normalized_prices.to_numpy(dtype=float)
    n_cols = len(cols)

    # Fast matrix calculation: D = P2_mean + P2_mean.T - 2 * (vals.T @ vals) / T
    if not np.isnan(vals).any():
        p2_mean = np.mean(vals ** 2, axis=0, keepdims=True)
        gram = (vals.T @ vals) / T
        dist_mat = p2_mean + p2_mean.T - 2.0 * gram
        dist_mat = np.maximum(0.0, dist_mat)

        distances: dict[tuple[str, str], float] = {}
        for i in range(n_cols):
            for j in range(i + 1, n_cols):
                distances[(cols[i], cols[j])] = float(dist_mat[i, j])
        return distances

    # Fallback with NaN masking
    distances: dict[tuple[str, str], float] = {}
    for i in range(n_cols):
        for j in range(i + 1, n_cols):
            diff = vals[:, i] - vals[:, j]
            valid_mask = ~np.isnan(diff)
            if np.sum(valid_mask) >= max(10, int(T * 0.8)):
                distances[(cols[i], cols[j])] = float(np.mean(diff[valid_mask] ** 2))

    return distances


def calculate_spread_variance(
    p_i: np.ndarray | pd.Series,
    p_j: np.ndarray | pd.Series,
) -> tuple[float, float]:
    """Calculates historical mean spread and spread standard deviation s_{i,j}.

    Formula:
        s_{i,j}^2 = (1/T) * sum_{t=1}^T [ (P_{i,t} - P_{j,t}) - mean(P_i - P_j) ]^2

    Returns:
        (mean_spread, s_ij)
    """
    arr_i = np.asarray(p_i, dtype=float)
    arr_j = np.asarray(p_j, dtype=float)
    diff = arr_i - arr_j
    valid = diff[~np.isnan(diff)]

    if len(valid) < 2:
        return 0.0, 1.0

    mean_spread = float(np.mean(valid))
    var_spread = float(np.var(valid, ddof=1))
    s_ij = float(np.sqrt(max(1e-8, var_spread)))
    return mean_spread, s_ij
