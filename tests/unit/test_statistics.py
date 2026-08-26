"""Unit tests for quant.statistics uncertainty engine."""

import math

import numpy as np
import pandas as pd
import pytest

from quant.statistics.sharpe import (
    calculate_sharpe_statistics,
    compute_deflated_sharpe_ratio,
    norm_cdf,
    norm_ppf,
)


def test_norm_cdf_and_ppf_inverses():
    for p in [0.01, 0.05, 0.50, 0.95, 0.99]:
        z = norm_ppf(p)
        recovered_p = norm_cdf(z)
        assert pytest.approx(recovered_p, abs=1e-5) == p


def test_sharpe_statistics_calculation_with_series_rf():
    np.random.seed(42)
    dates = pd.date_range("2020-01-01", periods=1000, freq="B")
    rets = pd.Series(np.random.normal(0.0005, 0.00945, size=1000), index=dates)
    rf_series = pd.Series(0.03 / 252.0, index=dates)

    stats = calculate_sharpe_statistics(rets, rf_daily=rf_series, periods_per_year=252)

    assert stats["n_observations"] == 1000
    assert stats["gross_sharpe"] > 0
    assert stats["excess_sharpe"] > 0
    # Mandatory assertion: non-zero rf must make excess Sharpe strictly less than gross Sharpe
    assert stats["excess_sharpe"] < stats["gross_sharpe"]
    assert abs(stats["gross_sharpe"] - stats["excess_sharpe"]) > 0.01
    assert stats["sharpe_se"] > 0
    assert stats["sharpe_t_stat"] > 0
    assert stats["sharpe_ci_lower_95"] < stats["excess_sharpe"] < stats["sharpe_ci_upper_95"]


def test_deflated_sharpe_ratio_non_saturation():
    """Verifies DSR does not saturate at float 1.0 or 0.0 for realistic candidate parameters."""
    dsr = compute_deflated_sharpe_ratio(
        observed_sharpe=0.6022,
        n_trials=29,
        var_trials=0.0125,
        skewness=-0.15,
        kurtosis=0.05,
        n_observations=1739,
    )
    # Expected value around 0.835 (not saturated at 1.0 or 0.0)
    assert 0.0 < dsr < 1.0
    assert not math.isclose(dsr, 1.0, abs_tol=1e-4)
    assert not math.isclose(dsr, 0.0, abs_tol=1e-4)
    assert pytest.approx(dsr, abs=0.05) == 0.835


def test_deflated_sharpe_ratio_known_answer():
    # If observed Sharpe is exactly equal to expected maximum benchmark, DSR should be 0.50
    euler_mascheroni = 0.5772156649
    n_trials = 10
    var_trials = 0.04  # std = 0.20
    p1 = 1.0 - 1.0 / n_trials
    p2 = 1.0 - 1.0 / (n_trials * math.e)
    benchmark_sr = math.sqrt(var_trials) * ((1.0 - euler_mascheroni) * norm_ppf(p1) + euler_mascheroni * norm_ppf(p2))

    dsr_at_benchmark = compute_deflated_sharpe_ratio(
        observed_sharpe=benchmark_sr,
        n_trials=n_trials,
        var_trials=var_trials,
        skewness=0.0,
        kurtosis=0.0,
        n_observations=1000,
    )
    assert pytest.approx(dsr_at_benchmark, abs=1e-3) == 0.50
