"""Interactive Brokers BrokerAdapter implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ...core.enums import ExecutionMode, OrderSide, OrderStatus, OrderType
from ...core.interfaces import Fill, Holding, Order, PortfolioState
from ..base import BrokerAdapter
from .client import IBKRClientProtocol, MockIBKRClient
from .errors import (
    IBKRConnectionError,
    IBKRInvalidOrderError,
    IBKRLiveSafetyLockedError,
    IBKRShortUnavailableError,
)
from .health import IBKRHealthTracker
from .mapper import IBKRMapper
from .models import IBKRConfig, ShortAvailability


class IBKRBrokerAdapter(BrokerAdapter):
    """Production broker adapter for Interactive Brokers (TWS / IB Gateway)."""

    def __init__(
        self,
        config: IBKRConfig | None = None,
        client: IBKRClientProtocol | None = None,
    ) -> None:
        self.config = config or IBKRConfig()
        self.config.validate_safety_locks()

        self.client = client or MockIBKRClient(self.config)
        self.health_tracker = IBKRHealthTracker()

        # Connect client and initialize health
        try:
            self.client.connect()
            self.health_tracker.record_connected()
        except Exception as e:
            self.health_tracker.record_disconnected(str(e))

        # Local cache and identifier mapping
        self._submitted_orders: dict[str, Order] = {}
        self._ibkr_oid_to_domain_id: dict[int, str] = {}
        self._ingested_fill_ids: set[str] = set()

    @property
    def broker_name(self) -> str:
        return "InteractiveBrokersAdapter"

    def submit_order(
        self,
        order: Order,
        price_lookup: dict[str, float] | None = None,
    ) -> Fill | None:
        """Submits an order asynchronously to Interactive Brokers."""
        if not self.client.is_connected():
            self.health_tracker.record_disconnected("Socket disconnected during submit_order")
            raise IBKRConnectionError("Cannot submit order: Interactive Brokers socket is not connected.")

        # Fail-closed Short Borrow Locate Gate
        if order.side == OrderSide.SELL:
            # Check if this sale opens or increases a short position
            positions = self.get_positions()
            curr_holding = positions.get(order.symbol)
            curr_shares = curr_holding.shares if curr_holding is not None else 0.0
            if curr_shares <= 0 or (curr_shares - order.quantity) < 0:
                avail = self.get_short_availability(order.symbol)
                if avail == ShortAvailability.UNAVAILABLE.value:
                    raise IBKRShortUnavailableError(f"Short borrow unavailable for symbol {order.symbol!r}. Order rejected.")
                if avail == ShortAvailability.UNKNOWN.value:
                    raise IBKRShortUnavailableError(f"Short availability is UNKNOWN for {order.symbol!r}. Failing closed.")

        action = "BUY" if order.side == OrderSide.BUY else "SELL"
        order_type_str = "MKT" if order.order_type == OrderType.MARKET else "LMT"

        try:
            ibkr_oid = self.client.place_order(
                symbol=order.symbol,
                action=action,
                quantity=order.quantity,
                order_type=order_type_str,
                limit_price=order.limit_price,
                client_order_id=order.client_order_id or order.order_id,
            )
        except Exception as e:
            self.health_tracker.record_disconnected(str(e))
            raise

        # Track submitted order
        self._submitted_orders[order.order_id] = order
        self._ibkr_oid_to_domain_id[ibkr_oid] = order.order_id
        self.health_tracker.record_heartbeat()

        if getattr(self.client, "auto_fill_on_submit", False):
            px = (price_lookup and price_lookup.get(order.symbol)) or order.limit_price or 100.0
            comm = max(1.0, order.quantity * px * 0.0010)
            self.client.inject_partial_fill(ibkr_oid, fill_shares=order.quantity, fill_price=px, commission=comm)

        # Asynchronous execution boundary: returns None on submission acknowledgment
        return None

    def cancel_order(self, order_id: str) -> bool:
        """Requests order cancellation at IBKR."""
        if not self.client.is_connected():
            raise IBKRConnectionError("Cannot cancel order: IBKR socket disconnected.")

        for ibkr_oid, d_oid in self._ibkr_oid_to_domain_id.items():
            if d_oid == order_id:
                return self.client.cancel_order(ibkr_oid)
        return False

    def get_order(self, order_id: str) -> Order | None:
        """Queries current status of an order from IBKR records."""
        for rec in self.client.get_order_records():
            domain_order_id = self._ibkr_oid_to_domain_id.get(rec.ibkr_order_id, rec.order_id)
            if domain_order_id == order_id or rec.order_id == order_id or rec.client_order_id == order_id:
                domain_status = IBKRMapper.to_domain_order_status(rec.status)
                original = self._submitted_orders.get(domain_order_id) or self._submitted_orders.get(order_id)
                side = OrderSide.BUY if rec.action == "BUY" else OrderSide.SELL
                return Order(
                    order_id=domain_order_id,
                    run_id=original.run_id if original else "run_unknown",
                    strategy_id=original.strategy_id if original else "strategy_unknown",
                    symbol=rec.symbol,
                    side=side,
                    order_type=OrderType.MARKET if rec.order_type == "MKT" else OrderType.LIMIT,
                    quantity=rec.total_quantity,
                    limit_price=rec.limit_price,
                    client_order_id=rec.client_order_id,
                    execution_mode=ExecutionMode.PAPER if self.config.is_paper else ExecutionMode.LIVE,
                    created_at=rec.submitted_at,
                    status=domain_status,
                )
        return None

    def get_open_orders(self) -> list[Order]:
        """Lists active unfilled/partially-filled orders."""
        open_orders: list[Order] = []
        for rec in self.client.get_order_records():
            domain_status = IBKRMapper.to_domain_order_status(rec.status)
            if domain_status in (OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED):
                domain_order_id = self._ibkr_oid_to_domain_id.get(rec.ibkr_order_id, rec.order_id)
                ord_obj = self.get_order(domain_order_id)
                if ord_obj is not None:
                    open_orders.append(ord_obj)
        return open_orders

    def get_all_orders(self) -> list[Order]:
        """Lists all orders reported by IBKR."""
        orders: list[Order] = []
        for rec in self.client.get_order_records():
            domain_order_id = self._ibkr_oid_to_domain_id.get(rec.ibkr_order_id, rec.order_id)
            ord_obj = self.get_order(domain_order_id)
            if ord_obj is not None:
                orders.append(ord_obj)
        return orders

    def get_positions(self) -> dict[str, Holding]:
        """Queries physical asset positions from IBKR."""
        pos_raw = self.client.get_positions()
        holdings: dict[str, Holding] = {}
        for sym, (shs, cost, px) in pos_raw.items():
            holdings[sym] = IBKRMapper.to_domain_holding(sym, shs, cost, px)
        return holdings

    def get_account_state(self, current_prices: dict[str, float] | None = None) -> PortfolioState:
        """Queries cash, holdings, and mark-to-market NAV from IBKR."""
        cash, nav = self.client.get_account_summary()
        holdings = self.get_positions()
        return IBKRMapper.to_domain_portfolio_state(cash, holdings)

    def get_fills(self) -> list[Fill]:
        """Queries all executed fills reported by IBKR."""
        from dataclasses import replace
        exec_records = self.client.get_execution_records()
        fills: list[Fill] = []
        for e in exec_records:
            fill = IBKRMapper.to_domain_fill(e)
            raw_id_num = e.order_id.replace("ord_", "")
            domain_oid = None
            if raw_id_num.isdigit():
                domain_oid = self._ibkr_oid_to_domain_id.get(int(raw_id_num))
            if domain_oid is None:
                domain_oid = (
                    e.order_id if e.order_id in self._submitted_orders
                    else e.client_order_id if e.client_order_id in self._submitted_orders
                    else fill.order_id
                )
            fill = replace(fill, order_id=domain_oid)
            fills.append(fill)
            self._ingested_fill_ids.add(fill.fill_id)
        return fills

    def health_check(self) -> str:
        """Queries IBKR connection status."""
        return self.health_tracker.status_string()

    def get_buying_power(self) -> float | None:
        """Queries current buying power balance."""
        if not self.client.is_connected():
            return None
        info = self.client.get_buying_power_info()
        return info.buying_power

    def get_short_availability(self, symbol: str) -> str:
        """Queries short locate availability."""
        if not self.client.is_connected():
            return ShortAvailability.UNKNOWN.value
        avail = self.client.check_short_availability(symbol)
        return avail.value

    def get_borrow_rate(self, symbol: str) -> float | None:
        """Queries annual borrow rate fee."""
        if not self.client.is_connected():
            return None
        return self.client.get_borrow_rate(symbol)
