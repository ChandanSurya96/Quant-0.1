"""Domain models, issue types, and statuses for portfolio reconciliation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from ..core.enums import ExecutionMode


class ReconciliationStatus(str, Enum):
    """Reconciliation verdict status."""
    MATCHED = "MATCHED"
    MISMATCHED = "MISMATCHED"
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"


class RecoveryState(str, Enum):
    """Recovery state machine lifecycle."""
    HEALTHY = "HEALTHY"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    RECONCILING = "RECONCILING"
    MATCHED = "MATCHED"
    EXECUTION_PERMITTED = "EXECUTION_PERMITTED"


class ReconciliationIssueType(str, Enum):
    """Specific reconciliation discrepancy category."""
    POSITION_MISSING_INTERNAL = "POSITION_MISSING_INTERNAL"
    POSITION_MISSING_BROKER = "POSITION_MISSING_BROKER"
    POSITION_QUANTITY_MISMATCH = "POSITION_QUANTITY_MISMATCH"

    ORDER_MISSING_INTERNAL = "ORDER_MISSING_INTERNAL"
    ORDER_MISSING_BROKER = "ORDER_MISSING_BROKER"
    ORDER_STATUS_MISMATCH = "ORDER_STATUS_MISMATCH"
    ORDER_QUANTITY_MISMATCH = "ORDER_QUANTITY_MISMATCH"
    ORDER_UNKNOWN_STATE = "ORDER_UNKNOWN_STATE"

    FILL_MISSING_INTERNAL = "FILL_MISSING_INTERNAL"
    FILL_MISSING_BROKER = "FILL_MISSING_BROKER"
    FILL_QUANTITY_MISMATCH = "FILL_QUANTITY_MISMATCH"
    FILL_PRICE_MISMATCH = "FILL_PRICE_MISMATCH"
    FILL_DUPLICATE = "FILL_DUPLICATE"
    FILL_OVERFILL = "FILL_OVERFILL"

    CASH_MISMATCH = "CASH_MISMATCH"
    NAV_MISMATCH = "NAV_MISMATCH"
    SHARE_CONSERVATION_VIOLATION = "SHARE_CONSERVATION_VIOLATION"
    NAV_CONSERVATION_VIOLATION = "NAV_CONSERVATION_VIOLATION"


@dataclass(frozen=True)
class ReconciliationIssue:
    """Individual reconciliation discrepancy."""
    issue_type: ReconciliationIssueType
    symbol: str | None = None
    order_id: str | None = None
    fill_id: str | None = None
    internal_value: Any = None
    broker_value: Any = None
    discrepancy: float | None = None
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "issue_type": self.issue_type.value,
            "symbol": self.symbol,
            "order_id": self.order_id,
            "fill_id": self.fill_id,
            "internal_value": self.internal_value,
            "broker_value": self.broker_value,
            "discrepancy": self.discrepancy,
            "message": self.message,
        }


@dataclass(frozen=True)
class ReconciliationConfig:
    """Configurable numerical tolerances for state comparison."""
    position_qty_tolerance: float = 0.001
    cash_tolerance: float = 0.01
    nav_tolerance: float = 0.01
    price_tolerance: float = 1e-4


@dataclass(frozen=True)
class ReconciliationResult:
    """Overall result of a portfolio reconciliation run."""
    reconciliation_id: str
    run_id: str
    timestamp: datetime
    execution_mode: ExecutionMode
    status: ReconciliationStatus
    issues: list[ReconciliationIssue] = field(default_factory=list)
    internal_holdings: dict[str, float] = field(default_factory=dict)
    broker_positions: dict[str, float] = field(default_factory=dict)
    internal_cash: float = 0.0
    broker_cash: float = 0.0
    internal_nav: float = 0.0
    broker_nav: float = 0.0

    @property
    def is_matched(self) -> bool:
        return self.status == ReconciliationStatus.MATCHED and len(self.issues) == 0

    @property
    def passed(self) -> bool:
        """Alias for is_matched."""
        return self.is_matched

    @property
    def violations(self) -> list[str]:
        """List of violation messages."""
        return [i.message for i in self.issues]

    @property
    def cash_difference(self) -> float:
        return float(self.internal_cash - self.broker_cash)

    @property
    def nav_difference(self) -> float:
        return float(self.internal_nav - self.broker_nav)

    @property
    def position_differences(self) -> dict[str, float]:
        all_syms = set(self.internal_holdings.keys()) | set(self.broker_positions.keys())
        return {sym: self.internal_holdings.get(sym, 0.0) - self.broker_positions.get(sym, 0.0) for sym in all_syms}

    @property
    def order_mismatches(self) -> list[dict]:
        return [i.to_dict() for i in self.issues if "ORDER" in i.issue_type.value]

    @property
    def fill_mismatches(self) -> list[dict]:
        return [i.to_dict() for i in self.issues if "FILL" in i.issue_type.value]

    def to_dict(self) -> dict:
        return {
            "reconciliation_id": self.reconciliation_id,
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            "execution_mode": self.execution_mode.value,
            "status": self.status.value,
            "is_matched": self.is_matched,
            "passed": self.passed,
            "issues_count": len(self.issues),
            "violations": self.violations,
            "issues": [i.to_dict() for i in self.issues],
            "internal_holdings": self.internal_holdings,
            "broker_positions": self.broker_positions,
            "position_differences": self.position_differences,
            "internal_cash": self.internal_cash,
            "broker_cash": self.broker_cash,
            "cash_difference": self.cash_difference,
            "internal_nav": self.internal_nav,
            "broker_nav": self.broker_nav,
            "nav_difference": self.nav_difference,
            "order_mismatches": self.order_mismatches,
            "fill_mismatches": self.fill_mismatches,
        }
