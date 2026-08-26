"""Unit tests for CAND-011 Multi-Strategy Risk Ensemble."""

import numpy as np
import pandas as pd

from scripts.run_cand011_research import compute_performance_metrics, get_cand006_target_weights


def test_cand006_target_weights_deterministic():
    dates = pd.date_range("2020-01-01", periods=800, freq="D")
    tickers = ["SPY", "EWJ", "EFA", "EEM", "TLT", "IEF", "BNDX", "IGOV", "UUP", "FXE", "FXY", "FXB"]
    rng = np.random.default_rng(42)
    p_data = {t: 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, 800))) for t in tickers}
    df_close = pd.DataFrame(p_data, index=dates)

    tw_df = get_cand006_target_weights(df_close, start_idx=756)
    assert tw_df.shape == df_close.shape
    # Check that weights sum to approx 0 net (longs + shorts)
    row_sum = tw_df.iloc[-1].sum()
    assert abs(row_sum) < 0.1
    # Check long and short positions exist
    assert (tw_df.iloc[-1] > 0).sum() == 3
    assert (tw_df.iloc[-1] < 0).sum() == 3


def test_compute_performance_metrics():
    r = pd.Series([0.01, -0.005, 0.02, -0.01, 0.015] * 50)
    m = compute_performance_metrics(r)
    assert "sharpe" in m
    assert "cagr" in m
    assert "volatility" in m
    assert "max_drawdown" in m
    assert m["sharpe"] > 0
