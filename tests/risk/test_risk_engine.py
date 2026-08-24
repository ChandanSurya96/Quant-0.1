"""Unit tests for Pre-Trade Risk Engine and portfolio risk limits."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pytest

from quant.core.enums import ExecutionMode
from quant.core.interfaces import Holding, PortfolioState, TargetPortfolio
from quant.persistence.database import DatabaseManager
from quant.persistence.repositories import (
    RiskEvaluationRepository,
    RunRepository,
    TargetPortfolioRepository,
)
from quant.risk.config import RiskConfig
from quant.risk.engine import RiskEngine


@pytest.fixture
def base_portfolio_state() -> PortfolioState:
    now = datetime.now(timezone.utc)
    return PortfolioState(
        timestamp=now,
        cash=10000.0,  # 10% cash buffer
        holdings={"SPY": Holding("SPY", 100.0, 450.0, 450.0, 45000.0), "TLT": Holding("TLT", 500.0, 90.0, 90.0, 45000.0)},
        nav=100000.0,
        realized_weights={"SPY": 0.45, "TLT": 0.45},
    )


# ------------------------------------------------ 1. Exposure Limits
def test_risk_gross_exposure_approved_and_rejected(base_portfolio_state: PortfolioState):
    engine = RiskEngine(RiskConfig(max_gross_exposure=1.0, max_single_position_weight=0.50))
    now = datetime.now(timezone.utc)

    # Gross = 0.80 -> APPROVED
    tp_pass = TargetPortfolio(now, "macro_v1", {"SPY": 0.40, "TLT": -0.40}, 21)
    dec_pass = engine.evaluate(tp_pass, base_portfolio_state)
    assert dec_pass.approved is True
    assert dec_pass.metrics["gross_exposure"] == pytest.approx(0.80, abs=1e-4)

    # Gross = 1.30 -> REJECTED
    tp_fail = TargetPortfolio(now, "macro_v1", {"SPY": 0.70, "TLT": -0.60}, 21)
    dec_fail = engine.evaluate(tp_fail, base_portfolio_state)
    assert dec_fail.approved is False
    assert any("Gross exposure 1.3000 exceeds limit 1.0000" in v for v in dec_fail.violations)


def test_risk_net_exposure_limit(base_portfolio_state: PortfolioState):
    engine = RiskEngine(RiskConfig(max_net_exposure=0.50))
    now = datetime.now(timezone.utc)

    # Net = +0.70 -> REJECTED
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.70, "TLT": 0.0}, 21)
    dec = engine.evaluate(tp, base_portfolio_state)
    assert dec.approved is False
    assert any("Net exposure 0.7000 exceeds limit 0.5000" in v for v in dec.violations)


def test_risk_long_and_short_exposure_limits(base_portfolio_state: PortfolioState):
    engine = RiskEngine(RiskConfig(max_long_exposure=0.60, max_short_exposure=0.40))
    now = datetime.now(timezone.utc)

    # Long = 0.50, Short = 0.50 (Short exceeds 0.40) -> REJECTED
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.50, "TLT": -0.50}, 21)
    dec = engine.evaluate(tp, base_portfolio_state)
    assert dec.approved is False
    assert any("Short exposure 0.5000 exceeds limit 0.4000" in v for v in dec.violations)


# ----------------------------------------------- 2. Concentration Limits
def test_risk_concentration_single_position_limit(base_portfolio_state: PortfolioState):
    engine = RiskEngine(RiskConfig(max_single_position_weight=0.25))
    now = datetime.now(timezone.utc)

    # SPY = +0.35 (exceeds 0.25) -> REJECTED
    tp_long = TargetPortfolio(now, "macro_v1", {"SPY": 0.35, "TLT": 0.10}, 21)
    dec_long = engine.evaluate(tp_long, base_portfolio_state)
    assert dec_long.approved is False
    assert any("Single position concentration 0.3500 exceeds limit 0.2500" in v for v in dec_long.violations)

    # TLT = -0.30 (magnitude 0.30 exceeds 0.25) -> REJECTED
    tp_short = TargetPortfolio(now, "macro_v1", {"SPY": 0.10, "TLT": -0.30}, 21)
    dec_short = engine.evaluate(tp_short, base_portfolio_state)
    assert dec_short.approved is False
    assert any("Single position concentration 0.3000 exceeds limit 0.2500" in v for v in dec_short.violations)


# ------------------------------------------------- 3. Cash Buffer Limits
def test_risk_cash_buffer_limits():
    engine = RiskEngine(RiskConfig(min_cash_buffer_pct=0.05))  # Requires 5% cash
    now = datetime.now(timezone.utc)
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.20}, 21)

    # Cash = $1,000 / $100,000 NAV = 1% (< 5%) -> REJECTED
    state_low_cash = PortfolioState(
        timestamp=now, cash=1000.0, holdings={"SPY": Holding("SPY", 220.0, 450.0, 450.0, 99000.0)}, nav=100000.0, realized_weights={"SPY": 0.99}
    )
    dec = engine.evaluate(tp, state_low_cash)
    assert dec.approved is False
    assert any("Cash buffer 1.00% below minimum required 5.00%" in v for v in dec.violations)


# -------------------------------------------- 4. Drawdown Circuit Breaker
def test_risk_drawdown_kill_switch(base_portfolio_state: PortfolioState):
    engine = RiskEngine(RiskConfig(max_drawdown_pct=0.15))
    now = datetime.now(timezone.utc)
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.20}, 21)

    # Current NAV = $100k, Peak NAV = $110k (Drawdown = -9.09% <= 15%) -> APPROVED
    dec_pass = engine.evaluate(tp, base_portfolio_state, peak_nav=110000.0)
    assert dec_pass.approved is True

    # Current NAV = $100k, Peak NAV = $125k (Drawdown = -20.0% > 15%) -> REJECTED
    dec_fail = engine.evaluate(tp, base_portfolio_state, peak_nav=125000.0)
    assert dec_fail.approved is False
    assert any("Portfolio drawdown -20.00% breached kill-switch threshold -15.00%" in v for v in dec_fail.violations)


# -------------------------------------------- 5. Volatility Limits & Fail-Closed
def test_risk_volatility_limits_and_fail_closed(base_portfolio_state: PortfolioState):
    engine = RiskEngine(RiskConfig(max_volatility_annualized=0.25, min_vol_history_bars=20))
    now = datetime.now(timezone.utc)
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.20}, 21)

    # Case A: Insufficient History (< 20 bars) -> FAIL CLOSED (REJECTED)
    short_rets = np.random.normal(0, 0.01, 10)
    dec_short = engine.evaluate(tp, base_portfolio_state, historical_returns=short_rets)
    assert dec_short.approved is False
    assert any("Insufficient volatility history" in v for v in dec_short.violations)

    # Case B: High Volatility (annualized vol ~ 40% > 25%) -> REJECTED
    high_vol_rets = np.random.normal(0, 0.025, 60)  # 2.5% daily vol * sqrt(252) ~ 40%
    dec_high = engine.evaluate(tp, base_portfolio_state, historical_returns=high_vol_rets)
    assert dec_high.approved is False
    assert any("exceeds limit 25.00%" in v for v in dec_high.violations)


# --------------------------------------- 6. Structured Violation Reporting
def test_risk_structured_violations_reporting(base_portfolio_state: PortfolioState):
    engine = RiskEngine(RiskConfig(max_gross_exposure=1.0, max_single_position_weight=0.25))
    now = datetime.now(timezone.utc)

    # Both Gross (1.50) and Concentration (0.50) breached
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.50, "TLT": 0.50, "GLD": 0.50}, 21)
    dec = engine.evaluate(tp, base_portfolio_state)

    assert dec.approved is False
    assert len(dec.violations) >= 2
    assert any("Gross exposure" in v for v in dec.violations)
    assert any("Single position concentration" in v for v in dec.violations)


# ---------------------------------------- 7. Risk Decision Persistence
def test_risk_decision_persistence(tmp_path: Path, base_portfolio_state: PortfolioState):
    db_file = tmp_path / "test_risk_db.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    run_repo = RunRepository(db)
    run_repo.create_run("run_risk_01", ExecutionMode.PAPER, "macro_v1")
    tp_repo = TargetPortfolioRepository(db)
    tp = TargetPortfolio(datetime.now(timezone.utc), "macro_v1", {"SPY": 0.20}, 21)
    tp_repo.save_target_portfolio("tp_risk_01", tp, run_id="run_risk_01")

    engine = RiskEngine()
    dec = engine.evaluate(tp, base_portfolio_state, portfolio_id="tp_risk_01", decision_id="dec_001")

    risk_repo = RiskEvaluationRepository(db)
    risk_repo.save_risk_evaluation(dec)

    loaded = risk_repo.get_risk_evaluation("dec_001")
    assert loaded is not None
    assert loaded.decision_id == "dec_001"
    assert loaded.approved is True
    assert loaded.metrics["gross_exposure"] == pytest.approx(0.20, abs=1e-4)


# ------------------------------------------------ 8. P5 Specific Tests
def test_gross_leverage_exactly_one(base_portfolio_state: PortfolioState):
    """Gross leverage exactly 1.0 -> pass."""
    engine = RiskEngine(RiskConfig(max_gross_exposure=1.0, max_single_position_weight=0.25))
    now = datetime.now(timezone.utc)
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.25, "TLT": -0.25, "GLD": 0.25, "IEF": -0.25}, 21)
    dec = engine.evaluate(tp, base_portfolio_state)
    assert dec.approved is True
    assert dec.metrics["gross_exposure"] == pytest.approx(1.0, abs=1e-4)


def test_gross_leverage_deterministic_scaling(base_portfolio_state: PortfolioState):
    """Gross leverage > 1.0 -> deterministic proportional scaling."""
    engine = RiskEngine(RiskConfig(max_gross_exposure=1.0, max_single_position_weight=0.50, scale_gross_leverage=True))
    now = datetime.now(timezone.utc)
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.80, "TLT": -0.80}, 21)  # Gross = 1.60
    dec = engine.evaluate(tp, base_portfolio_state)
    assert dec.approved is True
    assert dec.metadata["was_scaled"] is True
    assert dec.metadata["decision_status"] == "approved_scaled"
    assert dec.adjusted_weights["SPY"] == pytest.approx(0.50, abs=1e-4)
    assert dec.adjusted_weights["TLT"] == pytest.approx(-0.50, abs=1e-4)
    assert sum(abs(w) for w in dec.adjusted_weights.values()) == pytest.approx(1.0, abs=1e-4)


def test_single_asset_concentration_boundary(base_portfolio_state: PortfolioState):
    """Single asset exactly 25% -> pass. Single asset > 25% -> rejected."""
    engine = RiskEngine(RiskConfig(max_single_position_weight=0.25))
    now = datetime.now(timezone.utc)
    
    tp_exact = TargetPortfolio(now, "macro_v1", {"SPY": 0.25}, 21)
    dec_exact = engine.evaluate(tp_exact, base_portfolio_state)
    assert dec_exact.approved is True

    tp_over = TargetPortfolio(now, "macro_v1", {"SPY": 0.2501}, 21)
    dec_over = engine.evaluate(tp_over, base_portfolio_state)
    assert dec_over.approved is False
    assert any("Single position concentration" in v for v in dec_over.violations)


def test_short_borrow_with_and_without_borrow(base_portfolio_state: PortfolioState):
    """Short with available borrow -> pass. Short without borrow -> reject."""
    engine = RiskEngine(RiskConfig(max_single_position_weight=0.25))
    now = datetime.now(timezone.utc)
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.20, "TLT": -0.20}, 21)

    # 1. Borrow available for TLT -> PASS
    dec_avail = engine.evaluate(tp, base_portfolio_state, available_borrows={"TLT": True, "SPY": True})
    assert dec_avail.approved is True

    # 2. Borrow unavailable for TLT -> REJECT (never converted to cash or long)
    dec_unavail = engine.evaluate(tp, base_portfolio_state, available_borrows={"TLT": False})
    assert dec_unavail.approved is False
    assert any("borrow unavailable" in v for v in dec_unavail.violations)
    assert dec_unavail.adjusted_weights == {}


def test_drawdown_circuit_breaker_permits_risk_reduction():
    """Drawdown worse than -15% blocks expansion but permits risk reduction."""
    engine = RiskEngine(RiskConfig(max_drawdown_pct=0.15, max_single_position_weight=0.50, allow_risk_reduction=True))
    now = datetime.now(timezone.utc)

    # Current state: NAV = 80k, Peak = 100k -> Drawdown = -20% (breaches -15%)
    # Current holding: SPY = 40k (0.50 weight)
    state = PortfolioState(
        timestamp=now,
        cash=40000.0,
        holdings={"SPY": Holding("SPY", 100.0, 400.0, 400.0, 40000.0)},
        nav=80000.0,
        realized_weights={"SPY": 0.50},
    )

    # Risk expansion: Target SPY 0.50 + TLT 0.30 (gross 0.80 > current 0.50) -> REJECTED
    tp_expand = TargetPortfolio(now, "macro_v1", {"SPY": 0.50, "TLT": 0.30}, 21)
    dec_expand = engine.evaluate(tp_expand, state, peak_nav=100000.0)
    assert dec_expand.approved is False
    assert any("breached circuit breaker" in v for v in dec_expand.violations)

    # Risk reduction: Target SPY 0.20 (gross 0.20 <= current 0.50) -> APPROVED
    tp_reduce = TargetPortfolio(now, "macro_v1", {"SPY": 0.20}, 21)
    dec_reduce = engine.evaluate(tp_reduce, state, peak_nav=100000.0)
    assert dec_reduce.approved is True
