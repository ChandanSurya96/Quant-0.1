"""Price normalization module for Yale / Gatev Pairs Trading."""

from __future__ import annotations

import numpy as np
import pandas as pd


def normalize_price_series(prices: pd.DataFrame) -> pd.DataFrame:
    """Normalizes price series such that initial value equals 1.0 at t=0.

    Formula:
        P_{s,t} = P'_{s,t} / P'_{s,0}

    Represents the cumulative return of a $1 investment in asset s.
    """
    if prices.empty:
        return prices.copy()

    # Identify first valid (non-null and non-zero) price per column
    first_prices = prices.iloc[0].copy()
    for col in prices.columns:
        valid = prices[col].dropna()
        if not valid.empty and valid.iloc[0] > 0:
            first_prices[col] = valid.iloc[0]
        else:
            first_prices[col] = 1.0

    normalized = prices.div(first_prices, axis=1)
    return normalized
