"""Live execution configuration and multi-condition safety policy."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from ..core.enums import OrderType
from ..core.exceptions import ModeViolationError


@dataclass(frozen=True)
class LiveExecutionConfig:
    """Explicit multi-condition configuration for controlled live execution."""
    broker_env: str = field(default_factory=lambda: os.getenv("BROKER_ENV", "PAPER").upper())
    live_execution_enabled: bool = field(
        default_factory=lambda: os.getenv("LIVE_EXECUTION_ENABLED", "false").lower() in ("true", "1", "yes")
    )
    live_capital_limit: float = field(
        default_factory=lambda: float(os.getenv("LIVE_CAPITAL_LIMIT", "25000.0"))
    )
    instrument_whitelist: tuple[str, ...] = (
        "SPY", "TLT", "IEF", "BNDX", "IGOV", "UUP",
        "FXE", "FXY", "FXB", "EWJ", "EFA", "EEM",
        "GLD", "DBC", "VNQ", "EMB"
    )
    allowed_order_types: tuple[OrderType, ...] = (OrderType.MARKET, OrderType.LIMIT)
    max_live_order_batches_per_day: int = 1
    approval_ttl_minutes: float = 15.0
    emergency_stop_active: bool = field(
        default_factory=lambda: os.getenv("EMERGENCY_STOP", "false").lower() in ("true", "1", "yes")
    )

    def validate_safety_locks(self) -> None:
        """Enforces unambiguous environment separation and multi-condition safety requirements."""
        if self.broker_env not in ("PAPER", "LIVE"):
            raise ValueError(
                f"Ambiguous or invalid BROKER_ENV={self.broker_env!r}. Must be explicitly 'PAPER' or 'LIVE'."
            )

        if self.broker_env == "LIVE":
            if not self.live_execution_enabled:
                raise ModeViolationError(
                    "LIVE execution blocked: BROKER_ENV=LIVE requires LIVE_EXECUTION_ENABLED=true."
                )
            if self.live_capital_limit <= 0:
                raise ModeViolationError(
                    f"LIVE execution blocked: LIVE_CAPITAL_LIMIT must be > 0 (got ${self.live_capital_limit:,.2f})."
                )
            if not self.instrument_whitelist:
                raise ModeViolationError("LIVE execution blocked: Instrument whitelist cannot be empty.")
            if self.emergency_stop_active:
                raise ModeViolationError("LIVE execution blocked: Emergency Stop (Kill Switch) is currently active.")
