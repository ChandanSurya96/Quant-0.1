"""Integration tests proving RiskEngine authority over OMS order generation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from quant.core.enums import OrderSide
from quant.core.exceptions import RiskViolationError
from quant.core.interfaces import Holding, PortfolioState, RiskDecision, TargetPortfolio
from quant.oms.engine import OrderManagementSystem
from quant.risk.config import RiskConfig
from quant.risk.engine import RiskEngine


@pytest.fixture
def sample_portfolio_state() -> PortfolioState:
    now = datetime.now(timezone.utc)
    return PortfolioState(
        timestamp=now,
        cash=60000.0,
        holdings={"SPY": Holding("SPY", 100.0, 400.0, 400.0, 40000.0)},
        nav=100000.0,
        realized_weights={"SPY": 0.40},
    )


def test_approved_risk_decision_allows_oms_execution(sample_portfolio_state: PortfolioState):
    now = datetime.now(timezone.utc)
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.50}, 21)
    engine = RiskEngine(RiskConfig(max_gross_exposure=1.0, max_single_position_weight=0.60))

    dec = engine.evaluate(tp, sample_portfolio_state, portfolio_id="tp_app_01")
    assert dec.approved is True

    # OMS generates orders with approved RiskDecision
    batch = OrderManagementSystem.generate_order_batch(
        sample_portfolio_state.holdings,
        tp,
        {"SPY": 400.0},
        nav=100000.0,
        run_id="run_app_01",
        target_portfolio_id="tp_app_01",
        risk_decision=dec,
        require_risk_approval=True,
    )
    assert len(batch.orders) == 1
    assert batch.orders[0].side == OrderSide.BUY
    assert batch.orders[0].quantity == pytest.approx(25.0, abs=1e-4)


def test_rejected_risk_decision_blocks_oms_execution(sample_portfolio_state: PortfolioState):
    now = datetime.now(timezone.utc)
    # Gross exposure 1.50 > 1.0 limit
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.75, "TLT": 0.75}, 21)
    engine = RiskEngine(RiskConfig(max_gross_exposure=1.0))

    dec = engine.evaluate(tp, sample_portfolio_state, portfolio_id="tp_rej_01")
    assert dec.approved is False

    # OMS MUST raise RiskViolationError and reject order generation
    with pytest.raises(RiskViolationError, match="TargetPortfolio was rejected by RiskEngine"):
        OrderManagementSystem.generate_order_batch(
            sample_portfolio_state.holdings,
            tp,
            {"SPY": 400.0, "TLT": 100.0},
            nav=100000.0,
            run_id="run_rej_01",
            target_portfolio_id="tp_rej_01",
            risk_decision=dec,
            require_risk_approval=True,
        )


def test_missing_risk_decision_blocks_oms_execution_when_required(sample_portfolio_state: PortfolioState):
    now = datetime.now(timezone.utc)
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.50}, 21)

    with pytest.raises(RiskViolationError, match="Pre-trade risk decision missing"):
        OrderManagementSystem.generate_order_batch(
            sample_portfolio_state.holdings,
            tp,
            {"SPY": 400.0},
            nav=100000.0,
            run_id="run_miss_01",
            risk_decision=None,
            require_risk_approval=True,
        )


def test_wrong_portfolio_id_risk_decision_blocked(sample_portfolio_state: PortfolioState):
    now = datetime.now(timezone.utc)
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.50}, 21)
    # Authorized for tp_A, but presented for tp_B
    dec = RiskDecision(
        timestamp=now,
        approved=True,
        portfolio_id="tp_A",
        strategy_id="macro_v1",
    )

    with pytest.raises(RiskViolationError, match="RiskDecision portfolio_id mismatch"):
        OrderManagementSystem.generate_order_batch(
            sample_portfolio_state.holdings,
            tp,
            {"SPY": 400.0},
            nav=100000.0,
            run_id="run_mis_01",
            target_portfolio_id="tp_B",
            risk_decision=dec,
            require_risk_approval=True,
        )


def test_wrong_strategy_id_risk_decision_blocked(sample_portfolio_state: PortfolioState):
    now = datetime.now(timezone.utc)
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.50}, 21)
    # Authorized for 'other_strategy', presented for 'macro_v1'
    dec = RiskDecision(
        timestamp=now,
        approved=True,
        portfolio_id="tp_01",
        strategy_id="other_strategy",
    )

    with pytest.raises(RiskViolationError, match="RiskDecision strategy_id mismatch"):
        OrderManagementSystem.generate_order_batch(
            sample_portfolio_state.holdings,
            tp,
            {"SPY": 400.0},
            nav=100000.0,
            run_id="run_mis_02",
            target_portfolio_id="tp_01",
            risk_decision=dec,
            require_risk_approval=True,
        )
