"""Unit tests asserting fail-closed data behavior on missing or rate-limited market data."""

from unittest.mock import patch
import pandas as pd
import pytest
from markov2.universe_data import fetch_universe
from quant.core.exceptions import FailClosedDataError


def test_fetch_universe_fails_closed_by_default_on_empty_download():
    # When yfinance returns empty payload, default allow_synthetic_fallback=False must raise FailClosedDataError
    with patch("yfinance.download", return_value=pd.DataFrame()):
        with pytest.raises(FailClosedDataError, match="Ingestion failed closed"):
            fetch_universe(["SPY", "TLT"], allow_synthetic_fallback=False)


def test_fetch_universe_explicit_synthetic_generates_warning():
    with patch("yfinance.download", return_value=pd.DataFrame()):
        with pytest.warns(UserWarning, match="SYNTHETIC / NON-PERFORMANCE EVIDENCE"):
            df = fetch_universe(["SPY", "TLT"], years=1, allow_synthetic_fallback=True)
            assert not df.empty
            assert "SPY" in df.columns
            assert "TLT" in df.columns
