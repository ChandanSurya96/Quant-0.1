"""Data models and configuration for Interactive Brokers adapter."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ShortAvailability(str, Enum):
    """Short locate and borrow availability states."""
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


@dataclass
class BuyingPowerInfo:
    """Margin and buying power balances reported by IBKR."""
    available_funds: float
    buying_power: float
    initial_margin: float | None = None
    maintenance_margin: float | None = None
    currency: str = "USD"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class IBKRConfig:
    """Configuration for Interactive Brokers connection and safety boundary."""
    host: str = field(default_factory=lambda: os.getenv("IBKR_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("IBKR_PORT", "7497")))
    client_id: int = field(default_factory=lambda: int(os.getenv("IBKR_CLIENT_ID", "1")))
    account_id: str = field(default_factory=lambda: os.getenv("IBKR_ACCOUNT", ""))
    is_paper: bool = True
    live_execution_enabled: bool = False
    timeout_seconds: float = 10.0

    def validate_safety_locks(self) -> None:
        """Enforces live trading safety lock. Live execution is forbidden without explicit multi-condition approval."""
        if not self.is_paper:
            if not self.live_execution_enabled:
                from .errors import IBKRLiveSafetyLockedError
                raise IBKRLiveSafetyLockedError(
                    "LIVE execution is locked! live_execution_enabled must be explicitly True to connect to live port."
                )


@dataclass
class IBKROrderRecord:
    """Internal tracking record for an order submitted to IBKR."""
    order_id: str
    client_order_id: str
    ibkr_order_id: int
    symbol: str
    action: str  # "BUY" or "SELL"
    total_quantity: float
    order_type: str = "MKT"
    limit_price: float | None = None
    status: str = "Submitted"
    filled_quantity: float = 0.0
    remaining_quantity: float = 0.0
    avg_fill_price: float = 0.0
    submitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class IBKRExecutionRecord:
    """Execution fill reported by IBKR."""
    exec_id: str
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    shares: float
    price: float
    commission: float = 0.0
    exec_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
