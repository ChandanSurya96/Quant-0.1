"""Comprehensive audit test suite for P5.1 Risk Policy, Invariants, and Execution Gate."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from quant.broker.paper_broker import PaperBroker
from quant.core.enums import AssetClass, ExecutionMode
from quant.core.exceptions import ReconciliationError, RiskViolationError
from quant.core.interfaces import Holding, Instrument, PortfolioState, TargetPortfolio
from quant.oms.engine import OrderManagementSystem
from quant.oms.reconciler import ExecutionReconciliationGate, PortfolioReconciler
from quant.persistence.database import DatabaseManager
from quant.persistence.repositories import HoldingRepository, InstrumentRepository, RunRepository, SnapshotRepository
from quant.reconciliation.types import (
    ReconciliationIssue,
    ReconciliationIssueType,
    ReconciliationResult,
    ReconciliationStatus,
)
from quant.risk.config import RiskConfig
from quant.risk.engine import RiskEngine


@pytest.fixture
def base_state_100k() -> PortfolioState:
    now = datetime.now(timezone.utc)
    h_spy = Holding("SPY", 100.0, 400.0, 400.0, 40000.0)
    h_tlt = Holding("TLT", 200.0, 100.0, 100.0, 20000.0)
    return PortfolioState(
        timestamp=now,
        cash=40000.0,  # 40% cash
        holdings={"SPY": h_spy, "TLT": h_tlt},
        nav=100000.0,
        realized_weights={"SPY": 0.40, "TLT": 0.20},
    )


# ------------------------------------------------ 1. Gross Exposure Audit
def test_gross_exposure_policy_is_configurable(base_state_100k: PortfolioState):
    """Gross exposure is a configurable policy parameter, not a hardcoded strategy calculation."""
    now = datetime.now(timezone.utc)
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.40, "TLT": -0.40, "GLD": 0.40}, 21)  # Gross = 1.20

    # Policy A: max gross = 1.0 -> REJECTED
    engine_strict = RiskEngine(RiskConfig(max_gross_exposure=1.0, max_single_position_weight=0.50))
    dec_strict = engine_strict.evaluate(tp, base_state_100k)
    assert dec_strict.approved is False

    # Policy B: max gross = 1.50 -> APPROVED
    engine_relaxed = RiskEngine(RiskConfig(max_gross_exposure=1.50, max_single_position_weight=0.50, max_long_exposure=1.0))
    dec_relaxed = engine_relaxed.evaluate(tp, base_state_100k)
    assert dec_relaxed.approved is True
    assert dec_relaxed.metrics["gross_exposure"] == pytest.approx(1.20, abs=1e-4)


def test_scaling_is_deterministic_and_preserves_original_target(base_state_100k: PortfolioState):
    """Proportional scaling deterministically adjusts weights while preserving original TargetPortfolio."""
    engine = RiskEngine(RiskConfig(max_gross_exposure=1.0, max_single_position_weight=0.50, scale_gross_leverage=True))
    now = datetime.now(timezone.utc)
    original_weights = {"SPY": 0.80, "TLT": -0.80}  # Gross = 1.60
    tp = TargetPortfolio(now, "macro_v1", original_weights, 21)

    dec = engine.evaluate(tp, base_state_100k)
    assert dec.approved is True
    assert dec.metadata["decision_status"] == "approved_scaled"
    assert dec.metadata["was_scaled"] is True

    # Original target portfolio remains strictly unaltered
    assert tp.target_weights == original_weights
    assert tp.target_weights["SPY"] == 0.80

    # Adjusted weights scaled by 1.0 / 1.60 = 0.625
    assert dec.adjusted_weights["SPY"] == pytest.approx(0.50, abs=1e-4)
    assert dec.adjusted_weights["TLT"] == pytest.approx(-0.50, abs=1e-4)


# ------------------------------------------------ 2. Short Exposure Audit
def test_short_exposure_invariants(base_state_100k: PortfolioState):
    """Negative weights remain strictly negative and are never converted to cash, longs, or inverse ETFs."""
    engine = RiskEngine(RiskConfig(max_single_position_weight=0.25))
    now = datetime.now(timezone.utc)
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.20, "TLT": -0.20}, 21)

    # 1. Borrow Available -> Approved with negative weight preserved
    dec = engine.evaluate(tp, base_state_100k, available_borrows={"TLT": True, "SPY": True})
    assert dec.approved is True
    assert dec.adjusted_weights["TLT"] == -0.20

    # 2. Borrow Unavailable -> Rejected (Zero silent conversion)
    dec_no_borrow = engine.evaluate(tp, base_state_100k, available_borrows={"TLT": False, "SPY": True})
    assert dec_no_borrow.approved is False
    assert dec_no_borrow.adjusted_weights == {}
    assert any("borrow unavailable" in v for v in dec_no_borrow.violations)


def test_mixed_multiple_short_positions(base_state_100k: PortfolioState):
    """Multiple short positions with mixed borrow availability are evaluated deterministically."""
    engine = RiskEngine(RiskConfig(max_single_position_weight=0.25))
    now = datetime.now(timezone.utc)
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.20, "TLT": -0.15, "IEF": -0.10}, 21)

    # TLT available, IEF unavailable -> REJECTED with specific violation on IEF
    dec = engine.evaluate(tp, base_state_100k, available_borrows={"TLT": True, "IEF": False, "SPY": True})
    assert dec.approved is False
    assert any("Short position in IEF" in v for v in dec.violations)
    assert not any("Short position in TLT" in v for v in dec.violations)


# ------------------------------------------------ 3. Drawdown Audit
@pytest.mark.parametrize(
    "peak_nav,current_nav,expected_approved",
    [
        (100000.0, 85010.0, True),   # Drawdown = -14.99% -> PASS
        (100000.0, 85000.0, True),   # Drawdown = -15.00% -> PASS (Exact boundary)
        (100000.0, 84990.0, False),  # Drawdown = -15.01% -> REJECT (Breached)
    ],
)
def test_drawdown_exact_boundary(peak_nav: float, current_nav: float, expected_approved: bool):
    """Exact boundary evaluation of the -15.0% drawdown circuit breaker."""
    engine = RiskEngine(RiskConfig(max_drawdown_pct=0.15, max_single_position_weight=0.25))
    now = datetime.now(timezone.utc)
    state = PortfolioState(now, cash=current_nav, holdings={}, nav=current_nav, realized_weights={})
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.20}, 21)

    dec = engine.evaluate(tp, state, peak_nav=peak_nav)
    assert dec.approved == expected_approved
    if not expected_approved:
        assert any("Portfolio drawdown" in v for v in dec.violations)


def test_drawdown_breach_permits_risk_reduction_without_auto_liquidation():
    """Breached drawdown freezes risk expansion but permits risk reduction without auto-liquidation."""
    engine = RiskEngine(RiskConfig(max_drawdown_pct=0.15, max_single_position_weight=0.50, allow_risk_reduction=True))
    now = datetime.now(timezone.utc)

    # NAV = 80k, Peak = 100k -> Drawdown = -20% (breached)
    # Current holding: SPY = 40k (0.50 weight)
    state = PortfolioState(
        timestamp=now,
        cash=40000.0,
        holdings={"SPY": Holding("SPY", 100.0, 400.0, 400.0, 40000.0)},
        nav=80000.0,
        realized_weights={"SPY": 0.50},
    )

    # Attempt risk reduction: SPY reduced to 0.25 (gross 0.25 <= current gross 0.50) -> APPROVED
    tp_reduce = TargetPortfolio(now, "macro_v1", {"SPY": 0.25}, 21)
    dec_reduce = engine.evaluate(tp_reduce, state, peak_nav=100000.0)
    assert dec_reduce.approved is True

    # Attempt risk expansion: SPY 0.50 + TLT 0.20 (gross 0.70 > current gross 0.50) -> REJECTED
    tp_expand = TargetPortfolio(now, "macro_v1", {"SPY": 0.50, "TLT": 0.20}, 21)
    dec_expand = engine.evaluate(tp_expand, state, peak_nav=100000.0)
    assert dec_expand.approved is False
    assert any("breached circuit breaker" in v for v in dec_expand.violations)


# ------------------------------------------------ 4. Concentration Audit
@pytest.mark.parametrize(
    "weight,expected_approved",
    [
        (0.2499, True),   # Long +24.99% -> PASS
        (0.2500, True),   # Long +25.00% -> PASS (Exact boundary)
        (0.2501, False),  # Long +25.01% -> REJECT
        (-0.2499, True),  # Short -24.99% -> PASS
        (-0.2500, True),  # Short -25.00% -> PASS (Exact boundary)
        (-0.2501, False), # Short -25.01% -> REJECT
    ],
)
def test_concentration_exact_boundaries(base_state_100k: PortfolioState, weight: float, expected_approved: bool):
    """Single position concentration |w_i| <= 0.25 boundary test."""
    engine = RiskEngine(RiskConfig(max_single_position_weight=0.25))
    now = datetime.now(timezone.utc)
    tp = TargetPortfolio(now, "macro_v1", {"SPY": weight}, 21)

    dec = engine.evaluate(tp, base_state_100k)
    assert dec.approved == expected_approved
    if not expected_approved:
        assert any("Single position concentration" in v for v in dec.violations)
        assert dec.adjusted_weights == {}  # Zero silent clipping


# ------------------------------------------------ 5. Cash Buffer Audit
def test_cash_buffer_evaluated_post_trade_with_friction(base_state_100k: PortfolioState):
    """Cash buffer evaluates projected cash taking into account rebalance trade costs."""
    engine = RiskEngine(RiskConfig(min_cash_buffer_pct=0.02, max_single_position_weight=0.50))
    now = datetime.now(timezone.utc)

    # Current state: NAV = $100k, Cash = $40k. Target requires buying $50k SPY + $40k TLT = $90k buys.
    # Net cash flow = -$90k. Projected cash = $40k - $90k = -$50k (< 2%) -> REJECTED
    tp_overbuy = TargetPortfolio(now, "macro_v1", {"SPY": 0.50, "TLT": 0.40, "GLD": 0.10}, 21)
    prices = {"SPY": 400.0, "TLT": 100.0, "GLD": 180.0}
    dec = engine.evaluate(tp_overbuy, base_state_100k, current_prices=prices)
    assert dec.approved is False
    assert any("Projected cash buffer" in v for v in dec.violations)


# ------------------------------------------------ 6. Reconciliation Audit & Bypass Prevention
def test_reconciliation_failure_blocks_broker_submission(tmp_path):
    """An approved RiskDecision cannot result in broker execution if reconciliation fails."""
    db_file = tmp_path / "test_rec_bypass.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    run_id = "run_bypass_01"
    RunRepository(db).create_run(run_id, ExecutionMode.PAPER, "macro_v1")
    InstrumentRepository(db).save_instrument(Instrument("SPY", AssetClass.EQUITY))

    # Internal state: 100 SPY
    HoldingRepository(db).save_holdings({"SPY": Holding("SPY", 100.0, 400.0, 400.0, 40000.0)})
    SnapshotRepository(db).save_snapshot(
        "snap_bp", run_id, PortfolioState(datetime.now(timezone.utc), 60000.0, {"SPY": Holding("SPY", 100.0, 400.0, 400.0, 40000.0)}, 100000.0, {"SPY": 0.40}),
        ExecutionMode.PAPER, "macro_v1"
    )

    # Broker has corrupted position: 90 SPY (unexplained mismatch)
    broker = PaperBroker(initial_cash=60000.0)
    broker._holdings = {"SPY": Holding("SPY", 90.0, 400.0, 400.0, 36000.0)}

    # Step 1: Risk Engine Approves Target Portfolio
    engine = RiskEngine()
    tp = TargetPortfolio(datetime.now(timezone.utc), "macro_v1", {"SPY": 0.20}, 21)
    dec = engine.evaluate(tp, broker.get_account_state(), portfolio_id="tp_bp_01")
    assert dec.approved is True

    # Step 2: OMS Generates Order Batch
    order_batch = OrderManagementSystem.generate_order_batch(
        current_holdings=broker.get_positions(),
        target_portfolio=tp,
        current_prices={"SPY": 400.0},
        nav=100000.0,
        run_id=run_id,
        target_portfolio_id="tp_bp_01",
        risk_decision=dec,
        require_risk_approval=True,
    )
    assert len(order_batch.orders) >= 1

    # Step 3: Reconciliation Gate Check -> Reconciliation fails and blocks execution
    reconciler = PortfolioReconciler(db)
    rec_result = reconciler.reconcile(run_id, ExecutionMode.PAPER, broker)
    assert rec_result.passed is False

    with pytest.raises(ReconciliationError) as exc_info:
        ExecutionReconciliationGate.enforce_gate(rec_result)

    assert "Execution Halted: Reconciliation failed" in str(exc_info.value)


def test_reconciliation_unknown_status_fails_closed():
    """UNKNOWN reconciliation status is treated as an execution blocker (UNKNOWN != healthy)."""
    now = datetime.now(timezone.utc)
    unknown_result = ReconciliationResult(
        reconciliation_id="rec_unk",
        run_id="run_unk",
        timestamp=now,
        execution_mode=ExecutionMode.PAPER,
        status=ReconciliationStatus.UNKNOWN,
        issues=[ReconciliationIssue(issue_type=ReconciliationIssueType.ORDER_UNKNOWN_STATE, message="Broker unreachable")],
    )
    assert unknown_result.passed is False

    with pytest.raises(ReconciliationError):
        ExecutionReconciliationGate.enforce_gate(unknown_result)


# ------------------------------------------------ 7. Order / Risk / Portfolio Binding
def test_order_generation_fails_closed_on_portfolio_id_mismatch():
    """RiskDecision for portfolio A cannot authorize portfolio B."""
    now = datetime.now(timezone.utc)
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.20}, 21)
    state = PortfolioState(now, cash=100000.0, holdings={}, nav=100000.0, realized_weights={})

    engine = RiskEngine()
    dec_a = engine.evaluate(tp, state, portfolio_id="tp_AAA")

    # Present decision for tp_AAA to target portfolio tp_BBB -> MUST FAIL CLOSED
    with pytest.raises(RiskViolationError) as exc_info:
        OrderManagementSystem.generate_order_batch(
            current_holdings={},
            target_portfolio=tp,
            current_prices={"SPY": 400.0},
            nav=100000.0,
            run_id="run_mismatch",
            target_portfolio_id="tp_BBB",
            risk_decision=dec_a,
            require_risk_approval=True,
        )

    assert "RiskDecision portfolio_id mismatch" in str(exc_info.value)


def test_order_batch_contains_traceable_risk_binding():
    """OrderBatch metadata contains explicit risk_decision_id and run_id bindings."""
    now = datetime.now(timezone.utc)
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.20}, 21)
    state = PortfolioState(now, cash=100000.0, holdings={}, nav=100000.0, realized_weights={})

    engine = RiskEngine()
    dec = engine.evaluate(tp, state, portfolio_id="tp_bind_01", decision_id="dec_bind_01")

    batch = OrderManagementSystem.generate_order_batch(
        current_holdings={},
        target_portfolio=tp,
        current_prices={"SPY": 400.0},
        nav=100000.0,
        run_id="run_bind_01",
        target_portfolio_id="tp_bind_01",
        risk_decision=dec,
        require_risk_approval=True,
    )
    assert batch.metadata["risk_decision_id"] == "dec_bind_01"
    assert batch.metadata["run_id"] == "run_bind_01"
    assert batch.target_portfolio_id == "tp_bind_01"
    assert batch.strategy_id == "macro_v1"
