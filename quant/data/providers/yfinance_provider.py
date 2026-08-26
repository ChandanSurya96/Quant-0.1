"""Fail-closed yfinance market data provider with caching and deterministic fallbacks."""

from __future__ import annotations

import hashlib
import time
import warnings
import numpy as np
import pandas as pd
import yfinance as yf

from ...core.enums import ExecutionMode
from ...core.exceptions import FailClosedDataError, ModeViolationError
from ..base import AbstractMarketDataProvider
from ..cache import MarketDataCache
from ..validation import DataValidationGate


class YFinanceProvider(AbstractMarketDataProvider):
    """Provides market data via yfinance with execution-mode-aware fail-closed validation."""

    def __init__(
        self,
        retries: int = 2,
        pause: float = 2.0,
        allow_synthetic_fallback: bool = False,
        use_cache: bool = True,
    ) -> None:
        self._retries = retries
        self._pause = pause
        self._allow_synthetic_fallback = allow_synthetic_fallback
        self._use_cache = use_cache
        self._cache = MarketDataCache() if use_cache else None

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
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")

        # 1. Check on-disk cache
        if self._cache is not None:
            cached_df = self._cache.get(universe, start_str, end_str, self.provider_name)
            if cached_df is not None and not cached_df.empty:
                return DataValidationGate.validate_matrix(cached_df, universe=universe, mode=mode)

        # 2. Live fetch
        series_dict: dict[str, pd.Series] = {}
        last_error = None

        for attempt in range(1, self._retries + 1):
            try:
                df_batch = yf.download(
                    universe,
                    start=start_str,
                    end=end_str,
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

        # Check if complete universe was retrieved
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
                "SYNTHETIC / NON-PERFORMANCE EVIDENCE: yfinance rate-limited; generating synthetic geometric random walks.",
                UserWarning,
                stacklevel=2,
            )
            dates = pd.date_range(start=start_str, end=end_str, freq="B")
            for t in universe:
                seed = int(hashlib.sha256(t.encode("utf-8")).hexdigest()[:8], 16)
                rng = np.random.default_rng(seed)
                rets = rng.normal(0.0002, 0.015, size=len(dates))
                prices = 100.0 * np.exp(np.cumsum(rets))
                series_dict[t] = pd.Series(prices, index=dates)

        df_aligned = pd.DataFrame(series_dict).ffill().dropna(how="all")
        validated_df = DataValidationGate.validate_matrix(df_aligned, universe=universe, mode=mode)

        # Cache on successful download
        if self._cache is not None and not missing:
            self._cache.put(validated_df, universe, start_str, end_str, self.provider_name)

        return validated_df

    def fetch_ticker(
        self,
        ticker: str,
        lookback_years: int = 10,
        mode: ExecutionMode = ExecutionMode.RESEARCH,
    ) -> pd.DataFrame:
        """Fetch OHLCV DataFrame for a single ticker with fail-closed validation."""
        end = pd.Timestamp.now("UTC").normalize()
        start = end - pd.DateOffset(years=lookback_years)
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")

        df = pd.DataFrame()
        last_error = None

        for attempt in range(1, self._retries + 1):
            try:
                df = yf.download(
                    ticker,
                    start=start_str,
                    end=end_str,
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
