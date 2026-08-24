"""Unit tests for fail-closed data architecture and validation gates."""

from __future__ import annotations

from unittest.mock import patch
import numpy as np
import pandas as pd
import pytest

from quant.core.enums import ExecutionMode
from quant.core.exceptions import AnomalyGapError, FailClosedDataError, ModeViolationError
from quant.data.providers.fixture_provider import HistoricalFixtureProvider
from quant.data.providers.yfinance_provider import YFinanceProvider
from quant.data.validation import DataValidationGate


# -------------------------------------------------- 1. DataValidationGate
def test_filter_vendor_artifacts_drops_zero_vol_flat_bars():
    dates = pd.date_range("2026-01-01", periods=5, freq="D")
    df = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 101.0, 102.0, 103.0],
            "High": [100.0, 101.0, 101.0, 102.0, 103.0],
            "Low": [100.0, 101.0, 101.0, 102.0, 103.0],
            "Close": [100.0, 101.0, 101.0, 102.0, 103.0],
            "Volume": [1000, 0, 0, 1500, 2000],  # 2nd and 3rd are artifacts
        },
        index=dates,
    )
    cleaned, dropped = DataValidationGate.filter_vendor_artifacts(df)
    assert len(cleaned) == 3
    assert len(dropped) == 2
    assert "2026-01-02" in dropped
    assert "2026-01-03" in dropped


def test_detect_anomalies_flags_exceeding_threshold():
    dates = pd.date_range("2026-01-01", periods=4, freq="D")
    # Day 3 drops by 40% (e.g. unadjusted demerger)
    close = pd.Series([100.0, 101.0, 60.0, 61.0], index=dates)
    anomalies = DataValidationGate.detect_anomalies(close, threshold=0.15)
    assert len(anomalies) == 1
    assert anomalies[0]["date"] == "2026-01-03"
    assert pytest.approx(anomalies[0]["return"], abs=1e-3) == -0.4059


def test_validate_matrix_empty_fails_closed():
    empty_df = pd.DataFrame()
    with pytest.raises(FailClosedDataError, match="Market data payload is empty"):
        DataValidationGate.validate_matrix(empty_df, universe=["SPY"])


def test_validate_matrix_missing_universe_ticker_fails_closed():
    dates = pd.date_range("2026-01-01", periods=20, freq="D")
    df = pd.DataFrame({"SPY": np.linspace(400, 410, 20)}, index=dates)
    with pytest.raises(FailClosedDataError, match="missing 1 requested universe tickers: \\['TLT'\\]"):
        DataValidationGate.validate_matrix(df, universe=["SPY", "TLT"])


def test_validate_matrix_paper_mode_unhandled_gap_fails_closed():
    dates = pd.date_range("2026-01-01", periods=20, freq="D")
    prices = np.linspace(100, 105, 20)
    prices[10] = 50.0  # -50% unadjusted price gap anomaly
    df = pd.DataFrame({"SPY": prices}, index=dates)
    
    with pytest.raises(AnomalyGapError, match=r"Unhandled price anomaly gap"):
        DataValidationGate.validate_matrix(
            df, universe=["SPY"], mode=ExecutionMode.PAPER, threshold=0.15
        )


# ------------------------------------------------ 2. HistoricalFixtureProvider
def test_fixture_provider_loads_existing_fixture():
    provider = HistoricalFixtureProvider()
    df = provider.fetch_ticker("TCS.NS")
    assert not df.empty
    assert "Close" in df.columns
    assert len(df) > 100


def test_fixture_provider_missing_ticker_fails_closed():
    provider = HistoricalFixtureProvider()
    with pytest.raises(FailClosedDataError, match="Fixture file not found"):
        provider.fetch_ticker("NONEXISTENT_TICKER_XYZ")


def test_fixture_provider_fetch_daily_bars():
    provider = HistoricalFixtureProvider()
    # Uses existing pinned fixtures TCS.NS and TMPV.NS
    df = provider.fetch_daily_bars(["TCS.NS", "TMPV.NS"], mode=ExecutionMode.RESEARCH)
    assert not df.empty
    assert "TCS.NS" in df.columns
    assert "TMPV.NS" in df.columns


# ---------------------------------------------------- 3. YFinanceProvider
def test_yfinance_provider_paper_mode_rejects_synthetic_fallback():
    provider = YFinanceProvider(allow_synthetic_fallback=True)
    with pytest.raises(ModeViolationError, match="Synthetic fallback is strictly forbidden in PAPER mode"):
        provider.fetch_daily_bars(["SPY"], mode=ExecutionMode.PAPER)


def test_yfinance_provider_live_mode_rejects_synthetic_fallback():
    provider = YFinanceProvider(allow_synthetic_fallback=True)
    with pytest.raises(ModeViolationError, match="Synthetic fallback is strictly forbidden in LIVE mode"):
        provider.fetch_daily_bars(["SPY"], mode=ExecutionMode.LIVE)


def test_yfinance_provider_fail_closed_on_empty_download():
    provider = YFinanceProvider(retries=1, allow_synthetic_fallback=False)
    # Mock yf.download to return empty DataFrame
    with patch("yfinance.download", return_value=pd.DataFrame()):
        with pytest.raises(FailClosedDataError, match="yfinance failed to fetch market data"):
            provider.fetch_daily_bars(["SPY"], mode=ExecutionMode.PAPER)
