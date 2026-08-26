"""Unit tests for Portfolio Reconciliation engine (Positions, Orders, Fills, Cash, NAV)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from quant.broker.paper_broker import PaperBroker
from quant.core.enums import AssetClass, ExecutionMode, OrderSide, OrderStatus, OrderType
from quant.core.interfaces import Fill, Holding, Instrument, Order, PortfolioState
from quant.persistence.database import DatabaseManager
from quant.persistence.repositories import (
    HoldingRepository,
    InstrumentRepository,
    OrderRepository,
    ReconciliationRepository,
    RunRepository,
    SnapshotRepository,
)
from quant.reconciliation.engine import ReconciliationEngine
from quant.reconciliation.types import (
    ReconciliationConfig,
    ReconciliationIssueType,
    ReconciliationStatus,
)


@pytest.fixture
def setup_db_and_broker(tmp_path: Path):
    db_file = tmp_path / "test_rec.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    run_repo = RunRepository(db)
    run_id = "run_rec_01"
    run_repo.create_run(run_id, ExecutionMode.PAPER, "macro_v1")

    inst_repo = InstrumentRepository(db)
    inst_repo.save_instrument(Instrument("SPY", AssetClass.EQUITY))
    inst_repo.save_instrument(Instrument("TLT", AssetClass.BOND))

    broker = PaperBroker(initial_cash=100_000.0)
    return db, broker, run_id


# ------------------------------------------------ 1. Position Matching
def test_position_reconciliation_exact_match(setup_db_and_broker):
    db, broker, run_id = setup_db_and_broker
    holding_repo = HoldingRepository(db)
    snap_repo = SnapshotRepository(db)

    # Internal holdings: 100 SPY, -200 TLT
    h_spy = Holding("SPY", 100.0, 400.0, 400.0, 40000.0)
    h_tlt = Holding("TLT", -200.0, 100.0, 100.0, -20000.0)
    holding_repo.save_holdings({"SPY": h_spy, "TLT": h_tlt})

    # Internal snapshot: cash $80,000, NAV $100,000
    now = datetime.now(timezone.utc)
    state = PortfolioState(now, cash=80000.0, holdings={"SPY": h_spy, "TLT": h_tlt}, nav=100000.0, realized_weights={"SPY": 0.40, "TLT": -0.20})
    snap_repo.save_snapshot("snap_01", run_id, state, ExecutionMode.PAPER, "macro_v1")

    # Broker state matches exactly
    broker.cash = 80000.0
    broker._holdings = {"SPY": h_spy, "TLT": h_tlt}

    result = ReconciliationEngine.reconcile(run_id, ExecutionMode.PAPER, db, broker)
    assert result.status == ReconciliationStatus.MATCHED
    assert result.is_matched is True
    assert len(result.issues) == 0


def test_position_reconciliation_missing_broker_position(setup_db_and_broker):
    db, broker, run_id = setup_db_and_broker
    holding_repo = HoldingRepository(db)

    # Internal has SPY 100 shares, broker has nothing
    h_spy = Holding("SPY", 100.0, 400.0, 400.0, 40000.0)
    holding_repo.save_holdings({"SPY": h_spy})

    result = ReconciliationEngine.reconcile(run_id, ExecutionMode.PAPER, db, broker)
    assert result.status == ReconciliationStatus.MISMATCHED
    assert any(i.issue_type == ReconciliationIssueType.POSITION_MISSING_BROKER for i in result.issues)


def test_position_reconciliation_unexpected_broker_position(setup_db_and_broker):
    db, broker, run_id = setup_db_and_broker
    # Internal has no holdings, broker has SPY 50 shares
    broker._holdings = {"SPY": Holding("SPY", 50.0, 400.0, 400.0, 20000.0)}

    result = ReconciliationEngine.reconcile(run_id, ExecutionMode.PAPER, db, broker)
    assert result.status == ReconciliationStatus.MISMATCHED
    assert any(i.issue_type == ReconciliationIssueType.POSITION_MISSING_INTERNAL for i in result.issues)


def test_position_reconciliation_quantity_mismatch(setup_db_and_broker):
    db, broker, run_id = setup_db_and_broker
    holding_repo = HoldingRepository(db)

    # Internal has 100 shares, broker has 95 shares
    holding_repo.save_holdings({"SPY": Holding("SPY", 100.0, 400.0, 400.0, 40000.0)})
    broker._holdings = {"SPY": Holding("SPY", 95.0, 400.0, 400.0, 38000.0)}

    result = ReconciliationEngine.reconcile(run_id, ExecutionMode.PAPER, db, broker)
    assert result.status == ReconciliationStatus.MISMATCHED
    issue = next(i for i in result.issues if i.issue_type == ReconciliationIssueType.POSITION_QUANTITY_MISMATCH)
    assert issue.discrepancy == pytest.approx(5.0, abs=1e-4)


# --------------------------------------------------- 2. Order Matching
def test_order_reconciliation_status_mismatch(setup_db_and_broker):
    db, broker, run_id = setup_db_and_broker
    order_repo = OrderRepository(db)

    order_int = Order("ord_01", run_id, "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 10.0, status=OrderStatus.SUBMITTED)
    order_repo.save_order(order_int, ExecutionMode.PAPER)

    # Broker has order marked as FILLED
    order_brk = Order("ord_01", run_id, "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 10.0, status=OrderStatus.FILLED)
    broker._orders["ord_01"] = order_brk

    result = ReconciliationEngine.reconcile(run_id, ExecutionMode.PAPER, db, broker)
    assert result.status == ReconciliationStatus.MISMATCHED
    assert any(i.issue_type == ReconciliationIssueType.ORDER_STATUS_MISMATCH for i in result.issues)


# ---------------------------------------------------- 3. Fill Matching
def test_fill_reconciliation_missing_internal_fill(setup_db_and_broker):
    db, broker, run_id = setup_db_and_broker
    order_repo = OrderRepository(db)

    order = Order("ord_01", run_id, "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 10.0, status=OrderStatus.SUBMITTED)
    order_repo.save_order(order, ExecutionMode.PAPER)
    broker._orders["ord_01"] = order

    # Broker has executed fill, but SQLite has not recorded it yet
    now = datetime.now(timezone.utc)
    fill = Fill("fill_01", "ord_01", "SPY", OrderSide.BUY, 10.0, 400.0, 1.0, now)
    broker._fills["fill_01"] = fill

    result = ReconciliationEngine.reconcile(run_id, ExecutionMode.PAPER, db, broker)
    assert result.status == ReconciliationStatus.MISMATCHED
    assert any(i.issue_type == ReconciliationIssueType.FILL_MISSING_INTERNAL for i in result.issues)


# ---------------------------------------------- 4. Cash / NAV Matching
def test_cash_and_nav_mismatch(setup_db_and_broker):
    db, broker, run_id = setup_db_and_broker
    snap_repo = SnapshotRepository(db)

    now = datetime.now(timezone.utc)
    # Internal: cash $100,000, NAV $100,000
    state = PortfolioState(now, cash=100000.0, holdings={}, nav=100000.0, realized_weights={})
    snap_repo.save_snapshot("snap_01", run_id, state, ExecutionMode.PAPER, "macro_v1")

    # Broker: cash $95,000 (diff $5,000)
    broker.cash = 95000.0

    result = ReconciliationEngine.reconcile(run_id, ExecutionMode.PAPER, db, broker)
    assert result.status == ReconciliationStatus.MISMATCHED
    assert any(i.issue_type == ReconciliationIssueType.CASH_MISMATCH for i in result.issues)


# -------------------------------- 5. Reconciliation Result Persistence
def test_reconciliation_result_persistence_and_retrieval(setup_db_and_broker):
    db, broker, run_id = setup_db_and_broker
    holding_repo = HoldingRepository(db)

    # Create mismatch
    holding_repo.save_holdings({"SPY": Holding("SPY", 100.0, 400.0, 400.0, 40000.0)})
    broker._holdings = {"SPY": Holding("SPY", 90.0, 400.0, 400.0, 36000.0)}

    result = ReconciliationEngine.reconcile(run_id, ExecutionMode.PAPER, db, broker, reconciliation_id="rec_save_01")
    assert result.status == ReconciliationStatus.MISMATCHED

    rec_repo = ReconciliationRepository(db)
    rec_repo.save_reconciliation_result(result)

    loaded = rec_repo.get_reconciliation_result("rec_save_01")
    assert loaded is not None
    assert loaded.reconciliation_id == "rec_save_01"
    assert loaded.status == ReconciliationStatus.MISMATCHED
    assert len(loaded.issues) >= 1
    assert loaded.issues[0].issue_type == ReconciliationIssueType.POSITION_QUANTITY_MISMATCH


# ------------------------------------------------ 6. P5 Cases A through K
def test_case_a_perfect_match(setup_db_and_broker):
    """CASE A: Perfectly matching internal/external state -> PASS."""
    db, broker, run_id = setup_db_and_broker
    h_spy = Holding("SPY", 100.0, 400.0, 400.0, 40000.0)
    HoldingRepository(db).save_holdings({"SPY": h_spy})
    SnapshotRepository(db).save_snapshot(
        "snap_a", run_id, PortfolioState(datetime.now(timezone.utc), 60000.0, {"SPY": h_spy}, 100000.0, {"SPY": 0.40}),
        ExecutionMode.PAPER, "macro_v1"
    )
    broker.cash = 60000.0
    broker._holdings = {"SPY": h_spy}

    result = ReconciliationEngine.reconcile(run_id, ExecutionMode.PAPER, db, broker, ReconciliationConfig(position_qty_tolerance=0.001))
    assert result.passed is True
    assert result.status == ReconciliationStatus.MATCHED


def test_case_b_share_diff_within_tolerance(setup_db_and_broker):
    """CASE B: Internal shares differ by 0.0005 -> PASS within tolerance (<= 0.001)."""
    db, broker, run_id = setup_db_and_broker
    h_int = Holding("SPY", 100.0, 400.0, 400.0, 40000.0)
    HoldingRepository(db).save_holdings({"SPY": h_int})
    SnapshotRepository(db).save_snapshot(
        "snap_b", run_id, PortfolioState(datetime.now(timezone.utc), 60000.0, {"SPY": h_int}, 100000.0, {"SPY": 0.40}),
        ExecutionMode.PAPER, "macro_v1"
    )
    # Broker has 100.0005 shares (diff = 0.0005 <= 0.001)
    broker.cash = 60000.0
    broker._holdings = {"SPY": Holding("SPY", 100.0005, 400.0, 400.0, 40000.20)}

    result = ReconciliationEngine.reconcile(run_id, ExecutionMode.PAPER, db, broker, ReconciliationConfig(position_qty_tolerance=0.001, nav_tolerance=1.0))
    assert result.passed is True


def test_case_c_share_diff_exceeds_tolerance(setup_db_and_broker):
    """CASE C: Internal shares differ by 0.002 -> FAIL (> 0.001)."""
    db, broker, run_id = setup_db_and_broker
    h_int = Holding("SPY", 100.0, 400.0, 400.0, 40000.0)
    HoldingRepository(db).save_holdings({"SPY": h_int})
    SnapshotRepository(db).save_snapshot(
        "snap_c", run_id, PortfolioState(datetime.now(timezone.utc), 60000.0, {"SPY": h_int}, 100000.0, {"SPY": 0.40}),
        ExecutionMode.PAPER, "macro_v1"
    )
    # Broker has 100.002 shares (diff = 0.002 > 0.001)
    broker.cash = 60000.0
    broker._holdings = {"SPY": Holding("SPY", 100.002, 400.0, 400.0, 40000.80)}

    result = ReconciliationEngine.reconcile(run_id, ExecutionMode.PAPER, db, broker, ReconciliationConfig(position_qty_tolerance=0.001))
    assert result.passed is False
    assert any(i.issue_type == ReconciliationIssueType.POSITION_QUANTITY_MISMATCH for i in result.issues)


def test_case_d_and_e_cash_mismatch_tolerance(setup_db_and_broker):
    """CASE D & E: Cash mismatch within tolerance ($0.005) passes; outside ($0.05) fails."""
    db, broker, run_id = setup_db_and_broker
    snap_repo = SnapshotRepository(db)
    snap_repo.save_snapshot(
        "snap_d", run_id, PortfolioState(datetime.now(timezone.utc), 100000.0, {}, 100000.0, {}),
        ExecutionMode.PAPER, "macro_v1"
    )

    # CASE D: $0.005 difference (tolerance $0.01) -> PASS
    broker.cash = 100000.005
    res_d = ReconciliationEngine.reconcile(run_id, ExecutionMode.PAPER, db, broker, ReconciliationConfig(cash_tolerance=0.01))
    assert res_d.passed is True

    # CASE E: $0.05 difference (tolerance $0.01) -> FAIL
    broker.cash = 100000.05
    res_e = ReconciliationEngine.reconcile(run_id, ExecutionMode.PAPER, db, broker, ReconciliationConfig(cash_tolerance=0.01))
    assert res_e.passed is False
    assert any(i.issue_type == ReconciliationIssueType.CASH_MISMATCH for i in res_e.issues)


def test_case_g_cumulative_fills_exceed_order_quantity(setup_db_and_broker):
    """CASE G: Cumulative fills exceed order quantity -> FAIL."""
    db, broker, run_id = setup_db_and_broker
    order_repo = OrderRepository(db)
    order = Order("ord_g", run_id, "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 10.0, status=OrderStatus.FILLED)
    order_repo.save_order(order, ExecutionMode.PAPER)
    broker._orders["ord_g"] = order

    # 2 fills of 6.0 shares = 12.0 shares total (> 10.0 order quantity)
    now = datetime.now(timezone.utc)
    broker._fills["fill_g1"] = Fill("fill_g1", "ord_g", "SPY", OrderSide.BUY, 6.0, 400.0, 1.0, now)
    broker._fills["fill_g2"] = Fill("fill_g2", "ord_g", "SPY", OrderSide.BUY, 6.0, 400.0, 1.0, now)

    result = ReconciliationEngine.reconcile(run_id, ExecutionMode.PAPER, db, broker)
    assert result.passed is False
    assert any(i.issue_type == ReconciliationIssueType.FILL_OVERFILL for i in result.issues)


def test_case_h_unknown_broker_order_state(setup_db_and_broker):
    """CASE H: Broker reports an unknown active order state -> FAIL."""
    db, broker, run_id = setup_db_and_broker
    order_repo = OrderRepository(db)
    order = Order("ord_h", run_id, "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 10.0, status=OrderStatus.SUBMITTED)
    order_repo.save_order(order, ExecutionMode.PAPER)

    # Broker has unrecognized order status
    broker._orders["ord_h"] = Order("ord_h", run_id, "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 10.0, status="UNKNOWN_BROKER_STATUS")  # type: ignore

    result = ReconciliationEngine.reconcile(run_id, ExecutionMode.PAPER, db, broker)
    assert result.passed is False
    assert any(i.issue_type == ReconciliationIssueType.ORDER_UNKNOWN_STATE for i in result.issues)
