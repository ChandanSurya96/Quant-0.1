"""Unit tests for Dynamic Carry Engine and Point-in-Time alignment."""

import numpy as np
import pandas as pd

from quant.factors.dynamic_carry import DynamicCarryEngine


def test_dynamic_carry_matrix_point_in_time_lag():
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    tickers = ["SPY", "TLT", "IEF", "UUP", "FXE", "FXY", "EWJ", "EFA", "EEM", "BNDX", "IGOV", "FXB"]
    df_close = pd.DataFrame(100.0, index=dates, columns=tickers)

    # Point-in-time alignment: Bar 0 should have 0.0 carry due to shift(1)
    carry_df = DynamicCarryEngine.compute_dynamic_carry_matrix(df_close)
    assert carry_df.shape == df_close.shape
    assert (carry_df.iloc[0] == 0.0).all()
    # Ensure no NaN values in carry matrix
    assert not carry_df.isna().any().any()


def test_dynamic_carry_cross_sectional_z_scores():
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    tickers = ["SPY", "TLT", "IEF", "UUP", "FXE", "FXY", "EWJ", "EFA", "EEM", "BNDX", "IGOV", "FXB"]
    df_close = pd.DataFrame(np.random.uniform(50, 150, (100, 12)), index=dates, columns=tickers)

    carry_df = DynamicCarryEngine.compute_dynamic_carry_matrix(df_close)
    z_scores = DynamicCarryEngine.get_cross_sectional_z_scores(carry_df, bar_idx=50)

    assert len(z_scores) == 12
    # Standardized z-score mean must be approximately 0.0
    assert abs(z_scores.mean()) < 1e-4
    # Standard deviation should be approx 1.0 (or 0 if constant)
    assert abs(z_scores.std(ddof=1) - 1.0) < 1e-3 or abs(z_scores.std(ddof=1)) < 1e-3
