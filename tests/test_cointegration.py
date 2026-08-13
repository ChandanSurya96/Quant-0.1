"""Test suite for the Cointegration & Condition-Number Subsystem."""

from __future__ import annotations

import pytest
import numpy as np
import pandas as pd

from markov2.cointegration import (
    exact_condition_number,
    estimate_condition_number,
    engle_granger_test,
    fast_engle_granger_test,
    scan_cointegrated_pairs,
    walk_forward_cointegration,
)
from markov2.cointegration.benchmark import (
    generate_synthetic_cases,
    run_synthetic_validation,
    benchmark_condition_number_estimator,
    benchmark_precision_scaling,
)


# =====================================================================
# 1. UNIT & NUMERICAL TESTS: CONDITION NUMBER
# =====================================================================

def test_exact_condition_number_identity():
    """Identity matrix should have condition number kappa = 1.0."""
    I = np.eye(5)
    assert np.isclose(exact_condition_number(I), 1.0, atol=1e-5)


def test_exact_condition_number_scaled():
    """Diagonal matrix with entries 10 and 1 should have kappa = 10.0."""
    D = np.diag([10.0, 5.0, 1.0])
    assert np.isclose(exact_condition_number(D), 10.0, atol=1e-5)


def test_estimate_condition_number_well_conditioned():
    """Fast estimator on well-conditioned matrix should match exact SVD within tolerance."""
    rng = np.random.RandomState(42)
    X = rng.randn(500, 5)
    exact_k = exact_condition_number(X)
    est_dict = estimate_condition_number(X, epsilon=1e-6)
    est_k = est_dict["estimated_condition_number"]

    assert est_dict["converged"] is True
    assert np.isclose(est_k, exact_k, rtol=0.05)


def test_estimate_condition_number_ill_conditioned():
    """Ill-conditioned matrix (kappa > 1e4) should be detected and flagged."""
    rng = np.random.RandomState(42)
    X = rng.randn(200, 4)
    # Create near multi-collinearity with small noise
    X[:, 3] = X[:, 0] * 2.0 + X[:, 1] * 0.5 + 1e-9 * rng.randn(200)

    exact_k = exact_condition_number(X)
    est_dict = estimate_condition_number(X, epsilon=1e-6)

    assert est_dict["diagnostics"]["ill_conditioned"] is True
    assert exact_k > 1e4


def test_condition_number_invalid_inputs():
    """Handling non-finite/NaN inputs gracefully."""
    X_nan = np.array([[1.0, np.nan], [2.0, 4.0]])
    with pytest.raises(ValueError, match="non-numeric"):
        exact_condition_number(X_nan)

    with pytest.raises(ValueError, match="non-numeric"):
        estimate_condition_number(X_nan)


# =====================================================================
# 2. EQUIVALENCE TESTS: FAST VS CLASSICAL ENGLE-GRANGER
# =====================================================================

def test_engle_granger_fast_vs_classical_equivalence():
    """Fast QR OLS and Classical OLS should produce equivalent test statistics and hedge ratios."""
    rng = np.random.RandomState(123)
    N = 500
    x = np.cumsum(rng.randn(N))
    y = 2.5 * x + 10.0 + rng.randn(N)

    res_class = engle_granger_test(y, x)
    res_fast = fast_engle_granger_test(y, x, epsilon=1e-6)

    # Test statistic equivalence
    assert np.isclose(res_class["test_statistic"], res_fast["test_statistic"], rtol=1e-4)
    # Hedge ratio equivalence
    assert np.isclose(res_class["hedge_ratio"][0], res_fast["hedge_ratio"][0], rtol=1e-4)
    # Intercept equivalence
    assert np.isclose(res_class["intercept"], res_fast["intercept"], rtol=1e-4)
    # Decision agreement
    assert res_class["cointegrated"] == res_fast["cointegrated"]


# =====================================================================
# 3. STATISTICAL VALIDATION TESTS (CASES A - E)
# =====================================================================

def test_synthetic_cases_statistical_behavior():
    """Validates statistical test behavior across synthetic cases A through E."""
    cases = generate_synthetic_cases(N=1000, seed=42)

    # Case A: Independent random walks -> Should NOT be cointegrated
    y_a, x_a = cases["Case A (Independent Random Walks)"]
    res_a = fast_engle_granger_test(y_a, x_a)
    assert res_a["cointegrated"] is False

    # Case B: Genuinely cointegrated -> SHOULD be cointegrated
    y_b, x_b = cases["Case B (Genuinely Cointegrated)"]
    res_b = fast_engle_granger_test(y_b, x_b)
    assert res_b["cointegrated"] is True
    assert np.isclose(res_b["hedge_ratio"][0], 1.5, atol=0.1)

    # Case E: High correlation BUT non-stationary residuals -> Proves Correlation != Cointegration
    y_e, x_e = cases["Case E (High Correlation, NO Cointegration)"]
    corr_e = float(np.corrcoef(y_e, x_e)[0, 1])
    res_e = fast_engle_granger_test(y_e, x_e)

    assert corr_e > 0.90  # Extremely high correlation
    assert res_e["cointegrated"] is False  # But NOT cointegrated!


# =====================================================================
# 4. DATA LEAKAGE & TRUNCATION INVARIANCE TESTS
# =====================================================================

def test_walk_forward_truncation_invariance():
    """Truncation invariance test: truncating future observations must NOT alter historical cointegration decisions."""
    rng = np.random.RandomState(99)
    N = 1000
    x1 = np.cumsum(rng.randn(N))
    x2 = 1.8 * x1 + rng.randn(N)
    x3 = np.cumsum(rng.randn(N))

    df = pd.DataFrame({"A": x2, "B": x1, "C": x3})

    # Full walk-forward
    res_full = walk_forward_cointegration(df, train_window=504, rebalance_freq=21)

    # Truncated walk-forward (only first 700 bars)
    df_trunc = df.iloc[:700]
    res_trunc = walk_forward_cointegration(df_trunc, train_window=504, rebalance_freq=21)

    # Historical values up to bar 700 must be bit-identical
    common_idx = res_trunc["index"]
    pd.testing.assert_series_equal(res_full["spread"].loc[common_idx], res_trunc["spread"].loc[common_idx])
    pd.testing.assert_series_equal(res_full["is_cointegrated"].loc[common_idx], res_trunc["is_cointegrated"].loc[common_idx])


# =====================================================================
# 5. DETERMINISM & STABILITY TESTS
# =====================================================================

def test_determinism_repeated_runs():
    """Repeated runs on identical inputs must yield deterministic results."""
    rng = np.random.RandomState(77)
    x = np.cumsum(rng.randn(300))
    y = 0.8 * x + rng.randn(300)

    res1 = fast_engle_granger_test(y, x, epsilon=1e-6)
    res2 = fast_engle_granger_test(y, x, epsilon=1e-6)

    assert res1["test_statistic"] == res2["test_statistic"]
    assert res1["p_value"] == res2["p_value"]
    assert np.array_equal(res1["residual"], res2["residual"])


def test_precision_scaling_sensitivity():
    """Testing sensitivity across varying epsilon parameters."""
    df_benchmark = benchmark_precision_scaling(epsilons=[1e-2, 1e-4, 1e-6, 1e-8])
    assert len(df_benchmark) == 4
    # Relative error should remain tiny across reasonable epsilons
    assert (df_benchmark["Rel Error"] < 1e-3).all()
