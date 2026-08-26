"""Offline historical fixture market data provider for tests and research."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ...core.enums import ExecutionMode
from ...core.exceptions import FailClosedDataError
from ..base import AbstractMarketDataProvider
from ..validation import DataValidationGate

DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "tests" / "fixtures"


class HistoricalFixtureProvider(AbstractMarketDataProvider):
    """Provides offline market data from pinned CSV fixtures."""

    def __init__(self, fixtures_dir: Path | str | None = None) -> None:
        self._dir = Path(fixtures_dir) if fixtures_dir else DEFAULT_FIXTURES_DIR

    @property
    def provider_name(self) -> str:
        return "HistoricalFixtureProvider"

    def fetch_ticker(
        self,
        ticker: str,
        lookback_years: int = 10,
        mode: ExecutionMode = ExecutionMode.RESEARCH,
    ) -> pd.DataFrame:
        """Load single ticker OHLCV from fixture directory."""
        csv_path = self._dir / f"{ticker}.csv"
        if not csv_path.exists():
            # Try without .NS or suffixes
            alt_path = self._dir / f"{ticker.split('.')[0]}.csv"
            if alt_path.exists():
                csv_path = alt_path
            else:
                raise FailClosedDataError(f"Fixture file not found for ticker {ticker!r} at {csv_path}")

        try:
            df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        except Exception as exc:
            raise FailClosedDataError(f"Failed to read fixture CSV {csv_path}: {exc}") from exc

        if df.empty:
            raise FailClosedDataError(f"Fixture CSV {csv_path} is empty.")

        filtered_df, _ = DataValidationGate.filter_vendor_artifacts(df)
        return filtered_df

    def fetch_daily_bars(
        self,
        universe: list[str],
        lookback_years: int = 10,
        mode: ExecutionMode = ExecutionMode.RESEARCH,
    ) -> pd.DataFrame:
        """Load multiple tickers and align Close prices."""
        series_dict = {}
        for ticker in universe:
            df = self.fetch_ticker(ticker, lookback_years=lookback_years, mode=mode)
            if "Close" not in df.columns:
                raise FailClosedDataError(f"Fixture for {ticker!r} missing 'Close' column.")
            series_dict[ticker] = df["Close"]

        aligned = pd.DataFrame(series_dict).ffill().dropna(how="all")
        return DataValidationGate.validate_matrix(aligned, universe=universe, mode=mode)
