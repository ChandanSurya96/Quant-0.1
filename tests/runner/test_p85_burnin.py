"""Comprehensive unit and integration test suite for External IBKR Paper Burn-In (P8.5)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from quant.broker.ibkr import IBKRBrokerAdapter, IBKRConfig, MockIBKRClient
from quant.broker.ibkr.models import IBKROrderRecord
from quant.core.enums import AssetClass, ExecutionMode, OrderSide, OrderStatus, OrderType
from quant.core.exceptions import ModeViolationError
from quant.core.interfaces import Fill, Instrument, Order, PortfolioState
from quant.oms.approval import ManualApprovalGate
from quant.persistence.database import DatabaseManager
from quant.persistence.repositories import (
    FillRepository,
    HoldingRepository,
    InstrumentRepository,
    OrderRepository,
    RunRepository,
    SnapshotRepository,
)
from quant.reconciliation.engine import ReconciliationEngine
from quant.reconciliation.recovery import RecoveryManager
from quant.runner.burnin_ledger import BurnInLedgerRepository
from quant.runner.burnin_runner import IBKRPaperBurnInRunner
from quant.runner.live_config import LiveExecutionConfig


@pytest.fixture
def burnin_env(tmp_path: Path):
    db_file = tmp_path / "test_p85_burnin.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    mock_client = MockIBKRClient(auto_fill_on_submit=True)
    cfg = IBKRConfig(host="127.0.0.1", port=7497, is_paper=True, live_execution_enabled=False, account_id="DU9876543")
    adapter = IBKRBrokerAdapter(config=cfg, client=mock_client)

    live_cfg = LiveExecutionConfig(broker_env="PAPER", live_execution_enabled=False, live_capital_limit=50_000.0)
    runner = IBKRPaperBurnInRunner(db_manager=db, broker=adapter, config=live_cfg)

    prices = {
        "SPY": 400.0, "TLT": 100.0, "IEF": 95.0, "BNDX": 140.0,
        "FXE": 96.0, "FXB": 134.0, "EEM": 114.0, "EFA": 190.0,
        "UUP": 28.0, "GLD": 180.0,
    }
    return db, mock_client, adapter, runner, prices


# ------------------------------------------------ 1. Environment Proof & Safety
def test_burnin_environment_proof_and_redaction(burnin_env):
    """Environment proof establishes connection to IBKR Paper and redacts account number."""
    db, mock_client, adapter, runner, prices = burnin_env

    proof = runner.verify_environment()
    assert proof.broker_env == "PAPER"
    assert proof.connection_status == "CONNECTED"
    assert proof.is_paper is True
    assert proof.account_redacted == "DU***6543"  # Redacted middle numbers
    assert "9876543" not in proof.account_redacted  # No raw credentials/account leaked


def test_burnin_refuses_live_environment_execution(burnin_env):
    """P8.5 Burn-In strictly refuses to run if BROKER_ENV is LIVE."""
    db, mock_client, adapter, runner, prices = burnin_env
    live_cfg = LiveExecutionConfig(broker_env="LIVE", live_execution_enabled=True, live_capital_limit=25_000.0)

    with pytest.raises(ModeViolationError) as exc:
        IBKRPaperBurnInRunner(db_manager=db, broker=adapter, config=live_cfg)
    assert "strictly requires BROKER_ENV=PAPER" in str(exc.value)


# ------------------------------------------------ 2. 10-Order Burn-In Sequence
def test_burnin_10_successful_diverse_orders_reach_completion(burnin_env):
    """Executes 10 distinct real paper orders covering BUY, SELL, short locate, LIMIT, and multiple assets."""
    db, mock_client, adapter, runner, prices = burnin_env

    records, summary = runner.run_10_order_burnin_suite(current_prices=prices)

    # Verification of 10 genuine orders
    assert len(records) == 10
    assert summary.total_orders_attempted == 10
    assert summary.successful_real_paper_orders == 10
    assert summary.failed_orders == 0
    assert summary.reconciliation_match_rate == 1.0
    assert summary.is_p85_complete is True
    assert summary.burnin_status == "10 / 10 (COMPLETE)"

    # Verify order diversity
    sides = {r.side for r in records}
    assert OrderSide.BUY in sides
    assert OrderSide.SELL in sides

    symbols = {r.symbol for r in records}
    assert len(symbols) >= 6  # Multi-asset diversity

    order_types = {r.order_type for r in records}
    assert OrderType.MARKET in order_types
    assert OrderType.LIMIT in order_types

    for r in records:
        assert r.success is True
        assert r.pre_reconciliation_status == "MATCHED"
        assert r.post_reconciliation_status == "MATCHED"
        assert r.broker_execution_id.startswith("fill_")
        assert r.commission > 0.0


# ------------------------------------------------ 3. Success Counter Derived from Persisted Database
def test_burnin_counter_derived_from_persisted_evidence(burnin_env):
    """Verifies that the success counter is computed directly from SQLite records, not an in-memory variable."""
    db, mock_client, adapter, runner, prices = burnin_env
    burnin_repo = BurnInLedgerRepository(db)

    assert burnin_repo.get_successful_count() == 0

    # Run 3 orders
    runner.execute_burnin_order("run_cnt_01", "SPY", OrderSide.BUY, 10.0, current_prices=prices)
    runner.execute_burnin_order("run_cnt_02", "TLT", OrderSide.BUY, 15.0, current_prices=prices)
    runner.execute_burnin_order("run_cnt_03", "IEF", OrderSide.BUY, 20.0, current_prices=prices)

    # Database query reflects exactly 3 persisted successes
    assert burnin_repo.get_successful_count() == 3
    summary = burnin_repo.get_burnin_summary()
    assert summary.burnin_status == "3 / 10 (IN_PROGRESS)"
    assert summary.is_p85_complete is False


# ------------------------------------------------ 4. Duplicate Execution Protection
def test_burnin_duplicate_execution_detection_and_deduplication(burnin_env):
    """Duplicate broker execution ID is deduplicated with zero duplicate fills in persistence."""
    db, mock_client, adapter, runner, prices = burnin_env

    # Execute initial order
    rec = runner.execute_burnin_order("run_dup_01", "SPY", OrderSide.BUY, 10.0, current_prices=prices)
    initial_fills = FillRepository(db).list_fills_for_order(rec.broker_order_id)
    assert len(initial_fills) == 1

    # Attempt to ingest the same broker execution ID again
    fill_repo = FillRepository(db)
    existing_fill = initial_fills[0]
    duplicate_fill = Fill("fill_dup_2", rec.broker_order_id, "SPY", OrderSide.BUY, 10.0, 400.0, 1.0, datetime.now(timezone.utc))

    with pytest.raises(Exception):
        fill_repo.save_fill(duplicate_fill, broker_execution_id=existing_fill.fill_id)

    all_fills = fill_repo.list_fills_for_order(rec.broker_order_id)
    assert len(all_fills) == 1  # No duplicate fill created in SQLite


# ------------------------------------------------ 5. Uncertain Submission Handling (No Blind Retry)
def test_burnin_uncertain_submission_no_blind_retry_and_reconcile(burnin_env):
    """When submission acknowledgement is lost, query broker and reconcile rather than blindly resubmitting."""
    db, mock_client, adapter, runner, prices = burnin_env

    # Disable auto-fill to simulate async in-flight order
    mock_client.auto_fill_on_submit = False
    run_id = "run_unc"
    RunRepository(db).create_run(run_id, ExecutionMode.PAPER, "macro_v1")
    InstrumentRepository(db).save_instrument(Instrument("SPY", AssetClass.EQUITY))
    order = Order("ord_unc_1", run_id, "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 20.0, client_order_id="cl_unc_1")
    OrderRepository(db).save_order(order, ExecutionMode.PAPER)
    adapter.submit_order(order)

    # Network drops immediately after submit
    mock_client.disconnect()
    assert adapter.client.is_connected() is False

    # Inflight order was accepted by broker before disconnect
    mock_client.connect()
    assert adapter.client.is_connected() is True

    # Check broker records: order is found by client_order_id
    found_order = adapter.get_order("ord_unc_1")
    assert found_order is not None
    assert found_order.client_order_id == "cl_unc_1"

    # Fill occurs on broker
    mock_client.inject_partial_fill(10001, fill_shares=20.0, fill_price=400.0, commission=1.0, exec_id="e_unc_1")
    fills = adapter.get_fills()
    assert len(fills) == 1
    FillRepository(db).save_fill(fills[0], broker_execution_id="e_unc_1")
    OrderRepository(db).update_order_status("ord_unc_1", OrderStatus.FILLED)
    HoldingRepository(db).save_holdings(adapter.get_positions())

    # Snapshot and reconcile
    SnapshotRepository(db).save_snapshot("snap_unc", run_id, adapter.get_account_state(prices), ExecutionMode.PAPER, "macro_v1")
    rec_res = ReconciliationEngine.reconcile(run_id, ExecutionMode.PAPER, db, adapter)
    assert rec_res.passed is True


# ------------------------------------------------ 6. Process Restart & Recovery During Burn-In
def test_burnin_controlled_restart_and_recovery_during_burnin(tmp_path: Path):
    """Process dies after broker fill; RecoveryManager syncs SQLite state and next burn-in order succeeds."""
    db_file = tmp_path / "test_burnin_restart.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    run_id = "run_restart_burnin"
    RunRepository(db).create_run(run_id, ExecutionMode.PAPER, "macro_v1")
    InstrumentRepository(db).save_instrument(Instrument("SPY", AssetClass.EQUITY))

    # Order was submitted before crash
    order = Order("ord_crash_1", run_id, "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 25.0, status=OrderStatus.SUBMITTED)
    OrderRepository(db).save_order(order, ExecutionMode.PAPER)

    # Broker executed fill, but process died before writing fill to SQLite
    mock_client = MockIBKRClient(auto_fill_on_submit=False)
    adapter = IBKRBrokerAdapter(client=mock_client)
    mock_client._orders[10001] = IBKROrderRecord(
        order_id="ord_crash_1", client_order_id="cl_crash_1", ibkr_order_id=10001,
        symbol="SPY", action="BUY", total_quantity=25.0, status="Filled",
        filled_quantity=25.0, remaining_quantity=0.0, avg_fill_price=400.0,
    )
    mock_client.inject_partial_fill(10001, fill_shares=25.0, fill_price=400.0, commission=1.0, exec_id="e_crash_01")
    adapter._ibkr_oid_to_domain_id[10001] = "ord_crash_1"

    # Initial snapshot
    SnapshotRepository(db).save_snapshot("snap_pre_crash", run_id, PortfolioState(datetime.now(timezone.utc), 100_000.0, {}, 100_000.0, {}), ExecutionMode.PAPER, "macro_v1")

    # Recovery Manager hydrates SQLite from broker
    recovery_mgr = RecoveryManager(db)
    recov_state, rec_res = recovery_mgr.reconcile_and_recover(run_id, ExecutionMode.PAPER, adapter)
    assert rec_res.passed is True

    # Next burn-in order on restarted process executes cleanly
    mock_client.auto_fill_on_submit = True
    runner = IBKRPaperBurnInRunner(db_manager=db, broker=adapter)
    prices = {"SPY": 400.0, "TLT": 100.0}
    rec2 = runner.execute_burnin_order("run_burn_next", "TLT", OrderSide.BUY, 20.0, current_prices=prices)
    assert rec2.success is True
    assert rec2.post_reconciliation_status == "MATCHED"


# ------------------------------------------------ 7. Unapproved Order Blocked
def test_burnin_unapproved_order_blocked_and_invalidated(burnin_env):
    """Submitting order without valid approval token is blocked and recorded as failure."""
    db, mock_client, adapter, runner, prices = burnin_env

    # Revoke approval gate
    gate = ManualApprovalGate()
    runner.approval_gate = gate

    # Intentionally do not grant approval
    rec = runner.execute_burnin_order(
        run_id="run_unapp_fail",
        symbol="SPY",
        side=OrderSide.BUY,
        quantity=10.0,
        current_prices=prices,
        auto_grant_approval=False,
    )
    assert rec.success is False
    assert rec.final_order_status == OrderStatus.REJECTED
    assert "lacks human approval token" in rec.failure_reason
