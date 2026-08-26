"""Core domain enums for Quant engine."""

from enum import Enum


class ExecutionMode(str, Enum):
    """Execution environment mode.

    RESEARCH: Permitted to use historical fixtures, research snapshots, or synthetic benchmarks.
    PAPER: Uses real live market data and simulated execution. Synthetic data is strictly forbidden.
    LIVE: Uses real live market data and live broker execution. Synthetic data is strictly forbidden.
    """
    RESEARCH = "RESEARCH"
    PAPER = "PAPER"
    LIVE = "LIVE"


class AssetClass(str, Enum):
    """Supported asset classes."""
    EQUITY = "EQUITY"
    BOND = "BOND"
    CURRENCY = "CURRENCY"
    COMMODITY = "COMMODITY"


class OrderSide(str, Enum):
    """Order direction."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order execution instruction type."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    TWAP = "TWAP"
    VWAP = "VWAP"


class OrderStatus(str, Enum):
    """Lifecycle state machine status for an Order."""
    CREATED = "CREATED"
    APPROVED = "APPROVED"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
