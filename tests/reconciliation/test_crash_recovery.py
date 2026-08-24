"""Integration tests for crash recovery, idempotent state synchronization, and execution gating."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import pytest

from quant.broker.paper_broker import PaperBroker
from quant.core.enums import AssetClass, ExecutionMode, OrderSide, OrderStatus, OrderType
from quant.core.interfaces import Fill, Holding, Instrument, Order, PortfolioState
from quant.observability.alerts import AlertDispatcher, LoggingAlertSink
from quant.observability.events import AlertSeverity, EventType
from quant.persistence.database import DatabaseManager
from quant.persistence.repositories import (
    FillRepository,
    HoldingRepository,
    InstrumentRepository,
    OrderRepository,
    RunRepository,
    SnapshotRepository,
)
from quant.reconciliation.recovery import RecoveryManager
from quant.reconciliation.types import RecoveryState


def test_idempotent_recovery_double_run(tmp_path: Path):
    db_file = tmp_path / "test_idemp.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    run_repo = RunRepository(db)
    run_id = "run_recov_01"
    run_repo.create_run(run_id, ExecutionMode.PAPER, "macro_v1")

    inst_repo = InstrumentRepository(db)
    inst_repo.save_instrument(Instrument("SPY", AssetClass.EQUITY))

    # 1. Order was submitted and persisted to SQLite as SUBMITTED
    order_repo = OrderRepository(db)
    order = Order("ord_100", run_id, "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 50.0, status=OrderStatus.SUBMITTED)
    order_repo.save_order(order, ExecutionMode.PAPER, client_order_id="cl_100")

    # 2. Broker executed the fill, but process crashed before SQLite fill persistence
    broker = PaperBroker(initial_cash=100_000.0)
    broker_order = replace(order, status=OrderStatus.FILLED)
    broker._orders["ord_100"] = broker_order
    fill = Fill("fill_100", "ord_100", "SPY", OrderSide.BUY, 50.0, 400.0, 20.0, datetime.now(timezone.utc))
    broker._fills["fill_100"] = fill
    broker.cash = 79_980.0
    broker._holdings = {"SPY": Holding("SPY", 50.0, 400.0, 400.0, 20000.0)}

    # Initial state snapshot in SQLite was prior to fill
    snap_repo = SnapshotRepository(db)
    snap_repo.save_snapshot("snap_pre", run_id, PortfolioState(datetime.now(timezone.utc), 100000.0, {}, 100000.0, {}), ExecutionMode.PAPER, "macro_v1")

    alert_sink = LoggingAlertSink()
    dispatcher = AlertDispatcher([alert_sink])
    manager = RecoveryManager(db, dispatcher)

    # 3. First Recovery Run -> Ingests missing fill and synchronizes state
    state1, result1 = manager.reconcile_and_recover(run_id, ExecutionMode.PAPER, broker)
    assert state1 == RecoveryState.EXECUTION_PERMITTED
    assert result1.is_matched is True

    fill_repo = FillRepository(db)
    loaded_fill = fill_repo.get_fill("fill_100")
    assert loaded_fill is not None
    assert loaded_fill.quantity == 50.0

    updated_order = order_repo.get_order("ord_100")
    assert updated_order.status == OrderStatus.FILLED

    # 4. Second Recovery Run -> Idempotency Check (No duplicate records created)
    state2, result2 = manager.reconcile_and_recover(run_id, ExecutionMode.PAPER, broker)
    assert state2 == RecoveryState.EXECUTION_PERMITTED
    assert result2.is_matched is True

    # Confirm only exactly 1 fill and 1 order exists in SQLite
    fills_for_order = fill_repo.list_fills_for_order("ord_100")
    assert len(fills_for_order) == 1


def test_unresolved_mismatch_blocks_execution_and_alerts(tmp_path: Path):
    db_file = tmp_path / "test_unres.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    run_repo = RunRepository(db)
    run_id = "run_recov_02"
    run_repo.create_run(run_id, ExecutionMode.PAPER, "macro_v1")

    inst_repo = InstrumentRepository(db)
    inst_repo.save_instrument(Instrument("SPY", AssetClass.EQUITY))

    # Internal holdings has 100 shares
    holding_repo = HoldingRepository(db)
    holding_repo.save_holdings({"SPY": Holding("SPY", 100.0, 400.0, 400.0, 40000.0)})

    # Broker has 90 shares (unexplained discrepancy of 10 shares)
    broker = PaperBroker(initial_cash=100_000.0)
    broker._holdings = {"SPY": Holding("SPY", 90.0, 400.0, 400.0, 36000.0)}

    alert_sink = LoggingAlertSink()
    dispatcher = AlertDispatcher([alert_sink])
    manager = RecoveryManager(db, dispatcher)

    state, result = manager.reconcile_and_recover(run_id, ExecutionMode.PAPER, broker)
    assert state == RecoveryState.RECOVERY_REQUIRED
    assert result.is_matched is False

    # Asserts that a CRITICAL alert was dispatched
    assert len(alert_sink.alerts) == 1
    alert = alert_sink.alerts[0]
    assert alert.severity == AlertSeverity.CRITICAL
    assert alert.event_type == EventType.SYSTEM_RECOVERY_REQUIRED


def test_no_automatic_corrective_orders_placed(tmp_path: Path):
    db_file = tmp_path / "test_no_auto.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    run_repo = RunRepository(db)
    run_id = "run_recov_03"
    run_repo.create_run(run_id, ExecutionMode.PAPER, "macro_v1")

    inst_repo = InstrumentRepository(db)
    inst_repo.save_instrument(Instrument("SPY", AssetClass.EQUITY))

    # Internal: 100 shares. Broker: 95 shares.
    holding_repo = HoldingRepository(db)
    holding_repo.save_holdings({"SPY": Holding("SPY", 100.0, 400.0, 400.0, 40000.0)})

    broker = PaperBroker(initial_cash=100_000.0)
    broker._holdings = {"SPY": Holding("SPY", 95.0, 400.0, 400.0, 38000.0)}

    initial_broker_orders_count = len(broker.get_all_orders())

    manager = RecoveryManager(db)
    manager.reconcile_and_recover(run_id, ExecutionMode.PAPER, broker)

    # Broker orders count must NOT change (zero corrective trades submitted)
    assert len(broker.get_all_orders()) == initial_broker_orders_count


def test_case_i_restart_valid_persisted_state(tmp_path: Path):
    """CASE I: Restart with valid persisted state -> hydrate -> reconcile -> PASS."""
    db_file = tmp_path / "test_case_i.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    run_repo = RunRepository(db)
    run_id = "run_case_i"
    run_repo.create_run(run_id, ExecutionMode.PAPER, "macro_v1")
    InstrumentRepository(db).save_instrument(Instrument("SPY", AssetClass.EQUITY))

    # Persist state
    h_spy = Holding("SPY", 100.0, 400.0, 400.0, 40000.0)
    HoldingRepository(db).save_holdings({"SPY": h_spy})
    SnapshotRepository(db).save_snapshot(
        "snap_i", run_id, PortfolioState(datetime.now(timezone.utc), 60000.0, {"SPY": h_spy}, 100000.0, {"SPY": 0.40}),
        ExecutionMode.PAPER, "macro_v1"
    )

    # Broker matches persisted state
    broker = PaperBroker(initial_cash=60000.0)
    broker._holdings = {"SPY": h_spy}

    # Simulate restart by instantiating new PortfolioReconciler
    from quant.oms.reconciler import PortfolioReconciler
    reconciler = PortfolioReconciler(db)
    result = reconciler.reconcile_and_gate(run_id, ExecutionMode.PAPER, broker)
    assert result.passed is True


def test_case_j_and_k_restart_corrupted_state_blocks_execution(tmp_path: Path):
    """CASE J & K: Restart with corrupted/mismatched state or risk approved portfolio -> FAIL -> Execution Halted."""
    db_file = tmp_path / "test_case_j.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    run_repo = RunRepository(db)
    run_id = "run_case_j"
    run_repo.create_run(run_id, ExecutionMode.PAPER, "macro_v1")
    InstrumentRepository(db).save_instrument(Instrument("SPY", AssetClass.EQUITY))

    # Persist internal state: 100 shares SPY
    h_int = Holding("SPY", 100.0, 400.0, 400.0, 40000.0)
    HoldingRepository(db).save_holdings({"SPY": h_int})
    SnapshotRepository(db).save_snapshot(
        "snap_j", run_id, PortfolioState(datetime.now(timezone.utc), 60000.0, {"SPY": h_int}, 100000.0, {"SPY": 0.40}),
        ExecutionMode.PAPER, "macro_v1"
    )

    # Broker has corrupted / mismatched state (50 shares)
    broker = PaperBroker(initial_cash=60000.0)
    broker._holdings = {"SPY": Holding("SPY", 50.0, 400.0, 400.0, 20000.0)}

    from quant.core.exceptions import ReconciliationError
    from quant.oms.reconciler import ExecutionReconciliationGate, PortfolioReconciler
    reconciler = PortfolioReconciler(db)

    # Reconcile should fail
    result = reconciler.reconcile(run_id, ExecutionMode.PAPER, broker)
    assert result.passed is False

    # Execution gate must raise ReconciliationError and halt order submission
    with pytest.raises(ReconciliationError) as exc_info:
        ExecutionReconciliationGate.enforce_gate(result)

    assert "Execution Halted" in str(exc_info.value)
