"""Interactive Brokers client interface and deterministic simulation client."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from .errors import (
    IBKRConnectionError,
    IBKRInvalidOrderError,
)
from .models import BuyingPowerInfo, IBKRConfig, IBKRExecutionRecord, IBKROrderRecord, ShortAvailability


class IBKRClientProtocol(ABC):
    """Abstract protocol for low-level IBKR communication."""

    @abstractmethod
    def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def is_connected(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        action: str,
        quantity: float,
        order_type: str = "MKT",
        limit_price: float | None = None,
        client_order_id: str | None = None,
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, ibkr_order_id: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_order_records(self) -> list[IBKROrderRecord]:
        raise NotImplementedError

    @abstractmethod
    def get_execution_records(self) -> list[IBKRExecutionRecord]:
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> dict[str, tuple[float, float, float]]:
        """Returns dict of symbol -> (shares, avg_cost, current_price)."""
        raise NotImplementedError

    @abstractmethod
    def get_account_summary(self) -> tuple[float, float]:
        """Returns (cash, nav)."""
        raise NotImplementedError

    @abstractmethod
    def get_buying_power_info(self) -> BuyingPowerInfo:
        raise NotImplementedError

    @abstractmethod
    def check_short_availability(self, symbol: str) -> ShortAvailability:
        raise NotImplementedError

    @abstractmethod
    def get_borrow_rate(self, symbol: str) -> float | None:
        raise NotImplementedError


class MockIBKRClient(IBKRClientProtocol):
    """Deterministic, testable mock of the Interactive Brokers TWS/Gateway socket API."""

    def __init__(self, config: IBKRConfig | None = None, auto_fill_on_submit: bool = False) -> None:
        self.config = config or IBKRConfig()
        self.auto_fill_on_submit = auto_fill_on_submit
        self._connected: bool = False
        self._next_order_id: int = 10001
        self._orders: dict[int, IBKROrderRecord] = {}
        self._client_oid_map: dict[str, int] = {}
        self._executions: list[IBKRExecutionRecord] = []
        self._seen_exec_ids: set[str] = set()
        self._cash: float = 100_000.0
        self._positions: dict[str, tuple[float, float, float]] = {}  # sym -> (shares, cost, px)
        self._short_availability_map: dict[str, ShortAvailability] = {}
        self._borrow_rates: dict[str, float] = {}
        self._buying_power: float = 200_000.0

    def connect(self) -> None:
        self.config.validate_safety_locks()
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def place_order(
        self,
        symbol: str,
        action: str,
        quantity: float,
        order_type: str = "MKT",
        limit_price: float | None = None,
        client_order_id: str | None = None,
    ) -> int:
        if not self._connected:
            raise IBKRConnectionError("Cannot submit order: IBKR socket is disconnected.")
        if quantity <= 0:
            raise IBKRInvalidOrderError(f"Invalid quantity {quantity}. Must be > 0.")

        cl_id = client_order_id or f"mock_cl_{uuid.uuid4().hex[:8]}"

        # Prevent duplicate submissions with the same client_order_id
        if cl_id in self._client_oid_map:
            return self._client_oid_map[cl_id]

        oid = self._next_order_id
        self._next_order_id += 1

        now = datetime.now(timezone.utc)
        record = IBKROrderRecord(
            order_id=f"ord_{oid}",
            client_order_id=cl_id,
            ibkr_order_id=oid,
            symbol=symbol,
            action=action.upper(),
            total_quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            status="Submitted",
            filled_quantity=0.0,
            remaining_quantity=quantity,
            avg_fill_price=0.0,
            submitted_at=now,
            last_updated_at=now,
        )
        self._orders[oid] = record
        self._client_oid_map[cl_id] = oid
        return oid

    def cancel_order(self, ibkr_order_id: int) -> bool:
        if not self._connected:
            raise IBKRConnectionError("Cannot cancel order: IBKR socket is disconnected.")
        if ibkr_order_id not in self._orders:
            return False
        rec = self._orders[ibkr_order_id]
        if rec.status in ("Filled", "Cancelled", "Inactive"):
            return False
        rec.status = "Cancelled"
        rec.last_updated_at = datetime.now(timezone.utc)
        return True

    def inject_partial_fill(
        self,
        ibkr_order_id: int,
        fill_shares: float,
        fill_price: float,
        commission: float = 1.0,
        exec_id: str | None = None,
    ) -> IBKRExecutionRecord:
        """Simulates an incoming asynchronous execution fill from IBKR."""
        if ibkr_order_id not in self._orders:
            raise IBKRInvalidOrderError(f"Order ID {ibkr_order_id} not found in mock IBKR state.")
        rec = self._orders[ibkr_order_id]

        e_id = exec_id or f"exec_{uuid.uuid4().hex[:8]}"
        if e_id in self._seen_exec_ids:
            # Duplicate execution ID -> return existing record
            return [e for e in self._executions if e.exec_id == e_id][0]

        now = datetime.now(timezone.utc)
        exec_rec = IBKRExecutionRecord(
            exec_id=e_id,
            order_id=rec.order_id,
            client_order_id=rec.client_order_id,
            symbol=rec.symbol,
            side=rec.action,
            shares=fill_shares,
            price=fill_price,
            commission=commission,
            exec_time=now,
        )
        self._executions.append(exec_rec)
        self._seen_exec_ids.add(e_id)

        # Update order progress
        prev_filled = rec.filled_quantity
        new_filled = prev_filled + fill_shares
        rec.filled_quantity = new_filled
        rec.remaining_quantity = max(0.0, rec.total_quantity - new_filled)
        rec.avg_fill_price = ((rec.avg_fill_price * prev_filled) + (fill_price * fill_shares)) / new_filled

        if rec.remaining_quantity <= 1e-4:
            rec.status = "Filled"
        else:
            rec.status = "PartiallyFilled"
        rec.last_updated_at = now

        # Update mock broker positions and cash
        mult = 1.0 if rec.action == "BUY" else -1.0
        trade_notional = fill_shares * fill_price
        self._cash -= (trade_notional * mult) + commission

        curr_shares, curr_cost, _ = self._positions.get(rec.symbol, (0.0, fill_price, fill_price))
        new_shares = curr_shares + (fill_shares * mult)
        if abs(new_shares) < 1e-4:
            self._positions.pop(rec.symbol, None)
        else:
            self._positions[rec.symbol] = (new_shares, fill_price, fill_price)

        return exec_rec

    def get_order_records(self) -> list[IBKROrderRecord]:
        return list(self._orders.values())

    def get_execution_records(self) -> list[IBKRExecutionRecord]:
        return list(self._executions)

    def get_positions(self) -> dict[str, tuple[float, float, float]]:
        return dict(self._positions)

    def get_account_summary(self) -> tuple[float, float]:
        mv = sum(shs * px for shs, _, px in self._positions.values())
        nav = self._cash + mv
        return self._cash, nav

    def get_buying_power_info(self) -> BuyingPowerInfo:
        return BuyingPowerInfo(
            available_funds=self._cash,
            buying_power=self._buying_power,
            initial_margin=10_000.0,
            maintenance_margin=8_000.0,
        )

    def check_short_availability(self, symbol: str) -> ShortAvailability:
        return self._short_availability_map.get(symbol, ShortAvailability.AVAILABLE)

    def get_borrow_rate(self, symbol: str) -> float | None:
        return self._borrow_rates.get(symbol, 0.005)  # 50 bps default borrow rate
