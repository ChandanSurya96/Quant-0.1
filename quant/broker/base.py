"""Abstract BrokerAdapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.interfaces import Fill, Holding, Order, PortfolioState


class BrokerAdapter(ABC):
    """Abstract interface decoupling strategy and OMS layers from physical broker APIs."""

    @property
    @abstractmethod
    def broker_name(self) -> str:
        """Name of the broker adapter."""
        raise NotImplementedError

    @abstractmethod
    def submit_order(
        self,
        order: Order,
        price_lookup: dict[str, float] | None = None,
    ) -> Fill | None:
        """Submits an order to the broker and returns the resulting Fill if executed immediately."""
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Requests cancellation of an open order."""
        raise NotImplementedError

    @abstractmethod
    def get_order(self, order_id: str) -> Order | None:
        """Queries current status of an order."""
        raise NotImplementedError

    @abstractmethod
    def get_open_orders(self) -> list[Order]:
        """Lists all active open orders."""
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> dict[str, Holding]:
        """Queries broker-reported physical asset holdings."""
        raise NotImplementedError

    @abstractmethod
    def get_account_state(self) -> PortfolioState:
        """Queries broker-reported account balances and mark-to-market NAV."""
        raise NotImplementedError

    @abstractmethod
    def get_fills(self) -> list[Fill]:
        """Queries all executed fills recorded by the broker."""
        raise NotImplementedError

    @abstractmethod
    def get_all_orders(self) -> list[Order]:
        """Queries all orders recorded by the broker."""
        raise NotImplementedError

    def health_check(self) -> str:
        """Queries broker connectivity state ('CONNECTED', 'DISCONNECTED', 'UNKNOWN')."""
        return "CONNECTED"

    def get_buying_power(self) -> float | None:
        """Queries broker buying power."""
        return None

    def get_short_availability(self, symbol: str) -> str:
        """Queries short availability ('AVAILABLE', 'UNAVAILABLE', 'UNKNOWN')."""
        return "AVAILABLE"

    def get_borrow_rate(self, symbol: str) -> float | None:
        """Queries annual borrow rate fee if available."""
        return None
