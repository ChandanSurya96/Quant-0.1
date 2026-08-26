"""Abstract base class for quantitative trading strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd


class AbstractStrategy(ABC):
    """Abstract strategy interface.

    A strategy answers strictly: 'What should I own?'
    It outputs target portfolio weights and has zero order-placement authority.
    """

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Unique strategy identifier."""
        raise NotImplementedError

    @abstractmethod
    def generate_target_weights(self, close_df: pd.DataFrame) -> pd.DataFrame:
        """Generates target portfolio weight DataFrame across time."""
        raise NotImplementedError

    def generate_target_portfolio(
        self,
        close_df: pd.DataFrame,
        as_of_date: Any = None,
    ) -> Any:
        """Generates point-in-time TargetPortfolio."""
        raise NotImplementedError


BaseStrategy = AbstractStrategy
