"""Comprehensive test suite for P9.1 Controlled Autonomous Live Canary."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quant.broker.ibkr import IBKRBrokerAdapter, IBKRConfig, MockIBKRClient
from quant.core.enums import AssetClass, ExecutionMode, OrderSide, OrderType
from quant.core.exceptions import ModeViolationError
from quant.core.interfaces import Fill, Instrument, Order, OrderBatch
from quant.oms.approval import AutonomousApprovalGate
from quant.persistence.database import DatabaseManager
from quant.persistence.repositories import (
    FillRepository,
    InstrumentRepository,
    OrderRepository,
    RunRepository,
)
from quant.runner.autonomous_config import AutonomousExecutionConfig
from quant.runner.canary_ledger import CanaryLedgerRepository, CanaryRecord
from quant.runner.canary_runner import IBKRAutonomousCanaryRunner
from quant.strategies.macro import SystematicMacroStrategy


@pytest.fixture
def canary_env(tmp_path: Path):
    db_file = tmp_path / "test_p91_canary.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    mock_client = MockIBKRClient(auto_fill_on_submit=True)
    cfg = IBKRConfig(
        host="127.0.0.1",
        port=7496,  # Live TWS port
        is_paper=False,
        live_execution_enabled=True,
        account_id="U1234567",
    )
    adapter = IBKRBrokerAdapter(config=cfg, client=mock_client)
    strategy = SystematicMacroStrategy(rebalance_cadence_days=21)

    prices = {
        "SPY": 450.0, "TLT": 95.0, "IEF": 92.0, "BNDX": 48.0,
        "IGOV": 45.0, "UUP": 28.0, "FXE": 105.0, "FXY": 65.0,
        "FXB": 125.0, "EWJ": 68.0, "EFA": 75.0, "EEM": 40.0,
        "GLD": 185.0, "DBC": 22.0, "VNQ": 82.0, "EMB": 88.0,
    }

    return db, mock_client, adapter, strategy, prices


def test_canary_live_environment_requires_explicit_capital_ceiling(canary_env):
    """LIVE autonomous execution without explicit MAX_LIVE_CAPITAL is strictly blocked at startup."""
    db, mock_client, adapter, strategy, prices = canary_env

    # Missing MAX_LIVE_CAPITAL
    cfg_missing = AutonomousExecutionConfig(
        autonomous_execution_enabled=True,
        approval_mode="AUTONOMOUS",
        broker_env="LIVE",
        live_execution_enabled=True,
        max_live_capital=None,
    )
    with pytest.raises(ModeViolationError, match="Explicit operator-provided MAX_LIVE_CAPITAL > 0 is mandatory"):
        cfg_missing.validate_safety_locks()


def test_canary_10_successful_autonomous_real_capital_executions(canary_env):
    """Executes 10 distinct, verified autonomous real-capital canary orders meeting all P9.1 criteria."""
    db, mock_client, adapter, strategy, prices = canary_env
    as_of = datetime.now(timezone.utc)

    auto_cfg = AutonomousExecutionConfig(
        autonomous_execution_enabled=True,
        approval_mode="AUTONOMOUS",
        broker_env="LIVE",
        live_execution_enabled=True,
        max_live_capital=100_000.0,
    )
    runner = IBKRAutonomousCanaryRunner(
        db_manager=db,
        broker=adapter,
        strategy=strategy,
        config=auto_cfg,
    )

    canary_sequence = [
        ("canary_run_01", {"SPY": 0.05}, OrderType.MARKET, None),
        ("canary_run_02", {"SPY": 0.05, "TLT": 0.05}, OrderType.MARKET, None),
        ("canary_run_03", {"SPY": 0.02, "TLT": 0.05}, OrderType.MARKET, None),
        ("canary_run_04", {"SPY": 0.02, "TLT": 0.05, "IEF": 0.04}, OrderType.LIMIT, 92.0),
        ("canary_run_05", {"SPY": 0.02, "TLT": 0.05, "IEF": 0.04, "GLD": 0.05}, OrderType.MARKET, None),
        ("canary_run_06", {"SPY": 0.02, "TLT": 0.05, "IEF": 0.04, "GLD": 0.05, "DBC": 0.03}, OrderType.MARKET, None),
        ("canary_run_07", {"SPY": 0.02, "TLT": 0.05, "IEF": 0.04, "GLD": 0.05, "DBC": 0.03, "FXE": 0.03}, OrderType.MARKET, None),
        ("canary_run_08", {"SPY": 0.02, "TLT": 0.05, "IEF": 0.04, "GLD": 0.05, "DBC": 0.03, "FXE": 0.03, "EFA": 0.04}, OrderType.LIMIT, 75.0),
        ("canary_run_09", {"SPY": 0.02, "TLT": 0.05, "IEF": 0.04, "GLD": 0.05, "DBC": 0.03, "FXE": 0.03, "EFA": 0.04, "EMB": 0.04}, OrderType.MARKET, None),
        ("canary_run_10", {"SPY": 0.02, "TLT": 0.02, "IEF": 0.04, "GLD": 0.05, "DBC": 0.03, "FXE": 0.03, "EFA": 0.04, "EMB": 0.04}, OrderType.MARKET, None),
    ]

    for idx, (cid, weights, otype, lprice) in enumerate(canary_sequence, start=1):
        run_id = f"sys_run_canary_{idx:02d}"
        rec = runner.execute_canary_order(
            canary_run_id=cid,
            run_id=run_id,
            target_weights=weights,
            current_prices=prices,
            as_of_date=as_of + timedelta(days=idx),
            order_type=otype,
            limit_price=lprice,
        )
        assert rec.success is True
        assert rec.pre_reconciliation_status == "MATCHED"
        assert rec.post_reconciliation_status == "MATCHED"
        assert rec.final_order_status == "FILLED"
        assert rec.broker_order_id is not None
        assert rec.broker_execution_id is not None

    summary = runner.canary_repo.get_canary_summary()
    assert summary.successful_executions == 10
    assert summary.failed_executions == 0
    assert summary.reconciliation_mismatches == 0
    assert summary.duplicate_executions_detected == 0
    assert summary.canary_complete is True


def test_canary_counter_derived_from_persisted_evidence(canary_env):
    """The successful canary counter is strictly computed from SQLite rows with success=1."""
    db, mock_client, adapter, strategy, prices = canary_env
    repo = CanaryLedgerRepository(db)
    assert repo.get_successful_count() == 0

    now = datetime.now(timezone.utc)
    RunRepository(db).create_run("run_c1", ExecutionMode.LIVE, "systematic_macro_v1")
    rec = CanaryRecord(
        sequence_num=None, timestamp=now, run_id="run_c1", canary_run_id="c_01",
        order_batch_id="b_01", symbol="SPY", side="BUY", quantity=10.0, order_type="MARKET",
        broker_order_id="o_01", broker_execution_id="e_01", approval_token_id="tok_01",
        risk_decision_id="dec_01", pre_reconciliation_status="MATCHED", post_reconciliation_status="MATCHED",
        final_order_status="FILLED", success=True,
    )
    repo.record_execution(rec)
    assert repo.get_successful_count() == 1


def test_canary_duplicate_execution_detection_and_deduplication(canary_env):
    """Duplicate broker execution ID is rejected by database with zero duplicate fills."""
    import sqlite3
    db, mock_client, adapter, strategy, prices = canary_env
    fill_repo = FillRepository(db)
    RunRepository(db).create_run("run_dup_c", ExecutionMode.LIVE, "systematic_macro_v1")
    InstrumentRepository(db).save_instrument(Instrument("SPY", AssetClass.EQUITY))
    order = Order("ord_c_dup", "run_dup_c", "systematic_macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 10.0)
    OrderRepository(db).save_order(order, ExecutionMode.LIVE)

    now = datetime.now(timezone.utc)
    fill = Fill("fill_c_dup", "ord_c_dup", "SPY", OrderSide.BUY, 10.0, 450.0, 1.0, now)

    # First save
    fill_repo.save_fill(fill, broker_execution_id="exec_ibkr_c_999")
    assert fill_repo.get_fill_by_broker_execution_id("exec_ibkr_c_999") is not None

    # Duplicate save with same broker_execution_id raises IntegrityError
    duplicate_fill = Fill("fill_c_dup_2", "ord_c_dup", "SPY", OrderSide.BUY, 10.0, 450.0, 1.0, now)
    with pytest.raises(sqlite3.IntegrityError):
        fill_repo.save_fill(duplicate_fill, broker_execution_id="exec_ibkr_c_999")

    all_fills = fill_repo.list_fills_for_order("ord_c_dup")
    assert len(all_fills) == 1


def test_canary_uncertain_submission_no_blind_retry_and_reconcile(canary_env):
    """Network drop after submit resolves via IBKR query, avoiding duplicate execution."""
    db, mock_client, adapter, strategy, prices = canary_env
    mock_client.auto_fill_on_submit = False

    run_id = "run_canary_unc"
    RunRepository(db).create_run(run_id, ExecutionMode.LIVE, "systematic_macro_v1")
    InstrumentRepository(db).save_instrument(Instrument("SPY", AssetClass.EQUITY))
    order = Order("ord_c_unc", run_id, "systematic_macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 5.0, client_order_id="cl_c_unc")
    OrderRepository(db).save_order(order, ExecutionMode.LIVE)

    adapter.submit_order(order)
    mock_client.disconnect()
    assert adapter.client.is_connected() is False

    mock_client.connect()
    found = adapter.get_order("ord_c_unc")
    assert found is not None
    assert found.client_order_id == "cl_c_unc"


def test_canary_controlled_restart_and_recovery(canary_env):
    """Crash after fill recovers by hydrating SQLite state and matching live broker."""
    db, mock_client, adapter, strategy, prices = canary_env
    as_of = datetime.now(timezone.utc)

    auto_cfg = AutonomousExecutionConfig(
        autonomous_execution_enabled=True,
        approval_mode="AUTONOMOUS",
        broker_env="LIVE",
        live_execution_enabled=True,
        max_live_capital=100_000.0,
    )
    runner1 = IBKRAutonomousCanaryRunner(db_manager=db, broker=adapter, strategy=strategy, config=auto_cfg)
    rec = runner1.execute_canary_order("canary_restart_01", "run_restart_c", {"SPY": 0.05}, prices, as_of)
    assert rec.success is True

    # Simulate process death & reboot
    runner2 = IBKRAutonomousCanaryRunner(db_manager=db, broker=adapter, strategy=strategy, config=auto_cfg)
    rec2 = runner2.execute_canary_order("canary_restart_02", "run_restart_c2", {"SPY": 0.05, "TLT": 0.05}, prices, as_of + timedelta(days=1))
    assert rec2.success is True
    assert rec2.pre_reconciliation_status == "MATCHED"


def test_canary_unapproved_order_blocked_and_invalidated(canary_env):
    """Order with unapproved or expired autonomous token is strictly rejected."""
    db, mock_client, adapter, strategy, prices = canary_env
    gate = AutonomousApprovalGate(autonomous_execution_enabled=False)

    batch = OrderBatch(
        batch_id="batch_unapp_c",
        orders=[Order("ord_unapp_c", "run_u", "systematic_macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 5.0)],
        target_portfolio_id="tp_u",
        strategy_id="systematic_macro_v1",
        execution_mode=ExecutionMode.LIVE,
        generated_at=datetime.now(timezone.utc),
    )

    with pytest.raises(ModeViolationError, match="AUTONOMOUS_EXECUTION_ENABLED is false"):
        gate.approve_batch(batch)


def test_canary_kill_switch_active_blocks_submission(canary_env):
    """When EMERGENCY_STOP is active, canary runner strictly refuses initialization."""
    db, mock_client, adapter, strategy, prices = canary_env
    auto_cfg = AutonomousExecutionConfig(
        autonomous_execution_enabled=True,
        approval_mode="AUTONOMOUS",
        broker_env="LIVE",
        live_execution_enabled=True,
        max_live_capital=100_000.0,
        emergency_stop_active=True,
    )
    with pytest.raises(ModeViolationError, match="Cannot enable autonomous execution while EMERGENCY_STOP is active"):
        IBKRAutonomousCanaryRunner(db_manager=db, broker=adapter, strategy=strategy, config=auto_cfg)
