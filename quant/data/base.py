"""Abstract base class for market data providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
import pandas as pd

from ..core.enums import ExecutionMode


class AbstractMarketDataProvider(ABC):
    """Abstract interface for all historical and live market data providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the data provider."""
        raise NotImplementedError

    @abstractmethod
    def fetch_daily_bars(
        self,
        universe: list[str],
        lookback_years: int = 10,
        mode: ExecutionMode = ExecutionMode.RESEARCH,
    ) -> pd.DataFrame:
        """Fetch aligned daily Close price matrix for a list of tickers.
        
        Must return a DataFrame with DateTime index and ticker columns.
        In PAPER and LIVE modes, implementations MUST fail closed on errors.
        """
        raise NotImplementedError

    @abstractmethod
    def fetch_ticker(
        self,
        ticker: str,
        lookback_years: int = 10,
        mode: ExecutionMode = ExecutionMode.RESEARCH,
    ) -> pd.DataFrame:
        """Fetch daily OHLCV DataFrame for a single ticker."""
        raise NotImplementedError


MarketDataProvider = AbstractMarketDataProvider
