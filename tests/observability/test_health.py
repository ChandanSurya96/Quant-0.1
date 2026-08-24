"""Unit tests for component health checks and fail-closed execution policies."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import pytest

from quant.broker.paper_broker import PaperBroker
from quant.core.enums import ExecutionMode
from quant.core.interfaces import RiskDecision
from quant.observability.events import HealthState, SystemStatus
from quant.observability.health import (
    ComponentHealth,
    SystemHealthSnapshot,
    check_broker_health,
    check_data_health,
    check_persistence_health,
    check_risk_health,
)
from quant.persistence.database import DatabaseManager


def test_data_provider_health():
    now = datetime.now(timezone.utc)

    h_healthy = check_data_health(last_fetch_time=now, is_stale=False, provider_available=True)
    assert h_healthy.state == HealthState.HEALTHY

    h_stale = check_data_health(last_fetch_time=now, is_stale=True, provider_available=True)
    assert h_stale.state == HealthState.DEGRADED

    h_failed = check_data_health(last_fetch_time=now, is_stale=False, provider_available=False)
    assert h_failed.state == HealthState.FAILED

    h_unknown = check_data_health(last_fetch_time=None, is_stale=False, provider_available=True)
    assert h_unknown.state == HealthState.UNKNOWN


def test_persistence_health(tmp_path: Path):
    db_file = tmp_path / "test_health.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    h_ok = check_persistence_health(db)
    assert h_ok.state == HealthState.HEALTHY
    assert h_ok.details["schema_version"] == 1

    # Uninitialized DB
    db_bad = DatabaseManager(tmp_path / "uninit.db")
    h_bad = check_persistence_health(db_bad)
    assert h_bad.state == HealthState.FAILED


def test_broker_health():
    broker = PaperBroker(initial_cash=100000.0)
    h_ok = check_broker_health(broker)
    assert h_ok.state == HealthState.HEALTHY
    assert h_ok.details["broker"] == "PaperBroker"


def test_risk_health():
    now = datetime.now(timezone.utc)
    dec_pass = RiskDecision(timestamp=now, approved=True)
    h_ok = check_risk_health(dec_pass)
    assert h_ok.state == HealthState.HEALTHY

    dec_fail = RiskDecision(timestamp=now, approved=False, violations=["Gross exposure breach"])
    h_deg = check_risk_health(dec_fail)
    assert h_deg.state == HealthState.DEGRADED

    h_kill = check_risk_health(dec_pass, kill_switch_active=True)
    assert h_kill.state == HealthState.FAILED


def test_system_health_snapshot_execution_blocking_policy():
    now = datetime.now(timezone.utc)
    h_ok = ComponentHealth("ok", HealthState.HEALTHY, "OK")
    h_deg = ComponentHealth("deg", HealthState.DEGRADED, "Degraded")
    h_fail = ComponentHealth("fail", HealthState.FAILED, "Failed")
    h_unk = ComponentHealth("unk", HealthState.UNKNOWN, "Unknown")

    # 1. PAPER Mode: All Healthy -> Execution Permitted
    snap_healthy = SystemHealthSnapshot(
        timestamp=now,
        execution_mode=ExecutionMode.PAPER,
        overall_status=SystemStatus.RUNNING,
        data_health=h_ok,
        persistence_health=h_ok,
        broker_health=h_ok,
        risk_health=h_ok,
    )
    assert snap_healthy.is_execution_permitted() is True

    # 2. PAPER Mode: Stale / Degraded Data -> Execution Blocked
    snap_stale = SystemHealthSnapshot(
        timestamp=now,
        execution_mode=ExecutionMode.PAPER,
        overall_status=SystemStatus.DEGRADED,
        data_health=h_deg,
        persistence_health=h_ok,
        broker_health=h_ok,
        risk_health=h_ok,
    )
    assert snap_stale.is_execution_permitted() is False

    # 3. PAPER Mode: UNKNOWN Risk State -> Execution Blocked (Fail-Closed)
    snap_unk = SystemHealthSnapshot(
        timestamp=now,
        execution_mode=ExecutionMode.PAPER,
        overall_status=SystemStatus.RUNNING,
        data_health=h_ok,
        persistence_health=h_ok,
        broker_health=h_ok,
        risk_health=h_unk,
    )
    assert snap_unk.is_execution_permitted() is False

    # 4. PAPER Mode: Recovery Required -> Execution Blocked
    snap_rec = SystemHealthSnapshot(
        timestamp=now,
        execution_mode=ExecutionMode.PAPER,
        overall_status=SystemStatus.RECOVERY_REQUIRED,
        data_health=h_ok,
        persistence_health=h_ok,
        broker_health=h_ok,
        risk_health=h_ok,
        recovery_required=True,
    )
    assert snap_rec.is_execution_permitted() is False


def test_system_health_snapshot_serialization():
    now = datetime.now(timezone.utc)
    h_ok = ComponentHealth("data", HealthState.HEALTHY, "Feed OK")
    snap = SystemHealthSnapshot(
        timestamp=now,
        execution_mode=ExecutionMode.PAPER,
        overall_status=SystemStatus.RUNNING,
        data_health=h_ok,
        persistence_health=h_ok,
        broker_health=h_ok,
        risk_health=h_ok,
    )
    d = snap.to_dict()
    assert d["execution_mode"] == "PAPER"
    assert d["overall_status"] == "RUNNING"
    assert d["execution_permitted"] is True
    assert d["data_health"]["state"] == "HEALTHY"
