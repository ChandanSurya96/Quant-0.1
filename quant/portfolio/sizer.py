"""Portfolio sizing and share calculation utilities."""

from __future__ import annotations


def target_weights_to_shares(
    target_weights: dict[str, float],
    nav: float,
    prices: dict[str, float],
) -> dict[str, float]:
    """Converts target portfolio weights to physical target share quantities.

    Target Dollar Allocation: D_i = w_i * NAV
    Target Shares: Q_i = D_i / P_i
    
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
        target_shares[sym] = target_dollars / price
    return target_shares
