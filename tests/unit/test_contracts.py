"""Unit tests for core domain contracts and type invariants."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from quant.core.enums import (
    AssetClass,
    ExecutionMode,
    OrderSide,
    OrderStatus,
    OrderType,
)
from quant.core.interfaces import (
    Fill,
    Holding,
    Instrument,
    Order,
    PortfolioState,
    RiskDecision,
    Signal,
    TargetPortfolio,
)

NOW = datetime.now(timezone.utc)


# ------------------------------------------------------------- 1. Instrument
def test_instrument_valid():
    inst = Instrument(symbol="SPY", asset_class=AssetClass.EQUITY, currency="USD", multiplier=1.0)
    assert inst.symbol == "SPY"
    assert inst.asset_class == AssetClass.EQUITY
    assert inst.multiplier == 1.0


def test_instrument_invalid_empty_symbol():
    with pytest.raises(ValueError, match="Invalid instrument symbol"):
        Instrument(symbol="", asset_class=AssetClass.EQUITY)


def test_instrument_invalid_multiplier():
    with pytest.raises(ValueError, match="Multiplier must be positive"):
        Instrument(symbol="SPY", asset_class=AssetClass.EQUITY, multiplier=-1.0)


# ----------------------------------------------------------------- 2. Signal
def test_signal_valid():
    sig = Signal(timestamp=NOW, strategy_id="macro_v1", symbol="TLT", score=0.85)
    assert sig.strategy_id == "macro_v1"
    assert sig.symbol == "TLT"
    assert sig.score == 0.85


def test_signal_empty_fields():
    with pytest.raises(ValueError, match="strategy_id cannot be empty"):
        Signal(timestamp=NOW, strategy_id="", symbol="TLT", score=0.85)
    with pytest.raises(ValueError, match="symbol cannot be empty"):
        Signal(timestamp=NOW, strategy_id="macro_v1", symbol="", score=0.85)


# -------------------------------------------------------- 3. TargetPortfolio
def test_target_portfolio_valid_long_short():
    weights = {"SPY": 0.33, "TLT": -0.33, "GLD": 0.33}
    tp = TargetPortfolio(timestamp=NOW, strategy_id="macro_v1", target_weights=weights, rebalance_horizon=21)
    assert tp.target_weights["SPY"] == 0.33
    assert tp.target_weights["TLT"] == -0.33  # Preserves direct shorting representation
    assert tp.rebalance_horizon == 21


def test_target_portfolio_invalid_weight():
    with pytest.raises(ValueError, match="cannot exceed"):
        TargetPortfolio(timestamp=NOW, strategy_id="macro_v1", target_weights={"SPY": 1.5}, rebalance_horizon=21)


def test_target_portfolio_invalid_horizon():
    with pytest.raises(ValueError, match="rebalance_horizon must be positive"):
        TargetPortfolio(timestamp=NOW, strategy_id="macro_v1", target_weights={"SPY": 0.5}, rebalance_horizon=0)


# ----------------------------------------------------------- 4. RiskDecision
def test_risk_decision_approved():
    rd = RiskDecision(timestamp=NOW, approved=True, adjusted_weights={"SPY": 0.5, "TLT": -0.5})
    assert rd.approved is True
    assert rd.violations == []


def test_risk_decision_rejected():
    rd = RiskDecision(
        timestamp=NOW,
        approved=False,
        adjusted_weights={},
        violations=["Gross leverage 1.5 exceeds cap 1.0"],
    )
    assert rd.approved is False
    assert len(rd.violations) == 1


# ------------------------------------------------------------------ 5. Order
def test_order_creation_and_fields():
    order = Order(
        order_id="ord_001",
        run_id="run_100",
        strategy_id="macro_v1",
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=150.0,
        status=OrderStatus.CREATED,
    )
    assert order.order_id == "ord_001"
    assert order.side == OrderSide.BUY
    assert order.quantity == 150.0
    assert order.status == OrderStatus.CREATED


def test_order_invalid_quantity():
    with pytest.raises(ValueError, match="Order quantity must be positive"):
        Order(
            order_id="ord_001",
            run_id="run_100",
            strategy_id="macro_v1",
            symbol="SPY",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=-10.0,
        )


# ------------------------------------------------------------------- 6. Fill
def test_fill_valid():
    fill = Fill(
        fill_id="fill_001",
        order_id="ord_001",
        symbol="SPY",
        side=OrderSide.BUY,
        quantity=150.0,
        fill_price=450.25,
        commission=1.50,
        timestamp=NOW,
    )
    assert fill.fill_id == "fill_001"
    assert fill.order_id == "ord_001"
    assert fill.fill_price == 450.25
    assert fill.commission == 1.50


def test_fill_invalid_price():
    with pytest.raises(ValueError, match="Fill price must be positive"):
        Fill(
            fill_id="fill_001",
            order_id="ord_001",
            symbol="SPY",
            side=OrderSide.BUY,
            quantity=150.0,
            fill_price=-10.0,
            commission=1.50,
            timestamp=NOW,
        )


# --------------------------------------------------------- 7. PortfolioState
def test_portfolio_state_nav_conservation():
    holdings = {
        "SPY": Holding(symbol="SPY", shares=100.0, cost_basis=400.0, current_price=450.0, market_value=45000.0),
        "TLT": Holding(symbol="TLT", shares=-200.0, cost_basis=100.0, current_price=95.0, market_value=-19000.0),
    }
    # Cash = 74,000, Total Market Value = 45,000 - 19,000 = 26,000. Expected NAV = 100,000
    ps = PortfolioState(
        timestamp=NOW,
        cash=74000.0,
        holdings=holdings,
        nav=100000.0,
        realized_weights={"SPY": 0.45, "TLT": -0.19},
    )
    assert ps.nav == 100000.0
    assert ps.cash == 74000.0


def test_portfolio_state_nav_mismatch_raises_error():
    holdings = {
        "SPY": Holding(symbol="SPY", shares=100.0, cost_basis=400.0, current_price=450.0, market_value=45000.0),
    }
    with pytest.raises(ValueError, match="NAV mismatch"):
        # Declares NAV = 100,000 when Cash=10,000 + MV=45,000 = 55,000
        PortfolioState(
            timestamp=NOW,
            cash=10000.0,
            holdings=holdings,
            nav=100000.0,
            realized_weights={"SPY": 0.45},
        )


# ---------------------------------------------------------- 8. ExecutionMode
def test_execution_mode_values():
    assert ExecutionMode.RESEARCH.value == "RESEARCH"
    assert ExecutionMode.PAPER.value == "PAPER"
    assert ExecutionMode.LIVE.value == "LIVE"
