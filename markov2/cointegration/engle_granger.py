"""Engle-Granger Cointegration Test Tool.

Implements:
1. `engle_granger_test(y, X)`: Classical reference two-step Engle-Granger test via OLS
   and Augmented Dickey-Fuller (ADF) unit root t-statistic test on residuals.
2. `fast_engle_granger_test(y, X, epsilon)`: Accelerated QR-decomposition OLS solver with
   precision-controlled residual ADF test.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

# MacKinnon (2010) critical values approximation for ADF cointegration test (with constant)
# Format: {k_regressors: {0.01: c1, 0.05: c5, 0.10: c10}}
MACKINNON_CRITICAL_VALUES = {
    1: {0.01: -3.896, 0.05: -3.336, 0.10: -3.046},  # 1 regressor (pair)
    2: {0.01: -4.292, 0.05: -3.743, 0.10: -3.452},  # 2 regressors
    3: {0.01: -4.649, 0.05: -4.100, 0.10: -3.811},  # 3 regressors
    4: {0.01: -4.969, 0.05: -4.425, 0.10: -4.135},  # 4 regressors
}


def _get_critical_values(num_regressors: int) -> dict[float, float]:
    """Retrieve or interpolate MacKinnon critical values based on number of regressors."""
    if num_regressors in MACKINNON_CRITICAL_VALUES:
        return MACKINNON_CRITICAL_VALUES[num_regressors]
    # Asymptotic approximation formula for larger k
    k = num_regressors
    return {
        0.01: -3.896 - 0.35 * (k - 1),
        0.05: -3.336 - 0.38 * (k - 1),
        0.10: -3.046 - 0.36 * (k - 1),
    }


def _approximate_p_value(stat: float, k: int) -> float:
    """Approximate p-value for the cointegration ADF statistic using normal/t mixture."""
    # Empirical MacKinnon p-value approximation formula
    crit_5 = _get_critical_values(k)[0.05]
    if stat < crit_5:
        # Strongly cointegrated
        diff = crit_5 - stat
        p = 0.05 * np.exp(-1.2 * diff)
    else:
        diff = stat - crit_5
        p = min(1.0, 0.05 + 0.15 * diff)
    return float(np.clip(p, 1e-6, 1.0))


def _adf_on_residuals(residuals: np.ndarray, max_lags: int = 5) -> tuple[float, float, int]:
    """Runs Augmented Dickey-Fuller (ADF) regression on residuals u_t:

    Delta u_t = gamma * u_{t-1} + sum_{i=1}^{L-1} delta_i * Delta u_{t-i} + e_t

    Returns (DF_stat, p_val_approx, best_lag).
    """
    u = np.asarray(residuals, dtype=float)
    N = len(u)
    if N < 20:
        raise ValueError(f"Need at least 20 observations for ADF test, got {N}.")

    diff_u = np.diff(u)

    # Choose optimal lag using Akaike Information Criterion (AIC)
    best_aic = float("inf")
    best_stat = 0.0
    best_lag = 1

    for lag in range(1, min(max_lags + 1, (N - 5) // 2)):
        # Construct design matrix for ADF
        # Target: diff_u[lag:]
        # Regressors: u_{t-1} (lagged level), and diff_u_{t-1}...diff_u_{t-lag} (lagged diffs)
        Y_adf = diff_u[lag:]
        u_lag = u[lag:-1]

        cols = [u_lag]
        for i in range(1, lag):
            cols.append(diff_u[lag - i : -i])

        X_adf = np.column_stack(cols)

        # OLS solve
        try:
            beta_adf, resids, rank, s = np.linalg.lstsq(X_adf, Y_adf, rcond=None)
            gamma_hat = beta_adf[0]

            # Residual variance & SE(gamma_hat)
            e_adf = Y_adf - X_adf @ beta_adf
            rss = float(np.sum(e_adf ** 2))
            df_err = len(Y_adf) - X_adf.shape[1]
            if df_err <= 0 or rss <= 0:
                continue

            sigma_sq = rss / df_err
            var_beta = sigma_sq * np.linalg.inv(X_adf.T @ X_adf)
            se_gamma = float(np.sqrt(var_beta[0, 0]))

            if se_gamma > 0:
                t_stat = float(gamma_hat / se_gamma)
                aic = len(Y_adf) * np.log(rss / len(Y_adf)) + 2 * X_adf.shape[1]

                if aic < best_aic:
                    best_aic = aic
                    best_stat = t_stat
                    best_lag = lag
        except Exception:
            continue

    return best_stat, _approximate_p_value(best_stat, 1), best_lag


def engle_granger_test(
    y: np.ndarray | pd.Series,
    X: np.ndarray | pd.DataFrame,
    *,
    max_lags: int = 5,
) -> dict:
    """Classical Engle-Granger Two-Step Cointegration Test.

    Step 1: OLS regression y_t = alpha + X_t @ beta + u_t
    Step 2: ADF unit root test on residuals u_t.

    Returns dict with test_statistic, critical_values, p_value, cointegrated, hedge_ratio, residual, diagnostics.
    """
    y_arr = np.asarray(y, dtype=float).ravel()
    X_arr = np.asarray(X, dtype=float)
    if X_arr.ndim == 1:
        X_arr = X_arr.reshape(-1, 1)

    N, d = X_arr.shape
    if len(y_arr) != N:
        raise ValueError(f"Mismatch: y length {len(y_arr)} != X length {N}.")

    # Include constant in OLS
    X_design = np.column_stack([np.ones(N), X_arr])

    # Step 1: Classical OLS via Normal Equations / SVD
    beta_full, rss, rank, s = np.linalg.lstsq(X_design, y_arr, rcond=None)
    alpha_hat = beta_full[0]
    beta_hat = beta_full[1:]

    residuals = y_arr - X_design @ beta_full

    # Step 2: ADF test on residuals
    t_stat, p_val, optimal_lag = _adf_on_residuals(residuals, max_lags=max_lags)
    crit_vals = _get_critical_values(d)
    is_cointegrated = bool(t_stat < crit_vals[0.05])

    # R-squared
    ss_tot = np.sum((y_arr - np.mean(y_arr)) ** 2)
    ss_res = np.sum(residuals ** 2)
    r_squared = float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0

    return {
        "test_statistic": float(t_stat),
        "critical_values": crit_vals,
        "p_value": float(p_val),
        "cointegrated": is_cointegrated,
        "hedge_ratio": beta_hat,
        "intercept": float(alpha_hat),
        "residual": residuals,
        "diagnostics": {
            "r_squared": r_squared,
            "optimal_lags": optimal_lag,
            "n_obs": N,
            "num_regressors": d,
            "method": "Classical OLS + ADF Test",
        },
    }


def fast_engle_granger_test(
    y: np.ndarray | pd.Series,
    X: np.ndarray | pd.DataFrame,
    *,
    epsilon: float = 1e-6,
    max_lags: int = 5,
) -> dict:
    """Accelerated Engle-Granger Test using QR decomposition for OLS.

    Precision parameter `epsilon` controls tolerance for rank decision in QR.
    Serves as the high-efficiency counterpart.
    """
    y_arr = np.asarray(y, dtype=float).ravel()
    X_arr = np.asarray(X, dtype=float)
    if X_arr.ndim == 1:
        X_arr = X_arr.reshape(-1, 1)

    N, d = X_arr.shape
    if len(y_arr) != N:
        raise ValueError(f"Mismatch: y length {len(y_arr)} != X length {N}.")

    # Design matrix with constant
    X_design = np.column_stack([np.ones(N), X_arr])

    # Fast OLS via QR decomposition: X = Q R -> R beta = Q^T y
    Q, R = np.linalg.qr(X_design)

    # Check for near-singularity using epsilon
    diag_R = np.abs(np.diag(R))
    if np.any(diag_R < epsilon):
        warnings.warn("Nearly singular matrix detected in fast QR OLS solve.", UserWarning)

    Qty = Q.T @ y_arr
    beta_full = np.linalg.solve(R, Qty)

    alpha_hat = beta_full[0]
    beta_hat = beta_full[1:]
    residuals = y_arr - X_design @ beta_full

    # ADF test on residuals
    t_stat, p_val, optimal_lag = _adf_on_residuals(residuals, max_lags=max_lags)
    crit_vals = _get_critical_values(d)
    is_cointegrated = bool(t_stat < crit_vals[0.05])

    ss_tot = np.sum((y_arr - np.mean(y_arr)) ** 2)
    ss_res = np.sum(residuals ** 2)
    r_squared = float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0

    return {
        "test_statistic": float(t_stat),
        "critical_values": crit_vals,
        "p_value": float(p_val),
        "cointegrated": is_cointegrated,
        "hedge_ratio": beta_hat,
        "intercept": float(alpha_hat),
        "residual": residuals,
        "diagnostics": {
            "r_squared": r_squared,
            "optimal_lags": optimal_lag,
            "n_obs": N,
            "num_regressors": d,
            "precision_epsilon": float(epsilon),
            "method": "Fast QR OLS + ADF Test",
        },
    }
