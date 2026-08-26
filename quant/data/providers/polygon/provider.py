"""Fail-closed Polygon.io market data provider."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd

from ....core.enums import ExecutionMode
from ....core.exceptions import FailClosedDataError
from ....observability.health import ComponentHealth, check_data_health
from ...base import AbstractMarketDataProvider
from ...validation import DataValidationGate
from .client import PolygonClientProtocol, PolygonRestClient
from .errors import PolygonError, PolygonNoDataError
from .mapper import PolygonMapper
from .models import PolygonConfig


class PolygonProvider(AbstractMarketDataProvider):
    """Provides market data via Polygon.io with execution-mode-aware fail-closed validation.

    Unlike YFinanceProvider this provider never fabricates data. There is no synthetic
    fallback in any mode: a Polygon failure is always an ingestion failure.
    """

    def __init__(
        self,
        config: PolygonConfig | None = None,
        client: PolygonClientProtocol | None = None,
    ) -> None:
        self.config = config or PolygonConfig()
        if client is None:
            self.config.validate_credentials()
        self.client = client or PolygonRestClient(self.config)
        self._last_fetch_at: datetime | None = None
        self._last_error: str | None = None

    @property
    def provider_name(self) -> str:
        return "PolygonProvider"

    def fetch_daily_bars(
        self,
        universe: list[str],
        lookback_years: int = 10,
        mode: ExecutionMode = ExecutionMode.RESEARCH,
    ) -> pd.DataFrame:
        """Fetch aligned Close price matrix for universe with fail-closed validation."""
        if not universe:
            raise FailClosedDataError("Polygon requires a non-empty universe. Ingestion failed closed.")

        start, end = self._window(lookback_years)

        series_dict: dict[str, pd.Series] = {}
        failures: dict[str, str] = {}

        for position, ticker in enumerate(universe):
            if position > 0 and self.config.pace_seconds > 0:
                time.sleep(self.config.pace_seconds)
            try:
                bars = self.client.fetch_daily_aggregates(ticker, start, end)
            except PolygonError as exc:
                failures[ticker] = str(exc)
                continue

            series = PolygonMapper.to_close_series(bars)
            if series.empty:
                failures[ticker] = "Polygon returned zero aggregate bars."
                continue
            series_dict[ticker] = series

        missing = [t for t in universe if t not in series_dict]
        if missing:
            self._record_failure(f"missing {missing}")
            detail = "; ".join(f"{t}: {failures.get(t, 'no bars returned')}" for t in missing)
            raise FailClosedDataError(
                f"Polygon failed to fetch market data for {missing} "
                f"({detail}). Ingestion failed closed."
            )

        df_aligned = pd.DataFrame(series_dict).ffill().dropna(how="all")
        validated = DataValidationGate.validate_matrix(df_aligned, universe=universe, mode=mode)
        self._record_success()
        return validated

    def fetch_ticker(
        self,
        ticker: str,
        lookback_years: int = 10,
        mode: ExecutionMode = ExecutionMode.RESEARCH,
    ) -> pd.DataFrame:
        """Fetch OHLCV DataFrame for a single ticker with fail-closed validation."""
        start, end = self._window(lookback_years)

        try:
            bars = self.client.fetch_daily_aggregates(ticker, start, end)
        except PolygonError as exc:
            self._record_failure(str(exc))
            raise FailClosedDataError(
                f"Polygon failed to fetch {ticker!r} ({exc}). Ingestion failed closed."
            ) from exc

        if not bars:
            self._record_failure(f"no bars for {ticker!r}")
            raise PolygonNoDataError(
                f"Polygon returned no aggregate bars for {ticker!r} between {start} and {end}. "
                "Ingestion failed closed."
            )

        df = PolygonMapper.to_ohlcv_frame(bars).dropna(subset=["Close"])
        filtered_df, _ = DataValidationGate.filter_vendor_artifacts(df)

        if filtered_df.empty:
            self._record_failure(f"all bars for {ticker!r} were vendor artifacts")
            raise FailClosedDataError(
                f"Every Polygon bar for {ticker!r} was a vendor artifact. Ingestion failed closed."
            )

        self._record_success()
        return filtered_df

    def check_health(self) -> ComponentHealth:
        """Returns normalized ComponentHealth for the Polygon data provider."""
        return check_data_health(
            last_fetch_time=self._last_fetch_at,
            is_stale=False,
            provider_available=self._last_error is None,
            details={"provider": self.provider_name, "last_error": self._last_error},
        )

    @staticmethod
    def _window(lookback_years: int) -> tuple[str, str]:
        """Returns the inclusive ISO date window Polygon expects for a lookback in years."""
        end = pd.Timestamp.now("UTC").normalize()
        start = end - pd.DateOffset(years=lookback_years)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    def _record_success(self) -> None:
        """Marks the most recent fetch as successful for health reporting."""
        self._last_fetch_at = datetime.now(timezone.utc)
        self._last_error = None

    def _record_failure(self, error: str) -> None:
        """Records the most recent ingestion failure for health reporting."""
        self._last_error = error
