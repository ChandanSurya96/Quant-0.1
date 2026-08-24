"""Fail-closed yfinance market data provider."""

from __future__ import annotations

import time
import warnings
import numpy as np
import pandas as pd
import yfinance as yf

from ...core.enums import ExecutionMode
from ...core.exceptions import FailClosedDataError, ModeViolationError
from ..base import AbstractMarketDataProvider
from ..validation import DataValidationGate


class YFinanceProvider(AbstractMarketDataProvider):
    """Provides market data via yfinance with execution-mode-aware fail-closed validation."""

    def __init__(
        self,
        retries: int = 2,
        pause: float = 2.0,
        allow_synthetic_fallback: bool = False,
    ) -> None:
        self._retries = retries
        self._pause = pause
        self._allow_synthetic_fallback = allow_synthetic_fallback

    @property
    def provider_name(self) -> str:
        return "YFinanceProvider"

    def fetch_daily_bars(
        self,
        universe: list[str],
        lookback_years: int = 10,
        mode: ExecutionMode = ExecutionMode.RESEARCH,
    ) -> pd.DataFrame:
        """Fetch aligned Close price matrix for universe with fail-closed validation."""
        if mode in (ExecutionMode.PAPER, ExecutionMode.LIVE) and self._allow_synthetic_fallback:
            raise ModeViolationError(
                f"Synthetic fallback is strictly forbidden in {mode.value} mode."
            )

        end = pd.Timestamp.now("UTC").normalize()
        start = end - pd.DateOffset(years=lookback_years)

        series_dict: dict[str, pd.Series] = {}
        last_error = None

        for attempt in range(1, self._retries + 1):
            try:
                df_batch = yf.download(
                    universe,
                    start=start.strftime("%Y-%m-%d"),
                    end=end.strftime("%Y-%m-%d"),
                    progress=False,
                    auto_adjust=True,
                )
                if not df_batch.empty:
                    if isinstance(df_batch.columns, pd.MultiIndex):
                        close_df = (
                            df_batch["Close"]
                            if "Close" in df_batch.columns.get_level_values(0)
                            else df_batch
                        )
                    else:
                        close_df = df_batch

                    for t in universe:
                        if t in close_df.columns:
                            s = close_df[t].dropna()
                            if not s.empty:
                                series_dict[t] = s
                    if len(series_dict) == len(universe):
                        break
            except Exception as exc:  # noqa: BLE001
                last_error = exc

            if attempt < self._retries and len(series_dict) < len(universe):
                time.sleep(self._pause)

        # Check if we have complete universe
        missing = [t for t in universe if t not in series_dict]
        if missing or not series_dict:
            if mode in (ExecutionMode.PAPER, ExecutionMode.LIVE) or not self._allow_synthetic_fallback:
                err_msg = (
                    f"yfinance failed to fetch market data for {missing or universe} "
                    f"after {self._retries} attempts (last error: {last_error}). Ingestion failed closed."
                )
                raise FailClosedDataError(err_msg)

            # RESEARCH ONLY explicit fallback
            warnings.warn(
                "RESEARCH ONLY: yfinance rate-limited; generating synthetic geometric random walks.",
                UserWarning,
                stacklevel=2,
            )
            dates = pd.date_range(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), freq="B")
            for t in universe:
                np.random.seed(abs(hash(t)) % (2**32))
                rets = np.random.normal(0.0002, 0.015, size=len(dates))
                prices = 100.0 * np.exp(np.cumsum(rets))
                series_dict[t] = pd.Series(prices, index=dates)

        df_aligned = pd.DataFrame(series_dict).ffill().dropna(how="all")
        return DataValidationGate.validate_matrix(df_aligned, universe=universe, mode=mode)

    def fetch_ticker(
        self,
        ticker: str,
        lookback_years: int = 10,
        mode: ExecutionMode = ExecutionMode.RESEARCH,
    ) -> pd.DataFrame:
        """Fetch OHLCV DataFrame for a single ticker with fail-closed validation."""
        end = pd.Timestamp.now("UTC").normalize()
        start = end - pd.DateOffset(years=lookback_years)

        df = pd.DataFrame()
        last_error = None

        for attempt in range(1, self._retries + 1):
            try:
                df = yf.download(
                    ticker,
                    start=start.strftime("%Y-%m-%d"),
                    end=end.strftime("%Y-%m-%d"),
                    progress=False,
                    auto_adjust=True,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc

            if not df.empty:
                break
            if attempt < self._retries:
                time.sleep(self._pause)

        if df.empty:
            raise FailClosedDataError(
                f"yfinance returned no data for {ticker!r} after {self._retries} attempts "
                f"(last error: {last_error}). Ingestion failed closed."
            )

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        keep = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
        df_clean = df[keep].dropna(subset=["Close"]).copy()

        filtered_df, _ = DataValidationGate.filter_vendor_artifacts(df_clean)
        return filtered_df
