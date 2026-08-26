"""Comprehensive unit and integration test suite for Controlled Live Deployment with Mandatory Human Approval (P8)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from quant.broker.ibkr import IBKRBrokerAdapter, MockIBKRClient
from quant.core.enums import ExecutionMode, OrderSide, OrderStatus, OrderType
from quant.core.exceptions import ModeViolationError, OMSError
from quant.core.interfaces import Holding, Order, OrderBatch, RiskDecision, TargetPortfolio
from quant.oms.approval import ApprovalToken, AutoApproveGate, ManualApprovalGate
from quant.oms.preview import OrderPreviewBuilder
from quant.oms.revalidation import PreSubmissionValidator
from quant.persistence.database import DatabaseManager
from quant.risk.engine import RiskEngine
from quant.runner.live_config import LiveExecutionConfig
from quant.runner.live_runner import LiveTradingRunner
from quant.runner.models import RunStatus
from quant.strategies.macro import SystematicMacroStrategy


@pytest.fixture
def test_env(tmp_path: Path):
    db_file = tmp_path / "test_p8_live.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    mock_client = MockIBKRClient(auto_fill_on_submit=True)
    adapter = IBKRBrokerAdapter(client=mock_client)
    strategy = SystematicMacroStrategy(rebalance_cadence_days=21)
    df = pd.read_csv("tests/fixtures/synthetic_macro_12etf.csv", index_col=0, parse_dates=True)

    return db, mock_client, adapter, strategy, df


# ------------------------------------------------ 1. Environment Separation & Safety Locks
def test_live_config_environment_separation():
    """Validates that environment must be unambiguously PAPER or LIVE."""
    # Valid PAPER
    cfg_paper = LiveExecutionConfig(broker_env="PAPER")
    cfg_paper.validate_safety_locks()

    # Valid LIVE with explicit unlock
    cfg_live = LiveExecutionConfig(broker_env="LIVE", live_execution_enabled=True, live_capital_limit=25_000.0)
    cfg_live.validate_safety_locks()

    # Invalid ambiguous environment
    with pytest.raises(ValueError) as exc:
        LiveExecutionConfig(broker_env="STAGING").validate_safety_locks()
    assert "Ambiguous or invalid BROKER_ENV" in str(exc.value)

    # LIVE without live_execution_enabled=True fails closed
    with pytest.raises(ModeViolationError) as exc:
        LiveExecutionConfig(broker_env="LIVE", live_execution_enabled=False).validate_safety_locks()
    assert "requires LIVE_EXECUTION_ENABLED=true" in str(exc.value)


def test_auto_approve_gate_forbidden_in_live_mode():
    """AutoApproveGate strictly raises ModeViolationError if execution_mode == LIVE."""
    gate = AutoApproveGate()
    now = datetime.now(timezone.utc)
    order = Order("ord_1", "run_1", "strat_1", "SPY", OrderSide.BUY, OrderType.MARKET, 10.0, execution_mode=ExecutionMode.LIVE)
    batch = OrderBatch("batch_1", "tp_1", "strat_1", [order], ExecutionMode.LIVE, now)

    with pytest.raises(ModeViolationError) as exc:
        gate.approve_batch(batch)
    assert "AutoApproveGate is strictly prohibited in LIVE mode" in str(exc.value)


# ------------------------------------------------ 2. Mandatory Human Approval Gate
def test_manual_approval_grant_and_verify():
    """ApprovalToken is issued, validated, and authorizes batch execution."""
    gate = ManualApprovalGate(default_ttl_minutes=15.0)
    now = datetime.now(timezone.utc)
    order = Order("ord_1", "run_1", "strat_1", "SPY", OrderSide.BUY, OrderType.MARKET, 10.0)
    batch = OrderBatch("batch_p8_01", "tp_p8_01", "strat_1", [order], ExecutionMode.PAPER, now)

    # Missing token -> OMSError
    with pytest.raises(OMSError) as exc:
        gate.approve_batch(batch)
    assert "lacks human approval token" in str(exc.value)

    # Grant valid human approval
    token = gate.grant_approval("batch_p8_01", "dec_01", "tp_p8_01", "run_1", approved_by="senior_trader")
    assert token.is_valid() is True

    # Approve batch succeeds
    approved_batch = gate.approve_batch(batch, token=token)
    assert approved_batch.orders[0].status == OrderStatus.APPROVED


def test_manual_approval_expired_token_rejected():
    """Expired ApprovalToken is rejected and cannot authorize orders."""
    gate = ManualApprovalGate()
    now = datetime.now(timezone.utc)
    order = Order("ord_1", "run_1", "strat_1", "SPY", OrderSide.BUY, OrderType.MARKET, 10.0)
    batch = OrderBatch("batch_p8_exp", "tp_p8_exp", "strat_1", [order], ExecutionMode.PAPER, now)

    # Create expired token
    token = gate.grant_approval("batch_p8_exp", "dec_01", "tp_p8_exp", "run_1", ttl_minutes=-5.0)
    assert token.is_valid() is False

    with pytest.raises(OMSError) as exc:
        gate.approve_batch(batch, token=token)
    assert "is not valid (EXPIRED)" in str(exc.value)


def test_manual_approval_batch_mismatch_rejected():
    """ApprovalToken for Batch A cannot authorize Batch B."""
    gate = ManualApprovalGate()
    now = datetime.now(timezone.utc)
    order = Order("ord_1", "run_1", "strat_1", "SPY", OrderSide.BUY, OrderType.MARKET, 10.0)
    batch_b = OrderBatch("batch_B", "tp_B", "strat_1", [order], ExecutionMode.PAPER, now)

    # Token issued for batch_A
    token_a = gate.grant_approval("batch_A", "dec_01", "tp_A", "run_1")

    with pytest.raises(OMSError) as exc:
        gate.approve_batch(batch_b, token=token_a)
    assert "does not match submitted batch ID" in str(exc.value)


# ------------------------------------------------ 3. Order Preview Formatting
def test_order_preview_builder_and_text_formatting():
    """Verifies that OrderPreview generates complete financial projections."""
    now = datetime.now(timezone.utc)
    order1 = Order("ord_1", "run_1", "strat_1", "SPY", OrderSide.BUY, OrderType.MARKET, 50.0)
    order2 = Order("ord_2", "run_1", "strat_1", "TLT", OrderSide.SELL, OrderType.MARKET, 30.0)
    batch = OrderBatch("batch_prev", "tp_prev", "strat_1", [order1, order2], ExecutionMode.PAPER, now, metadata={"run_id": "run_1", "risk_decision_id": "dec_prev"})

    tp = TargetPortfolio(now, "strat_1", {"SPY": 0.20, "TLT": -0.10}, 21)
    risk_dec = RiskDecision(
        decision_id="dec_prev", portfolio_id="tp_prev", timestamp=now, approved=True,
        violations=[], metrics={"gross_exposure": 0.30, "net_exposure": 0.10}
    )

    preview = OrderPreviewBuilder.build(
        order_batch=batch,
        target_portfolio=tp,
        risk_decision=risk_dec,
        current_holdings={"SPY": Holding("SPY", 0.0, 400.0, 400.0, 0.0), "TLT": Holding("TLT", 50.0, 100.0, 100.0, 5000.0)},
        current_prices={"SPY": 400.0, "TLT": 100.0},
        cash=50_000.0,
    )

    assert len(preview.items) == 2
    assert preview.gross_exposure == pytest.approx(0.30)
    assert preview.net_exposure == pytest.approx(0.10)
    assert preview.current_cash == 50_000.0
    text_report = preview.to_text_preview()
    assert "ORDER BATCH PREVIEW FOR HUMAN APPROVAL" in text_report
    assert "SPY" in text_report
    assert "TLT" in text_report


# ------------------------------------------------ 4. Pre-Submission Revalidation Gate
def test_pre_submission_validator_catches_emergency_stop(test_env):
    """Emergency Stop blocks pre-submission revalidation fail-closed."""
    db, mock_client, adapter, strategy, df = test_env
    now = datetime.now(timezone.utc)
    order = Order("ord_1", "run_1", "strat_1", "SPY", OrderSide.BUY, OrderType.MARKET, 10.0)
    batch = OrderBatch("batch_1", "tp_1", "strat_1", [order], ExecutionMode.PAPER, now)
    tp = TargetPortfolio(now, "strat_1", {"SPY": 0.10}, 21)
    token = ApprovalToken("t1", "batch_1", "d1", "tp_1", "run_1", "operator", now, now + timedelta(minutes=15))

    res = PreSubmissionValidator.validate(
        order_batch=batch,
        target_portfolio=tp,
        broker=adapter,
        db_manager=db,
        approval_token=token,
        risk_engine=RiskEngine(),
        current_prices={"SPY": 400.0},
        emergency_stop_active=True,
    )
    assert res.passed is False
    assert any("EMERGENCY STOP" in e for e in res.errors)


def test_pre_submission_validator_catches_whitelist_violation(test_env):
    """Trading symbol outside approved whitelist is blocked fail-closed."""
    db, mock_client, adapter, strategy, df = test_env
    now = datetime.now(timezone.utc)
    order = Order("ord_unapproved", "run_1", "strat_1", "MEME_COIN", OrderSide.BUY, OrderType.MARKET, 10.0)
    batch = OrderBatch("batch_w", "tp_w", "strat_1", [order], ExecutionMode.PAPER, now)
    tp = TargetPortfolio(now, "strat_1", {"MEME_COIN": 0.10}, 21)
    token = ApprovalToken("t1", "batch_w", "d1", "tp_w", "run_1", "operator", now, now + timedelta(minutes=15))

    res = PreSubmissionValidator.validate(
        order_batch=batch,
        target_portfolio=tp,
        broker=adapter,
        db_manager=db,
        approval_token=token,
        risk_engine=RiskEngine(),
        current_prices={"MEME_COIN": 100.0},
        instrument_whitelist=["SPY", "TLT"],
    )
    assert res.passed is False
    assert any("outside the approved whitelist" in e for e in res.errors)


def test_pre_submission_validator_catches_capital_limit_excess(test_env):
    """Notional exceeding LIVE_CAPITAL_LIMIT is blocked fail-closed."""
    db, mock_client, adapter, strategy, df = test_env
    now = datetime.now(timezone.utc)
    order = Order("ord_large", "run_1", "strat_1", "SPY", OrderSide.BUY, OrderType.MARKET, 100.0)  # $40,000 notional
    batch = OrderBatch("batch_c", "tp_c", "strat_1", [order], ExecutionMode.LIVE, now)
    tp = TargetPortfolio(now, "strat_1", {"SPY": 0.40}, 21)
    token = ApprovalToken("t1", "batch_c", "d1", "tp_c", "run_1", "operator", now, now + timedelta(minutes=15))

    res = PreSubmissionValidator.validate(
        order_batch=batch,
        target_portfolio=tp,
        broker=adapter,
        db_manager=db,
        approval_token=token,
        risk_engine=RiskEngine(),
        current_prices={"SPY": 400.0},
        live_capital_limit=25_000.0,
        execution_mode=ExecutionMode.LIVE,
    )
    assert res.passed is False
    assert any("exceeds live capital limit" in e for e in res.errors)


# ------------------------------------------------ 5. Full End-to-End Live Runner Cycle
def test_live_trading_runner_full_operational_cycle(test_env):
    """Executes the complete 15-step daily operating procedure with human-in-the-loop approval."""
    db, mock_client, adapter, strategy, df = test_env
    window_df = df.iloc[:800]
    as_of_date = window_df.index[-1]
    run_id = "p8_live_op_run_01"

    live_cfg = LiveExecutionConfig(
        broker_env="PAPER",  # Paper-account validation mode
        live_execution_enabled=False,
        live_capital_limit=50_000.0,
    )
    approval_gate = ManualApprovalGate()
    runner = LiveTradingRunner(
        db_manager=db,
        broker=adapter,
        strategy=strategy,
        config=live_cfg,
        approval_gate=approval_gate,
    )

    # Steps 1-9: Prepare Order Preview for human review
    order_batch, target_portfolio, risk_decision, preview, current_prices = runner.prepare_order_preview(
        run_id=run_id,
        as_of_date=as_of_date,
        market_data=window_df,
        is_rebalance_day=True,
    )
    assert len(order_batch.orders) == 6
    assert preview.risk_approved is True

    # Human Review & Explicit Approval Grant
    token = approval_gate.grant_approval(
        order_batch_id=order_batch.batch_id,
        risk_decision_id=risk_decision.decision_id,
        target_portfolio_id=target_portfolio.metadata.get("target_portfolio_id", order_batch.target_portfolio_id),
        run_id=run_id,
        approved_by="lead_portfolio_manager",
    )
    assert token.is_valid() is True

    # Steps 10-15: Execute Approved Batch
    record, report = runner.execute_approved_batch(
        run_id=run_id,
        order_batch=order_batch,
        target_portfolio=target_portfolio,
        risk_decision=risk_decision,
        approval_token=token,
        current_prices=current_prices,
    )

    if record.status != RunStatus.COMPLETED:
        print(f"DEBUG ERROR MESSAGE: {record.error_message}")

    assert record.status == RunStatus.COMPLETED
    assert record.pre_reconciliation_status == "MATCHED"
    assert record.post_reconciliation_status == "MATCHED"
    assert record.orders_count == 6
    assert record.fills_count == 6
    assert report.final_run_status == RunStatus.COMPLETED
