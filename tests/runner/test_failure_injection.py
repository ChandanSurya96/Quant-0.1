"""Failure injection tests verifying fail-closed execution, alerting, and restart recovery."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import pytest

from quant.broker.paper_broker import PaperBroker
from quant.core.enums import AssetClass, ExecutionMode, OrderSide, OrderStatus, OrderType
from quant.core.interfaces import Fill, Holding, Instrument, Order, PortfolioState, TargetPortfolio
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
from quant.runner.models import RunStatus
from quant.runner.runner import PaperTradingRunner
from quant.strategies.macro import SystematicMacroStrategy


@pytest.fixture
def fail_injection_setup(tmp_path: Path):
    db_file = tmp_path / "test_fail_inj.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    broker = PaperBroker(initial_cash=100_000.0)
    strategy = SystematicMacroStrategy(rebalance_cadence_days=21)
    alert_sink = LoggingAlertSink()
    dispatcher = AlertDispatcher([alert_sink])

    runner = PaperTradingRunner(
        db_manager=db,
        broker=broker,
        strategy=strategy,
        alert_dispatcher=dispatcher,
    )

    df = pd.read_csv("tests/fixtures/synthetic_macro_12etf.csv", index_col=0, parse_dates=True)
    return db, broker, strategy, runner, alert_sink, df


def test_failure_injection_market_data_anomaly_gap(fail_injection_setup):
    """Single-bar +25% jump in SPY triggers DataValidationGate failure and zero orders."""
    db, broker, strategy, runner, alert_sink, df = fail_injection_setup
    corrupt_df = df.iloc[:800].copy()
    corrupt_df.iloc[-1, corrupt_df.columns.get_loc("SPY")] *= 1.25  # +25% jump

    record, report = runner.run_once(
        run_id="run_inj_anomaly",
        as_of_date=corrupt_df.index[-1],
        market_data=corrupt_df,
        is_rebalance_day=True,
    )

    assert record.status == RunStatus.VALIDATION_FAILED
    assert "rejected market data" in record.error_message
    assert record.orders_count == 0
    assert len(broker.get_all_orders()) == 0


def test_failure_injection_reconciliation_corruption_halts_and_alerts(fail_injection_setup):
    """Corrupted internal state fails pre-execution reconciliation, emits CRITICAL alert, and halts execution."""
    db, broker, strategy, runner, alert_sink, df = fail_injection_setup
    window_df = df.iloc[:800]

    # Pre-seed corrupted state
    InstrumentRepository(db).save_instrument(Instrument("SPY", AssetClass.EQUITY))
    HoldingRepository(db).save_holdings({"SPY": Holding("SPY", 100.0, 400.0, 400.0, 40000.0)})
    broker._holdings = {"SPY": Holding("SPY", 80.0, 400.0, 400.0, 32000.0)}

    record, report = runner.run_once(
        run_id="run_inj_rec_fail",
        as_of_date=window_df.index[-1],
        market_data=window_df,
        is_rebalance_day=True,
    )

    assert record.status == RunStatus.RECONCILIATION_FAILED
    assert record.pre_reconciliation_status == "MISMATCHED"
    assert record.orders_count == 0

    # Verify that a CRITICAL alert was emitted
    assert len(alert_sink.alerts) >= 1
    assert any(a.severity == AlertSeverity.CRITICAL for a in alert_sink.alerts)
    assert any(a.event_type == EventType.SYSTEM_RECOVERY_REQUIRED for a in alert_sink.alerts)


def test_failure_injection_restart_after_fill_and_recovery(tmp_path: Path):
    """Simulates process kill after broker fill; recovery manager synchronizes state so next run succeeds."""
    db_file = tmp_path / "test_restart_fill.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    run_repo = RunRepository(db)
    run_id = "run_inj_restart"
    run_repo.create_run(run_id, ExecutionMode.PAPER, "macro_v1")
    InstrumentRepository(db).save_instrument(Instrument("SPY", AssetClass.EQUITY))

    # Order was created and submitted
    order_repo = OrderRepository(db)
    order = Order("ord_inj_1", run_id, "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 50.0, status=OrderStatus.SUBMITTED)
    order_repo.save_order(order, ExecutionMode.PAPER)

    # Broker executed fill, but process died before fill was recorded in SQLite
    broker = PaperBroker(initial_cash=100_000.0)
    broker_order = Order("ord_inj_1", run_id, "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 50.0, status=OrderStatus.FILLED)
    broker._orders["ord_inj_1"] = broker_order
    fill = Fill("fill_inj_1", "ord_inj_1", "SPY", OrderSide.BUY, 50.0, 400.0, 20.0, datetime.now(timezone.utc))
    broker._fills["fill_inj_1"] = fill
    broker.cash = 79_980.0
    broker._holdings = {"SPY": Holding("SPY", 50.0, 400.0, 400.0, 20000.0)}

    # Initial snapshot before kill
    SnapshotRepository(db).save_snapshot("snap_pre_inj", run_id, PortfolioState(datetime.now(timezone.utc), 100000.0, {}, 100000.0, {}), ExecutionMode.PAPER, "macro_v1")

    # Run Recovery Manager to heal the state
    recovery_mgr = RecoveryManager(db)
    recov_state, rec_res = recovery_mgr.reconcile_and_recover(run_id, ExecutionMode.PAPER, broker)
    assert rec_res.passed is True

    # Next paper cycle should now succeed cleanly
    strategy = SystematicMacroStrategy(rebalance_cadence_days=21)
    runner = PaperTradingRunner(db_manager=db, broker=broker, strategy=strategy)
    df = pd.read_csv("tests/fixtures/synthetic_macro_12etf.csv", index_col=0, parse_dates=True)
    window_df = df.iloc[:800]

    record2, report2 = runner.run_once(
        run_id="run_inj_next_day",
        as_of_date=window_df.index[-1],
        market_data=window_df,
        is_rebalance_day=False,  # Drift day
    )

    assert record2.status == RunStatus.COMPLETED
    assert record2.pre_reconciliation_status == "MATCHED"
    assert record2.post_reconciliation_status == "MATCHED"
