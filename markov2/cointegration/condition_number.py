"""Condition Number Estimation Tool.

Implements:
1. `exact_condition_number(X)`: Standard oracle using SVD (complexity O(N d^2 + d^3)).
2. `estimate_condition_number(X, epsilon, max_iter)`: Fast iterative condition number
   estimator using Power / Lanczos Iteration on X^T X (complexity O(N d * k)),
   avoiding full SVD and matrix inversion.
"""

from __future__ import annotations

import warnings
import numpy as np
import pandas as pd


def _to_numpy_matrix(X: np.ndarray | pd.DataFrame) -> np.ndarray:
    """Validate input array/dataframe, handling non-finite values."""
    if isinstance(X, (pd.DataFrame, pd.Series)):
        arr = X.to_numpy(dtype=float)
    else:
        arr = np.asarray(X, dtype=float)

    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)

    if not np.all(np.isfinite(arr)):
        raise ValueError("Input matrix contains NaN, Inf, or non-numeric values.")

    return arr


def exact_condition_number(X: np.ndarray | pd.DataFrame) -> float:
    """Exact L2 condition number kappa(X) = sigma_max / sigma_min via SVD.

    Serves as the reference benchmark oracle.
    """
    arr = _to_numpy_matrix(X)
    s = np.linalg.svd(arr, compute_uv=False)
    if len(s) == 0 or s[-1] <= 0:
        return float("inf")
    return float(s[0] / s[-1])


def _power_iteration_largest_eig(A_func, d: int, max_iter: int, tol: float, seed: int = 42) -> tuple[float, int, bool]:
    """Iterative computation of the largest eigenvalue of symmetric operator A_func."""
    rng = np.random.RandomState(seed)
    v = rng.randn(d)
    v_norm = np.linalg.norm(v)
    if v_norm == 0:
        v = np.ones(d) / np.sqrt(d)
    else:
        v /= v_norm

    eig_val = 0.0
    converged = False

    for it in range(1, max_iter + 1):
        w = A_func(v)
        w_norm = np.linalg.norm(w)
        if w_norm == 0:
            return 0.0, it, True
        v_next = w / w_norm
        rayleigh = float(np.dot(v_next, A_func(v_next)))
        if abs(rayleigh - eig_val) < tol * max(1.0, abs(rayleigh)):
            converged = True
            eig_val = rayleigh
            return eig_val, it, converged
        eig_val = rayleigh
        v = v_next

    return eig_val, max_iter, converged


def _power_iteration_smallest_eig(X: np.ndarray, lambda_max: float, max_iter: int, tol: float, seed: int = 42) -> tuple[float, int, bool]:
    """Iterative computation of smallest singular value using inverse power iteration on X^T X."""
    N, d = X.shape
    XtX = X.T @ X
    reg = 1e-15 * max(1.0, lambda_max)
    XtX_reg = XtX + reg * np.eye(d)

    rng = np.random.RandomState(seed + 1)
    v = rng.randn(d)
    v_norm = np.linalg.norm(v)
    if v_norm == 0:
        v = np.ones(d) / np.sqrt(d)
    else:
        v /= v_norm

    eig_inv = 0.0
    converged = False

    for it in range(1, max_iter + 1):
        try:
            w = np.linalg.solve(XtX_reg, v)
        except np.linalg.LinAlgError:
            return 0.0, it, True

        w_norm = np.linalg.norm(w)
        if w_norm == 0:
            return 0.0, it, True

        v_next = w / w_norm
        rayleigh_inv = float(np.dot(v_next, w))
        if abs(rayleigh_inv - eig_inv) < tol * max(1.0, abs(rayleigh_inv)):
            converged = True
            eig_inv = rayleigh_inv
            break
        eig_inv = rayleigh_inv
        v = v_next

    lambda_min = max(0.0, (1.0 / max(1e-15, eig_inv)) - reg)
    return lambda_min, max_iter, converged


def estimate_condition_number(
    X: np.ndarray | pd.DataFrame,
    *,
    epsilon: float = 1e-6,
    max_iter: int = 1000,
    seed: int = 42,
) -> dict:
    """Fast estimation of kappa(X) = sigma_max / sigma_min without full SVD.

    Uses matrix-vector products X @ v and X.T @ u in O(N d * iterations).

    Parameters
    ----------
    X : array-like of shape (N, d)
        Design/price matrix.
    epsilon : float
        Desired convergence tolerance for power iterations.
    max_iter : int
        Maximum number of iterations allowed per eigenvalue estimate.
    seed : int
        Random seed for deterministic initialization.

    Returns
    -------
    dict
        - estimated_condition_number: float
        - method: str
        - precision: float (epsilon)
        - iterations: int (total iterations used)
        - converged: bool
        - diagnostics: dict (sigma_max, sigma_min, ill_conditioned, nearly_singular)
    """
    arr = _to_numpy_matrix(X)
    N, d = arr.shape

    if N < d:
        warnings.warn("Number of observations N < number of variables d. Matrix is rank deficient.", UserWarning)

    # Define operator for A = X^T X
    def XtX_op(v: np.ndarray) -> np.ndarray:
        return arr.T @ (arr @ v)

    # 1. Estimate largest eigenvalue of X^T X
    lambda_max, it1, conv1 = _power_iteration_largest_eig(XtX_op, d, max_iter, epsilon, seed=seed)
    sigma_max = np.sqrt(max(0.0, lambda_max))

    if sigma_max <= 0:
        return {
            "estimated_condition_number": float("inf"),
            "method": "Fast Shifted Power Iteration (O(N d * k))",
            "precision": float(epsilon),
            "iterations": it1,
            "converged": conv1,
            "diagnostics": {
                "sigma_max": 0.0,
                "sigma_min": 0.0,
                "ill_conditioned": True,
                "nearly_singular": True,
            },
        }

    # 2. Estimate smallest eigenvalue of X^T X via shifted power iteration
    lambda_min, it2, conv2 = _power_iteration_smallest_eig(arr, lambda_max, max_iter, epsilon, seed=seed)
    sigma_min = np.sqrt(max(0.0, lambda_min))

    if sigma_min <= 1e-12 * sigma_max:
        kappa_est = float("inf")
        nearly_singular = True
    else:
        kappa_est = float(sigma_max / sigma_min)
        nearly_singular = False

    ill_conditioned = bool(kappa_est > 1e4 or np.isinf(kappa_est))
    converged = bool(conv1 and conv2)
    total_iters = it1 + it2

    return {
        "estimated_condition_number": kappa_est,
        "method": "Fast Shifted Power Iteration (O(N d * k))",
        "precision": float(epsilon),
        "iterations": total_iters,
        "converged": converged,
        "diagnostics": {
            "sigma_max": float(sigma_max),
            "sigma_min": float(sigma_min),
            "ill_conditioned": ill_conditioned,
            "nearly_singular": nearly_singular,
        },
    }
