"""Benchmark Suite and Synthetic Validation Engine for Cointegration & Condition Number Tools."""

from __future__ import annotations

import time
import numpy as np
import pandas as pd

from .condition_number import estimate_condition_number, exact_condition_number
from .engle_granger import engle_granger_test, fast_engle_granger_test


def generate_synthetic_cases(N: int = 1000, seed: int = 42) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Generates 5 distinct synthetic time-series test cases:

    Case A: Independent random walks (No cointegration)
    Case B: Genuinely cointegrated random walks (y = 1.5 * x + stationary_noise)
    Case C: Nearly cointegrated series (high persistence AR(1) noise)
    Case D: Cointegrated series with structural break at N/2
    Case E: Highly correlated non-stationary series WITHOUT cointegration (Demonstrates Correlation != Cointegration)
    """
    rng = np.random.RandomState(seed)

    # Case A: Independent random walks
    x_a = np.cumsum(rng.randn(N))
    y_a = np.cumsum(rng.randn(N))

    # Case B: Genuinely cointegrated random walks
    x_b = np.cumsum(rng.randn(N))
    stationary_noise = np.random.normal(0, 1.0, N)
    # AR(1) stationary noise with phi = 0.5
    for i in range(1, N):
        stationary_noise[i] += 0.5 * stationary_noise[i - 1]
    y_b = 1.5 * x_b + 5.0 + stationary_noise

    # Case C: Nearly cointegrated series (phi = 0.98, near unit root)
    x_c = np.cumsum(rng.randn(N))
    near_unit_root = np.random.normal(0, 1.0, N)
    for i in range(1, N):
        near_unit_root[i] += 0.98 * near_unit_root[i - 1]
    y_c = 1.2 * x_c + near_unit_root

    # Case D: Structural break at N/2
    x_d = np.cumsum(rng.randn(N))
    noise_d = rng.randn(N)
    y_d = 1.5 * x_d + noise_d
    y_d[N // 2 :] += 20.0  # Shift level by 20 at midpoint

    # Case E: Highly correlated BUT NOT cointegrated series
    # Shared trend component makes correlation ~0.99, but residuals are non-stationary random walk!
    trend = np.cumsum(rng.randn(N))
    x_e = trend + np.cumsum(rng.randn(N) * 0.1)
    y_e = trend + np.cumsum(rng.randn(N) * 0.1)

    return {
        "Case A (Independent Random Walks)": (y_a, x_a),
        "Case B (Genuinely Cointegrated)": (y_b, x_b),
        "Case C (Nearly Cointegrated)": (y_c, x_c),
        "Case D (Structural Break)": (y_d, x_d),
        "Case E (High Correlation, NO Cointegration)": (y_e, x_e),
    }


def run_synthetic_validation() -> pd.DataFrame:
    """Evaluates Engle-Granger test on Cases A-E to validate statistical correctness."""
    cases = generate_synthetic_cases()
    records = []

    for name, (y, x) in cases.items():
        # Compute Pearson correlation
        corr = float(np.corrcoef(y, x)[0, 1])

        # Run classical & fast tests
        res_class = engle_granger_test(y, x)
        res_fast = fast_engle_granger_test(y, x)

        records.append({
            "Case": name,
            "Correlation": round(corr, 4),
            "Classical DF Stat": round(res_class["test_statistic"], 4),
            "Fast DF Stat": round(res_fast["test_statistic"], 4),
            "Cointegrated": res_fast["cointegrated"],
            "Hedge Ratio": round(float(res_fast["hedge_ratio"][0]), 4),
        })

    return pd.DataFrame(records)


def benchmark_condition_number_estimator(
    matrices_count: int = 20,
    seed: int = 42
) -> dict:
    """Benchmark exact SVD condition number vs fast Lanczos/Power Iteration estimator across controlled matrices."""
    rng = np.random.RandomState(seed)
    exact_kappa_list = []
    est_kappa_list = []
    rel_errors = []
    times_exact = []
    times_fast = []

    for idx in range(matrices_count):
        N = 1000
        d = 10
        # Generate matrix with controlled singular values
        U, _ = np.linalg.qr(rng.randn(N, d))
        V, _ = np.linalg.qr(rng.randn(d, d))
        # Log-spaced singular values giving known condition number
        target_kappa = 10 ** (1 + (idx % 5))  # kappa from 10 to 100000
        s_vals = np.linspace(target_kappa, 1.0, d)
        S = np.diag(s_vals)

        X = U @ S @ V.T

        # Exact SVD benchmark
        t0 = time.perf_counter()
        k_exact = exact_condition_number(X)
        t1 = time.perf_counter()

        # Fast estimator benchmark
        t2 = time.perf_counter()
        est_res = estimate_condition_number(X, epsilon=1e-6)
        k_est = est_res["estimated_condition_number"]
        t3 = time.perf_counter()

        exact_kappa_list.append(k_exact)
        est_kappa_list.append(k_est)
        rel_err = abs(k_est - k_exact) / k_exact if np.isfinite(k_exact) and k_exact > 0 else 0.0
        rel_errors.append(rel_err)

        times_exact.append(t1 - t0)
        times_fast.append(t3 - t2)

    return {
        "mean_relative_error": float(np.mean(rel_errors)),
        "max_relative_error": float(np.max(rel_errors)),
        "mean_time_exact_ms": float(np.mean(times_exact) * 1000),
        "mean_time_fast_ms": float(np.mean(times_fast) * 1000),
        "speedup_factor": float(np.mean(times_exact) / np.mean(times_fast)),
    }


def benchmark_precision_scaling(
    epsilons: list[float] = [1e-2, 1e-4, 1e-6, 1e-8],
    N: int = 2000,
    d: int = 10,
    seed: int = 42
) -> pd.DataFrame:
    """Measures empirical relationship between epsilon parameter, runtime, and approximation accuracy."""
    rng = np.random.RandomState(seed)
    X = rng.randn(N, d)
    y = X @ rng.randn(d) + rng.randn(N)

    exact_res = engle_granger_test(y, X)
    exact_stat = exact_res["test_statistic"]

    records = []
    for eps in epsilons:
        t0 = time.perf_counter()
        fast_res = fast_engle_granger_test(y, X, epsilon=eps)
        t1 = time.perf_counter()

        fast_stat = fast_res["test_statistic"]
        abs_err = abs(fast_stat - exact_stat)
        rel_err = abs_err / abs(exact_stat) if exact_stat != 0 else 0.0

        records.append({
            "Epsilon": eps,
            "Runtime (ms)": round((t1 - t0) * 1000, 4),
            "Test Statistic": round(fast_stat, 6),
            "Abs Error": round(abs_err, 8),
            "Rel Error": round(rel_err, 8),
        })

    return pd.DataFrame(records)


def benchmark_scaling(
    N_list: list[int] = [1000, 2000, 5000, 10000],
    d_list: list[int] = [2, 5, 10, 25],
    seed: int = 42
) -> pd.DataFrame:
    """Measures empirical runtime scaling across varying sample size N and dimensionality d.
    Fits empirical scaling exponent N^a d^b.
    """
    rng = np.random.RandomState(seed)
    records = []

    for N in N_list:
        for d in d_list:
            X = rng.randn(N, d)
            y = X @ rng.randn(d) + rng.randn(N)

            # Classical OLS benchmark
            t0 = time.perf_counter()
            _ = engle_granger_test(y, X)
            t1 = time.perf_counter()
            time_class = t1 - t0

            # Fast QR benchmark
            t2 = time.perf_counter()
            _ = fast_engle_granger_test(y, X, epsilon=1e-6)
            t3 = time.perf_counter()
            time_fast = t3 - t2

            records.append({
                "N": N,
                "d": d,
                "Classical Time (ms)": round(time_class * 1000, 4),
                "Fast Time (ms)": round(time_fast * 1000, 4),
                "Speedup Ratio": round(time_class / time_fast if time_fast > 0 else 1.0, 2),
            })

    df_res = pd.DataFrame(records)

    # Fit empirical log-linear regression log(time) = c + a * log(N) + b * log(d)
    log_N = np.log(df_res["N"].to_numpy())
    log_d = np.log(df_res["d"].to_numpy())
    log_t = np.log(df_res["Fast Time (ms)"].to_numpy() + 1e-9)

    A_reg = np.column_stack([np.ones(len(log_N)), log_N, log_d])
    coeffs, _, _, _ = np.linalg.lstsq(A_reg, log_t, rcond=None)
    a_exp, b_exp = coeffs[1], coeffs[2]

    df_res.attrs["empirical_scaling"] = f"Runtime ~ N^{a_exp:.2f} * d^{b_exp:.2f}"
    return df_res
