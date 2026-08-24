"""Translation mapper between Quant domain models and Interactive Brokers representation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ...core.enums import OrderSide, OrderStatus, OrderType
from ...core.interfaces import Fill, Holding, Order, PortfolioState
from .models import IBKRExecutionRecord, IBKROrderRecord


class IBKRMapper:
    """Translates between domain interfaces and IBKR representations."""

    IBKR_STATUS_MAP: dict[str, OrderStatus] = {
        "ApiPending": OrderStatus.SUBMITTED,
        "PendingSubmit": OrderStatus.SUBMITTED,
        "PreSubmitted": OrderStatus.SUBMITTED,
        "Submitted": OrderStatus.SUBMITTED,
        "PartiallyFilled": OrderStatus.PARTIALLY_FILLED,
        "Filled": OrderStatus.FILLED,
        "PendingCancel": OrderStatus.CANCELLED,
        "Cancelled": OrderStatus.CANCELLED,
        "ApiCancelled": OrderStatus.CANCELLED,
        "Inactive": OrderStatus.REJECTED,
    }

    @classmethod
    def to_domain_order_status(cls, ibkr_status: str) -> OrderStatus:
        """Maps an IBKR order status string to domain OrderStatus. Unrecognized values map to UNKNOWN."""
        return cls.IBKR_STATUS_MAP.get(ibkr_status, OrderStatus.UNKNOWN)

    @classmethod
    def to_domain_fill(cls, exec_rec: IBKRExecutionRecord) -> Fill:
        """Converts an IBKR execution record to a domain Fill."""
        side = OrderSide.BUY if exec_rec.side.upper() in ("BUY", "BOT") else OrderSide.SELL
        return Fill(
            fill_id=f"fill_{exec_rec.exec_id}",
            order_id=exec_rec.order_id,
            symbol=exec_rec.symbol,
            side=side,
            quantity=float(exec_rec.shares),
            fill_price=float(exec_rec.price),
            commission=max(0.0, float(exec_rec.commission)),
            timestamp=exec_rec.exec_time,
        )

    @classmethod
    def to_domain_holding(
        cls,
        symbol: str,
        shares: float,
        avg_cost: float,
        current_price: float,
    ) -> Holding:
        """Converts an IBKR position entry to a domain Holding."""
        shs = float(shares)
        px = float(current_price)
        cost = float(avg_cost)
        mv = shs * px
        return Holding(
            symbol=symbol,
            shares=shs,
            cost_basis=cost,
            current_price=px,
            market_value=mv,
        )

    @classmethod
    def to_domain_portfolio_state(
        cls,
        cash: float,
        holdings: dict[str, Holding],
        timestamp: datetime | None = None,
    ) -> PortfolioState:
        """Constructs a point-in-time domain PortfolioState from IBKR account balances."""
        ts = timestamp or datetime.now(timezone.utc)
        mv = sum(h.market_value for h in holdings.values())
        nav = cash + mv
        realized_weights = {sym: (h.market_value / nav) if abs(nav) > 1e-4 else 0.0 for sym, h in holdings.items()}
        return PortfolioState(
            timestamp=ts,
            cash=cash,
            holdings=holdings,
            nav=nav,
            realized_weights=realized_weights,
        )
