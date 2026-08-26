"""Unit tests for quant.statistics uncertainty engine."""

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


def test_sharpe_statistics_calculation():
    np.random.seed(42)
    # Generate 1000 daily return bars (ann ret ~ 10%, ann vol ~ 15%)
    rets = pd.Series(np.random.normal(0.0004, 0.00945, size=1000))
    stats = calculate_sharpe_statistics(rets, rf_daily=0.02 / 252.0, periods_per_year=252)

    assert stats["n_observations"] == 1000
    assert stats["gross_sharpe"] > 0
    assert stats["excess_sharpe"] > 0
    assert stats["sharpe_se"] > 0
    assert stats["sharpe_t_stat"] > 0
    assert stats["sharpe_ci_lower_95"] < stats["excess_sharpe"] < stats["sharpe_ci_upper_95"]


def test_deflated_sharpe_ratio():
    dsr = compute_deflated_sharpe_ratio(
        observed_sharpe=0.55,
        n_trials=10,
        var_trials=0.01,
        skewness=0.0,
        kurtosis=0.0,
        n_observations=1000,
    )
    assert 0.0 <= dsr <= 1.0
    assert dsr > 0.50
