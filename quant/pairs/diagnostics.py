"""Risk Diagnostics & Factor Decompositions for Pairs Trading per Zhu (2024)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def newey_west_ols(
    y: np.ndarray | pd.Series,
    X: np.ndarray | pd.DataFrame,
    lags: int = 6,
) -> dict:
    """Estimates OLS regression with Newey-West (1987) HAC standard errors.

    Model:
        y = X * beta + u
    """
    y_arr = np.asarray(y, dtype=float)
    X_arr = np.asarray(X, dtype=float)

    if X_arr.ndim == 1:
        X_arr = X_arr[:, np.newaxis]

    # Add constant intercept column if not present
    if not np.allclose(X_arr[:, 0], 1.0):
        X_mat = np.column_stack([np.ones(len(y_arr)), X_arr])
    else:
        X_mat = X_arr

    T, K = X_mat.shape
    if T <= K:
        return {"coefficients": np.zeros(K), "t_stats": np.zeros(K), "p_values": np.ones(K), "r_squared": 0.0}

    # OLS Estimator
    XtX_inv = np.linalg.pinv(X_mat.T @ X_mat)
    beta = XtX_inv @ X_mat.T @ y_arr
    u = y_arr - X_mat @ beta

    # Newey-West Spectral Density Matrix S_0 + sum_{l=1}^L w_l (S_l + S_l^T)
    # where w_l = 1 - l / (L + 1)
    S = np.zeros((K, K), dtype=float)
    for t in range(T):
        x_t = X_mat[t:t+1, :]
        S += (u[t] ** 2) * (x_t.T @ x_t)

    for lag_idx in range(1, lags + 1):
        weight = 1.0 - lag_idx / (lags + 1.0)
        gamma_lag = np.zeros((K, K), dtype=float)
        for t in range(lag_idx, T):
            x_t = X_mat[t:t+1, :]
            x_tl = X_mat[t-lag_idx:t-lag_idx+1, :]
            gamma_lag += (u[t] * u[t-lag_idx]) * (x_t.T @ x_tl)
        S += weight * (gamma_lag + gamma_lag.T)

    V = T * (XtX_inv @ S @ XtX_inv)
    se = np.sqrt(np.maximum(1e-12, np.diag(V) / T))
    t_stats = beta / se

    # Two-sided normal approximation p-values using standard error function (erf)
    import math
    p_values = np.array([
        2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(float(t)) / math.sqrt(2.0))))
        for t in t_stats
    ])

    # R-squared
    ss_tot = np.sum((y_arr - np.mean(y_arr)) ** 2)
    ss_res = np.sum(u ** 2)
    r2 = 1.0 - (ss_res / max(1e-12, ss_tot))

    return {
        "coefficients": beta,
        "std_errors": se,
        "t_stats": t_stats,
        "p_values": p_values,
        "r_squared": float(r2),
        "residuals": u,
        "residual_std": float(np.std(u, ddof=K)),
        "alpha": float(beta[0]),
        "alpha_t_stat": float(t_stats[0]),
        "alpha_p_value": float(p_values[0]),
    }


class PairsRiskDiagnostics:
    """Decomposes strategy excess returns against 6-factor and macroeconomic risk models."""

    @staticmethod
    def run_six_factor_model(
        strategy_returns: pd.Series,
        factors_df: pd.DataFrame,
        lags: int = 6,
    ) -> dict:
        """Estimates Eq (3): R_t = alpha + beta' [MKT, SMB, HML, MOM, SRV, LRV] + e_t."""
        common_idx = strategy_returns.dropna().index.intersection(factors_df.dropna().index)
        if len(common_idx) < 30:
            return {"error": "Insufficient overlapping data for 6-factor regression"}

        y = strategy_returns.loc[common_idx]
        X = factors_df.loc[common_idx]
        res = newey_west_ols(y, X, lags=lags)
        factor_names = ["Intercept"] + list(X.columns)

        loadings = {
            factor_names[i]: {
                "beta": float(res["coefficients"][i]),
                "t_stat": float(res["t_stats"][i]),
                "p_value": float(res["p_values"][i]),
            }
            for i in range(len(factor_names))
        }

        ir = float(res["alpha"] / max(1e-8, res["residual_std"]))
        return {
            "loadings": loadings,
            "r_squared": res["r_squared"],
            "information_ratio": ir,
            "residual_std": res["residual_std"],
        }

    @staticmethod
    def run_macro_risk_model(
        strategy_returns: pd.Series,
        macro_df: pd.DataFrame,
        lags: int = 6,
    ) -> dict:
        """Estimates Table 3: R_t = alpha + beta' [DEF, DIV, GDP, INF, MKT, RREL, TERM, UNEMP] + e_t."""
        common_idx = strategy_returns.dropna().index.intersection(macro_df.dropna().index)
        if len(common_idx) < 30:
            return {"error": "Insufficient overlapping data for macro regression"}

        y = strategy_returns.loc[common_idx]
        X = macro_df.loc[common_idx]
        res = newey_west_ols(y, X, lags=lags)
        macro_names = ["Intercept"] + list(X.columns)

        loadings = {
            macro_names[i]: {
                "beta": float(res["coefficients"][i]),
                "t_stat": float(res["t_stats"][i]),
                "p_value": float(res["p_values"][i]),
            }
            for i in range(len(macro_names))
        }

        return {
            "loadings": loadings,
            "r_squared": res["r_squared"],
            "residual_std": res["residual_std"],
        }
