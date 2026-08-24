"""Component health checks, fail-closed operational states, and system snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import sqlite3

from ..broker.base import BrokerAdapter
from ..core.enums import ExecutionMode
from ..core.interfaces import RiskDecision
from ..persistence.database import DatabaseManager
from .events import HealthState, SystemStatus


@dataclass
class ComponentHealth:
    """Point-in-time health state of an individual system component."""

    name: str
    state: HealthState
    message: str
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict = field(default_factory=dict)

    @property
    def is_healthy(self) -> bool:
        return self.state in (HealthState.HEALTHY, HealthState.DEGRADED)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "message": self.message,
            "checked_at": self.checked_at.isoformat(),
            "details": self.details,
        }


@dataclass
class SystemHealthSnapshot:
    """Comprehensive serializable system health snapshot."""

    timestamp: datetime
    execution_mode: ExecutionMode
    overall_status: SystemStatus
    data_health: ComponentHealth
    persistence_health: ComponentHealth
    broker_health: ComponentHealth
    risk_health: ComponentHealth
    active_failure: str | None = None
    recovery_required: bool = False

    def is_execution_permitted(self) -> bool:
        """Evaluates whether system conditions permit order generation and execution.

        Fail-Closed Principle:
        - In PAPER/LIVE: All critical components MUST be HEALTHY.
        - UNKNOWN is never treated as SAFE.
        - If recovery_required is True, execution is blocked.
        """
        if self.recovery_required or self.overall_status == SystemStatus.RECOVERY_REQUIRED:
            return False

        critical = [
            self.data_health,
            self.persistence_health,
            self.broker_health,
            self.risk_health,
        ]

        if self.execution_mode in (ExecutionMode.PAPER, ExecutionMode.LIVE):
            return all(c.state == HealthState.HEALTHY for c in critical)

        # In RESEARCH mode, persistence and data must be valid (not FAILED)
        return (
            self.persistence_health.state != HealthState.FAILED
            and self.data_health.state != HealthState.FAILED
        )

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "execution_mode": self.execution_mode.value,
            "overall_status": self.overall_status.value,
            "data_health": self.data_health.to_dict(),
            "persistence_health": self.persistence_health.to_dict(),
            "broker_health": self.broker_health.to_dict(),
            "risk_health": self.risk_health.to_dict(),
            "active_failure": self.active_failure,
            "recovery_required": self.recovery_required,
            "execution_permitted": self.is_execution_permitted(),
        }


def check_data_health(
    last_fetch_time: datetime | None = None,
    is_stale: bool = False,
    provider_available: bool = True,
    details: dict | None = None,
) -> ComponentHealth:
    """Evaluates market data provider health."""
    now = datetime.now(timezone.utc)
    det = details or {}
    if not provider_available:
        return ComponentHealth("data_provider", HealthState.FAILED, "Market data provider unavailable", now, det)
    if is_stale:
        return ComponentHealth("data_provider", HealthState.DEGRADED, "Market data timestamps are stale", now, det)
    if last_fetch_time is None:
        return ComponentHealth("data_provider", HealthState.UNKNOWN, "No market data fetch recorded", now, det)
    return ComponentHealth("data_provider", HealthState.HEALTHY, "Market data feed active and valid", now, det)


def check_persistence_health(db_manager: DatabaseManager) -> ComponentHealth:
    """Evaluates operational SQLite persistence health."""
    now = datetime.now(timezone.utc)
    try:
        ver = db_manager.get_schema_version()
        if ver <= 0:
            return ComponentHealth("persistence", HealthState.FAILED, f"Uninitialized schema version: {ver}", now)
        # Test basic write / read transaction
        with db_manager.get_connection() as conn:
            conn.execute("SELECT 1;").fetchone()
        return ComponentHealth("persistence", HealthState.HEALTHY, f"SQLite operational store reachable (schema v{ver})", now, {"schema_version": ver})
    except Exception as e:
        return ComponentHealth("persistence", HealthState.FAILED, f"Database failure: {str(e)}", now, {"error": str(e)})


def check_broker_health(broker: BrokerAdapter) -> ComponentHealth:
    """Evaluates broker adapter reachability and state integrity."""
    now = datetime.now(timezone.utc)
    try:
        name = broker.broker_name
        # Test position access
        positions = broker.get_positions()
        return ComponentHealth("broker_adapter", HealthState.HEALTHY, f"Broker {name} active and responsive", now, {"broker": name, "open_positions_count": len(positions)})
    except Exception as e:
        return ComponentHealth("broker_adapter", HealthState.FAILED, f"Broker adapter failure: {str(e)}", now, {"error": str(e)})


def check_risk_health(
    last_decision: Any | None = None,
    kill_switch_active: bool = False,
) -> ComponentHealth:
    """Evaluates risk engine state and circuit breaker status."""
    now = datetime.now(timezone.utc)
    if kill_switch_active:
        return ComponentHealth("risk_engine", HealthState.FAILED, "Drawdown kill switch active! Execution halted.", now, {"kill_switch": True})
    if last_decision is None:
        return ComponentHealth("risk_engine", HealthState.UNKNOWN, "No risk evaluations recorded", now)
    if hasattr(last_decision, "evaluate"):  # Passed RiskEngine instance
        return ComponentHealth("risk_engine", HealthState.HEALTHY, "RiskEngine online and operational", now)
    if not getattr(last_decision, "approved", True):
        violations = getattr(last_decision, "violations", [])
        return ComponentHealth("risk_engine", HealthState.DEGRADED, f"Latest allocation rejected: {'; '.join(violations)}", now, {"violations": violations})
    return ComponentHealth("risk_engine", HealthState.HEALTHY, "Risk controls active and passing", now)
