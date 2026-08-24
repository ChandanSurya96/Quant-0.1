"""Universe management and point-in-time liquidity filtering for Pairs Trading."""

from __future__ import annotations

import numpy as np
import pandas as pd


def filter_universe_liquidity(
    prices: pd.DataFrame,
    volumes: pd.DataFrame | None = None,
    percentile_threshold: float = 0.0,
) -> list[str]:
    """Applies point-in-time volume/liquidity filtering prior to pair formation.

    Parameters:
        prices: Asset price DataFrame over formation window.
        volumes: Asset volume DataFrame over formation window.
        percentile_threshold: e.g. 0.50 for L50, 0.75 for L75.

    Returns:
        List of eligible tickers.
    """
    eligible = list(prices.columns)

    # 1. Filter out tickers with all-nan or zero prices
    valid_cols = []
    for col in eligible:
        p_col = prices[col].dropna()
        if len(p_col) >= len(prices) * 0.8 and (p_col > 0).all():
            valid_cols.append(col)

    if volumes is None or percentile_threshold <= 0.0 or not valid_cols:
        return valid_cols

    # 2. Point-in-time liquidity ranking on the week prior to formation end
    recent_vol = volumes[valid_cols].iloc[-5:].mean(axis=0)
    cutoff = float(np.percentile(recent_vol.dropna(), percentile_threshold * 100.0))
    liquid_cols = [c for c in valid_cols if recent_vol.get(c, 0.0) >= cutoff]
    return liquid_cols


def filter_same_sector_pairs(
    pairs: list[tuple[str, str]],
    sector_map: dict[str, str],
) -> list[tuple[str, str]]:
    """Restricts eligible pairs to constituents belonging to the same sector (R20)."""
    restricted = []
    for t1, t2 in pairs:
        sec1 = sector_map.get(t1)
        sec2 = sector_map.get(t2)
        if sec1 is not None and sec2 is not None and sec1 == sec2:
            restricted.append((t1, t2))
    return restricted
