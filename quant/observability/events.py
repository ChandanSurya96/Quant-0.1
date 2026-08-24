"""Event taxonomies, severity levels, and operational health states."""

from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    """Operational lifecycle event types."""
    # Data Layer
    DATA_FETCH_STARTED = "DATA_FETCH_STARTED"
    DATA_FETCH_FAILED = "DATA_FETCH_FAILED"
    DATA_VALIDATION_FAILED = "DATA_VALIDATION_FAILED"
    DATA_VALIDATED = "DATA_VALIDATED"

    # Strategy Layer
    STRATEGY_STARTED = "STRATEGY_STARTED"
    STRATEGY_COMPLETED = "STRATEGY_COMPLETED"
    TARGET_PORTFOLIO_CREATED = "TARGET_PORTFOLIO_CREATED"

    # Risk Layer
    RISK_EVALUATION_STARTED = "RISK_EVALUATION_STARTED"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    RISK_KILL_SWITCH = "RISK_KILL_SWITCH"

    # OMS / Approval Layer
    ORDER_BATCH_CREATED = "ORDER_BATCH_CREATED"
    ORDER_APPROVAL_REQUIRED = "ORDER_APPROVAL_REQUIRED"
    ORDER_APPROVED = "ORDER_APPROVED"
    ORDER_REJECTED = "ORDER_REJECTED"

    # Broker Execution Layer
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_PARTIALLY_FILLED = "ORDER_PARTIALLY_FILLED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_CANCELLED = "ORDER_CANCELLED"

    # Portfolio State
    PORTFOLIO_UPDATED = "PORTFOLIO_UPDATED"
    SNAPSHOT_CREATED = "SNAPSHOT_CREATED"

    # System Lifecycle & Recovery
    SYSTEM_STOPPED = "SYSTEM_STOPPED"
    SYSTEM_RECOVERY_REQUIRED = "SYSTEM_RECOVERY_REQUIRED"
    SYSTEM_RECOVERED = "SYSTEM_RECOVERED"


class AlertSeverity(str, Enum):
    """Alert severity classification."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class HealthState(str, Enum):
    """Component health state."""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class SystemStatus(str, Enum):
    """Overall operational system lifecycle status."""
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    STOPPED = "STOPPED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
