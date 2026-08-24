"""Holding weight drift and mark-to-market calculations."""

from __future__ import annotations


def calculate_market_values(
    holdings: dict[str, float],
    prices: dict[str, float],
) -> dict[str, float]:
    """Calculates mark-to-market dollar value for each holding.

    Market Value: V_i = Q_i * P_i.
    For short positions (Q_i < 0), market value is negative liability.
    """
    market_values: dict[str, float] = {}
    for sym, shares in holdings.items():
        price = prices.get(sym, 0.0)
        market_values[sym] = shares * price
    return market_values


def calculate_portfolio_nav(
    cash: float,
    holdings: dict[str, float],
    prices: dict[str, float],
) -> float:
    """Calculates total mark-to-market Net Asset Value (NAV).

    NAV = Cash + sum(Shares_i * Price_i).
    """
    mvs = calculate_market_values(holdings, prices)
    return cash + sum(mvs.values())


def calculate_realized_weights(
    cash: float,
    holdings: dict[str, float],
    prices: dict[str, float],
) -> tuple[float, dict[str, float]]:
    """Calculates current NAV and natural realized portfolio weights.

    Realized Weight: w_i = (Q_i * P_i) / NAV.
    Returns (nav, realized_weights).
    """
    nav = calculate_portfolio_nav(cash, holdings, prices)
    if abs(nav) < 1e-8:
        return nav, {sym: 0.0 for sym in holdings}

    mvs = calculate_market_values(holdings, prices)
    realized_weights = {sym: mv / nav for sym, mv in mvs.items()}
    return nav, realized_weights
