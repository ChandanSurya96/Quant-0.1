"""Portfolio sizing and discrete share calculation utilities."""

from __future__ import annotations

import math


def target_weights_to_shares(
    target_weights: dict[str, float],
    nav: float,
    prices: dict[str, float],
    discrete_shares: bool = True,
    min_tradeable_notional: float = 10.0,
    lot_size: int = 1,
) -> dict[str, float]:
    """Converts target portfolio weights to physical target share quantities.

    Target Dollar Allocation: D_i = w_i * NAV
    Target Shares: Q_i = D_i / P_i (rounded to discrete integer shares if discrete_shares=True)
    
    Supports negative target weights for direct ETF shorting.
    """
    target_shares: dict[str, float] = {}
    for sym, weight in target_weights.items():
        if sym not in prices:
            continue
        price = prices[sym]
        if price <= 0:
            target_shares[sym] = 0.0
            continue

        target_dollars = weight * nav
        if abs(target_dollars) < min_tradeable_notional:
            target_shares[sym] = 0.0
            continue

        raw_shares = target_dollars / price

        if discrete_shares:
            if raw_shares > 0:
                shares = int(math.floor(raw_shares / lot_size)) * lot_size
            else:
                shares = int(math.ceil(raw_shares / lot_size)) * lot_size
            target_shares[sym] = float(shares)
        else:
            target_shares[sym] = float(raw_shares)

    return target_shares
