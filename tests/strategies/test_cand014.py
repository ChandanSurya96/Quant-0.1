"""Unit tests for CAND-014 Regime-Conditional Momentum Research Engine."""

import numpy as np
import pandas as pd
import pytest
from scripts.run_cand014_research import (
    compute_metrics,
    compute_point_in_time_regime_multipliers,
)


def test_regime_multipliers_point_in_time_and_bounded():
    dates = pd.date_range("2014-01-01", periods=1000, freq="B")
    tickers = ["SPY", "TLT", "IEF", "FXE", "UUP", "EWJ"]
    rng = np.random.default_rng(42)
    
    # Generate synthetic price series
    prices = {}
    for t in tickers:
        r = rng.standard_normal(1000) * 0.01
        prices[t] = 100.0 * np.exp(np.cumsum(r))
    df_macro = pd.DataFrame(prices, index=dates)

    mult_dict = compute_point_in_time_regime_multipliers(df_macro, start_idx=300, rebalance_freq=21)
    
    assert "H1_TREND" in mult_dict
    assert "H2_BREADTH" in mult_dict
    assert "H3_VOL_REGIME" in mult_dict
    assert "H4_DISPERSION" in mult_dict
    assert "H5_COMPOSITE" in mult_dict

    for k, m_series in mult_dict.items():
        assert len(m_series) == 1000
        assert not m_series.isna().any()
        assert (m_series >= 0.0).all()
        assert (m_series <= 1.0).all()


def test_compute_metrics_accuracy():
    dates = pd.date_range("2020-01-01", periods=252, freq="B")
    # Constant 10 bps daily return series
    rets = pd.Series(0.0010, index=dates)
    m = compute_metrics(rets, turnover=5.0)
    
    assert m["sharpe"] > 0
    assert m["cagr"] > 0
    assert m["max_drawdown"] == 0.0
    assert m["turnover"] == 5.0
