"""Deterministic PaperBroker adapter simulating execution fills and cash accounting."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import uuid

from ..core.enums import OrderSide, OrderStatus
from ..core.exceptions import OMSError
from ..core.interfaces import Fill, Holding, Order, PortfolioState
from ..oms.lifecycle import transition_order
from .base import BrokerAdapter


class PaperBroker(BrokerAdapter):
    """Simulates deterministic broker execution with configurable friction and exact cash accounting."""

    def __init__(
        self,
        initial_cash: float = 100_000.0,
        cost_bps: float = 10.0,
        slippage_bps: float = 0.0,
        commission_per_share: float = 0.0,
        commission_fixed: float = 0.0,
    ) -> None:
        self.cash = float(initial_cash)
        self.cost_bps = float(cost_bps)
        self.slippage_bps = float(slippage_bps)
        self.commission_per_share = float(commission_per_share)
        self.commission_fixed = float(commission_fixed)

        self._orders: dict[str, Order] = {}
        self._fills: dict[str, Fill] = {}
        self._holdings: dict[str, Holding] = {}

    @property
    def broker_name(self) -> str:
        return "PaperBroker"

    def submit_order(
        self,
        order: Order,
        price_lookup: dict[str, float] | None = None,
    ) -> Fill | None:
        """Executes an approved market order deterministically."""
        # Validate order lifecycle state
        if order.status == OrderStatus.CREATED:
            order = transition_order(order, OrderStatus.APPROVED)

        if order.status == OrderStatus.APPROVED:
            order = transition_order(order, OrderStatus.SUBMITTED)

        self._orders[order.order_id] = order

        if price_lookup is None or order.symbol not in price_lookup:
            rejected = transition_order(order, OrderStatus.REJECTED)
            self._orders[order.order_id] = rejected
            raise OMSError(f"Execution failed: missing reference price for symbol {order.symbol!r}")

        ref_price = price_lookup[order.symbol]
        if ref_price <= 0:
            rejected = transition_order(order, OrderStatus.REJECTED)
            self._orders[order.order_id] = rejected
            raise OMSError(f"Execution failed: invalid reference price {ref_price} for {order.symbol!r}")

        # Deterministic slippage model
        if order.side == OrderSide.BUY:
            exec_price = ref_price * (1.0 + self.slippage_bps / 10_000.0)
        else:
            exec_price = ref_price * (1.0 - self.slippage_bps / 10_000.0)

        # Decomposed friction model
        traded_notional = order.quantity * exec_price
        turnover_cost = traded_notional * (self.cost_bps / 10_000.0)
        share_commission = order.quantity * self.commission_per_share
        total_commission = turnover_cost + share_commission + self.commission_fixed

        fill_id = f"fill_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        fill = Fill(
            fill_id=fill_id,
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            fill_price=exec_price,
            commission=total_commission,
            timestamp=now,
        )

        # Physical cash and signed-share accounting
        current_h = self._holdings.get(order.symbol)
        current_shares = current_h.shares if current_h is not None else 0.0

        if order.side == OrderSide.BUY:
            self.cash -= (order.quantity * exec_price + total_commission)
            new_shares = current_shares + order.quantity
        else:
            self.cash += (order.quantity * exec_price - total_commission)
            new_shares = current_shares - order.quantity

        if abs(new_shares) < 1e-6:
            if order.symbol in self._holdings:
                del self._holdings[order.symbol]
        else:
            self._holdings[order.symbol] = Holding(
                symbol=order.symbol,
                shares=new_shares,
                cost_basis=exec_price,
                current_price=ref_price,
                market_value=new_shares * ref_price,
            )

        # Finalize order lifecycle
        filled_order = transition_order(order, OrderStatus.FILLED)
        self._orders[order.order_id] = filled_order
        self._fills[fill_id] = fill

        return fill

    def cancel_order(self, order_id: str) -> bool:
        """Cancels an order if in CREATED, APPROVED, or SUBMITTED state."""
        order = self._orders.get(order_id)
        if order is None:
            return False
        if order.status in (OrderStatus.CREATED, OrderStatus.APPROVED, OrderStatus.SUBMITTED):
            self._orders[order_id] = transition_order(order, OrderStatus.CANCELLED)
            return True
        return False

    def get_order(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def get_open_orders(self) -> list[Order]:
        return [
            o for o in self._orders.values()
            if o.status in (OrderStatus.CREATED, OrderStatus.APPROVED, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED)
        ]

    def get_positions(self) -> dict[str, Holding]:
        return dict(self._holdings)

    def get_account_state(self, current_prices: dict[str, float] | None = None) -> PortfolioState:
        """Returns the current mark-to-market PortfolioState."""
        prices = current_prices or {}
        updated_holdings: dict[str, Holding] = {}
        for sym, h in self._holdings.items():
            px = prices.get(sym, h.current_price)
            updated_holdings[sym] = replace(h, current_price=px, market_value=h.shares * px)

        mv_sum = sum(h.market_value for h in updated_holdings.values())
        nav = self.cash + mv_sum
        realized_w = {sym: (h.market_value / nav if abs(nav) > 1e-8 else 0.0) for sym, h in updated_holdings.items()}

        return PortfolioState(
            timestamp=datetime.now(timezone.utc),
            cash=self.cash,
            holdings=updated_holdings,
            nav=nav,
            realized_weights=realized_w,
        )

    def get_fills(self) -> list[Fill]:
        """Returns all executed fills recorded by PaperBroker."""
        return list(self._fills.values())

    def get_all_orders(self) -> list[Order]:
        """Returns all orders recorded by PaperBroker."""
        return list(self._orders.values())
