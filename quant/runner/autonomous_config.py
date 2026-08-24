"""Safety configuration and policy boundary for P9 Controlled Autonomous Execution."""

from __future__ import annotations

from dataclasses import dataclass, field
import os

from ..core.enums import OrderType
from ..core.exceptions import ModeViolationError


@dataclass(frozen=True)
class AutonomousExecutionConfig:
    """Immutable safety configuration for autonomous execution."""
    autonomous_execution_enabled: bool = field(
        default_factory=lambda: os.getenv("AUTONOMOUS_EXECUTION_ENABLED", "false").lower() in ("true", "1", "yes")
    )
    approval_mode: str = field(
        default_factory=lambda: os.getenv("APPROVAL_MODE", "MANUAL_APPROVAL").upper()
    )
    broker_env: str = field(
        default_factory=lambda: os.getenv("BROKER_ENV", "PAPER").upper()
    )
    live_execution_enabled: bool = field(
        default_factory=lambda: os.getenv("LIVE_EXECUTION_ENABLED", "false").lower() in ("true", "1", "yes")
    )
    max_live_capital: float | None = field(
        default_factory=lambda: float(os.getenv("MAX_LIVE_CAPITAL")) if os.getenv("MAX_LIVE_CAPITAL") is not None else None
    )
    max_autonomous_gross_exposure: float = 1.0
    max_autonomous_order_batches_per_day: int = 1
    autonomous_strategy_whitelist: tuple[str, ...] = ("systematic_macro_v1", "systematic_macro")
    autonomous_instrument_whitelist: tuple[str, ...] = (
        "SPY", "TLT", "IEF", "BNDX", "IGOV", "UUP",
        "FXE", "FXY", "FXB", "EWJ", "EFA", "EEM",
        "GLD", "DBC", "VNQ", "EMB"
    )
    allowed_order_types: tuple[OrderType, ...] = (OrderType.MARKET, OrderType.LIMIT)
    emergency_stop_active: bool = field(
        default_factory=lambda: os.getenv("EMERGENCY_STOP", "false").lower() in ("true", "1", "yes")
    )
    circuit_breaker_drawdown_limit: float = -0.15

    def validate_safety_locks(self) -> None:
        """Validates all multi-condition locks before allowing autonomous execution initialization."""
        if self.broker_env not in ("PAPER", "LIVE"):
            raise ValueError(f"Ambiguous or invalid BROKER_ENV={self.broker_env!r}. Must be 'PAPER' or 'LIVE'.")

        if self.approval_mode not in ("MANUAL_APPROVAL", "AUTONOMOUS"):
            raise ValueError(f"Invalid APPROVAL_MODE={self.approval_mode!r}. Must be 'MANUAL_APPROVAL' or 'AUTONOMOUS'.")

        if self.autonomous_execution_enabled:
            if self.approval_mode != "AUTONOMOUS":
                raise ModeViolationError(
                    f"AUTONOMOUS_EXECUTION_ENABLED=true requires APPROVAL_MODE=AUTONOMOUS (got {self.approval_mode!r})."
                )
            if self.broker_env == "LIVE":
                if not self.live_execution_enabled:
                    raise ModeViolationError(
                        "Autonomous execution in LIVE broker environment requires explicit LIVE_EXECUTION_ENABLED=true."
                    )
                if self.max_live_capital is None or self.max_live_capital <= 0:
                    raise ModeViolationError(
                        "Explicit operator-provided MAX_LIVE_CAPITAL > 0 is mandatory for LIVE autonomous execution. "
                        "No implicit financial default is permitted. Startup blocked."
                    )
            elif self.max_live_capital is not None and self.max_live_capital <= 0:
                raise ValueError(f"Invalid MAX_LIVE_CAPITAL={self.max_live_capital}. Must be > 0.")

        if self.emergency_stop_active and self.autonomous_execution_enabled:
            raise ModeViolationError("Cannot enable autonomous execution while EMERGENCY_STOP is active.")
