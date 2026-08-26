"""Unit tests for Order Management System (OMS) and lifecycle state machines."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from quant.core.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
)
from quant.core.exceptions import InvalidStateTransitionError
from quant.core.interfaces import Holding, Order, TargetPortfolio
from quant.oms.approval import AutoApproveGate
from quant.oms.engine import OrderManagementSystem
from quant.oms.lifecycle import transition_order


# -------------------------------------------------------- 1. Target -> Order Deltas
def test_oms_long_increase():
    # Current +100 shares, Target +150 shares -> BUY 50
    current_h = {"SPY": Holding("SPY", shares=100.0, cost_basis=400.0, current_price=400.0, market_value=40000.0)}
    # Target weight: $60,000 / $100,000 NAV = 0.60 (150 shares @ $400)
    tp = TargetPortfolio(datetime.now(timezone.utc), "macro_v1", {"SPY": 0.60}, 21)
    prices = {"SPY": 400.0}

    batch = OrderManagementSystem.generate_order_batch(
        current_h, tp, prices, nav=100000.0, run_id="run_01", batch_id="b_01"
    )
    assert len(batch.orders) == 1
    order = batch.orders[0]
    assert order.symbol == "SPY"
    assert order.side == OrderSide.BUY
    assert order.quantity == pytest.approx(50.0, abs=1e-4)
    assert order.client_order_id == "b_01_SPY_BUY"


def test_oms_long_reduction():
    # Current +100 shares, Target +50 shares -> SELL 50
    current_h = {"SPY": Holding("SPY", shares=100.0, cost_basis=400.0, current_price=400.0, market_value=40000.0)}
    # Target weight: $20,000 / $100,000 = 0.20 (50 shares @ $400)
    tp = TargetPortfolio(datetime.now(timezone.utc), "macro_v1", {"SPY": 0.20}, 21)
    prices = {"SPY": 400.0}

    batch = OrderManagementSystem.generate_order_batch(
        current_h, tp, prices, nav=100000.0, run_id="run_01", batch_id="b_02"
    )
    assert len(batch.orders) == 1
    order = batch.orders[0]
    assert order.symbol == "SPY"
    assert order.side == OrderSide.SELL
    assert order.quantity == pytest.approx(50.0, abs=1e-4)


def test_oms_position_closure():
    # Current +100 shares, Target 0 shares -> SELL 100
    current_h = {"SPY": Holding("SPY", shares=100.0, cost_basis=400.0, current_price=400.0, market_value=40000.0)}
    tp = TargetPortfolio(datetime.now(timezone.utc), "macro_v1", {}, 21)  # Target 0
    prices = {"SPY": 400.0}

    batch = OrderManagementSystem.generate_order_batch(
        current_h, tp, prices, nav=100000.0, run_id="run_01", batch_id="b_03"
    )
    assert len(batch.orders) == 1
    assert batch.orders[0].side == OrderSide.SELL
    assert batch.orders[0].quantity == pytest.approx(100.0, abs=1e-4)


def test_oms_short_opening():
    # Current 0 shares, Target -100 shares -> SELL 100
    current_h = {}
    # Target weight: -$10,000 / $100,000 = -0.10 (-100 shares @ $100)
    tp = TargetPortfolio(datetime.now(timezone.utc), "macro_v1", {"TLT": -0.10}, 21)
    prices = {"TLT": 100.0}

    batch = OrderManagementSystem.generate_order_batch(
        current_h, tp, prices, nav=100000.0, run_id="run_01", batch_id="b_04"
    )
    assert len(batch.orders) == 1
    order = batch.orders[0]
    assert order.symbol == "TLT"
    assert order.side == OrderSide.SELL
    assert order.quantity == pytest.approx(100.0, abs=1e-4)


def test_oms_short_increase():
    # Current -100 shares, Target -150 shares -> SELL 50
    current_h = {"TLT": Holding("TLT", shares=-100.0, cost_basis=100.0, current_price=100.0, market_value=-10000.0)}
    tp = TargetPortfolio(datetime.now(timezone.utc), "macro_v1", {"TLT": -0.15}, 21)
    prices = {"TLT": 100.0}

    batch = OrderManagementSystem.generate_order_batch(
        current_h, tp, prices, nav=100000.0, run_id="run_01", batch_id="b_05"
    )
    assert len(batch.orders) == 1
    order = batch.orders[0]
    assert order.side == OrderSide.SELL
    assert order.quantity == pytest.approx(50.0, abs=1e-4)


def test_oms_short_reduction():
    # Current -100 shares, Target -50 shares -> BUY 50
    current_h = {"TLT": Holding("TLT", shares=-100.0, cost_basis=100.0, current_price=100.0, market_value=-10000.0)}
    tp = TargetPortfolio(datetime.now(timezone.utc), "macro_v1", {"TLT": -0.05}, 21)
    prices = {"TLT": 100.0}

    batch = OrderManagementSystem.generate_order_batch(
        current_h, tp, prices, nav=100000.0, run_id="run_01", batch_id="b_06"
    )
    assert len(batch.orders) == 1
    order = batch.orders[0]
    assert order.side == OrderSide.BUY
    assert order.quantity == pytest.approx(50.0, abs=1e-4)


def test_oms_short_cover():
    # Current -100 shares, Target 0 shares -> BUY 100
    current_h = {"TLT": Holding("TLT", shares=-100.0, cost_basis=100.0, current_price=100.0, market_value=-10000.0)}
    tp = TargetPortfolio(datetime.now(timezone.utc), "macro_v1", {}, 21)
    prices = {"TLT": 100.0}

    batch = OrderManagementSystem.generate_order_batch(
        current_h, tp, prices, nav=100000.0, run_id="run_01", batch_id="b_07"
    )
    assert len(batch.orders) == 1
    order = batch.orders[0]
    assert order.side == OrderSide.BUY
    assert order.quantity == pytest.approx(100.0, abs=1e-4)


def test_oms_zero_delta_produces_no_order():
    # Current 100 shares @ $100, Target 100 shares ($10,000 / $100k = 0.10)
    current_h = {"SPY": Holding("SPY", shares=100.0, cost_basis=100.0, current_price=100.0, market_value=10000.0)}
    tp = TargetPortfolio(datetime.now(timezone.utc), "macro_v1", {"SPY": 0.10}, 21)
    prices = {"SPY": 100.0}

    batch = OrderManagementSystem.generate_order_batch(
        current_h, tp, prices, nav=100000.0, run_id="run_01"
    )
    assert len(batch.orders) == 0


def test_oms_multiple_instruments_and_determinism():
    current_h = {
        "SPY": Holding("SPY", 100.0, 400.0, 400.0, 40000.0),
        "TLT": Holding("TLT", -200.0, 100.0, 100.0, -20000.0),
        "GLD": Holding("GLD", 50.0, 180.0, 180.0, 9000.0),
    }
    # Target: SPY 0.20 (50 shares), TLT 0.0 (close short), FXE -0.10 (open short)
    tp = TargetPortfolio(
        datetime.now(timezone.utc),
        "macro_v1",
        {"SPY": 0.20, "FXE": -0.10},
        21,
    )
    prices = {"SPY": 400.0, "TLT": 100.0, "GLD": 180.0, "FXE": 100.0}

    batch1 = OrderManagementSystem.generate_order_batch(
        current_h, tp, prices, nav=100000.0, run_id="run_01", batch_id="b_det"
    )
    batch2 = OrderManagementSystem.generate_order_batch(
        current_h, tp, prices, nav=100000.0, run_id="run_01", batch_id="b_det"
    )

    assert len(batch1.orders) == 4  # SPY sell, TLT buy/cover, GLD sell/close, FXE sell/short
    assert [o.symbol for o in batch1.orders] == ["FXE", "GLD", "SPY", "TLT"]
    assert [o.client_order_id for o in batch1.orders] == [o.client_order_id for o in batch2.orders]


# ------------------------------------------------- 2. Order Lifecycle Transitions
def test_order_lifecycle_valid_transitions():
    order = Order("ord_1", "run_1", "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 10.0)
    assert order.status == OrderStatus.CREATED

    o_app = transition_order(order, OrderStatus.APPROVED)
    assert o_app.status == OrderStatus.APPROVED

    o_sub = transition_order(o_app, OrderStatus.SUBMITTED)
    assert o_sub.status == OrderStatus.SUBMITTED

    o_part = transition_order(o_sub, OrderStatus.PARTIALLY_FILLED)
    assert o_part.status == OrderStatus.PARTIALLY_FILLED

    o_fill = transition_order(o_part, OrderStatus.FILLED)
    assert o_fill.status == OrderStatus.FILLED


def test_order_lifecycle_terminal_cancellation_and_rejection():
    order = Order("ord_1", "run_1", "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 10.0)

    o_can = transition_order(order, OrderStatus.CANCELLED)
    assert o_can.status == OrderStatus.CANCELLED

    o_rej = transition_order(order, OrderStatus.REJECTED)
    assert o_rej.status == OrderStatus.REJECTED


def test_order_lifecycle_invalid_transitions_rejected():
    order = Order("ord_1", "run_1", "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 10.0, status=OrderStatus.FILLED)

    with pytest.raises(InvalidStateTransitionError, match="Illegal order state transition from FILLED to CREATED"):
        transition_order(order, OrderStatus.CREATED)

    with pytest.raises(InvalidStateTransitionError, match="Illegal order state transition from FILLED to SUBMITTED"):
        transition_order(order, OrderStatus.SUBMITTED)


# ----------------------------------------------------- 3. Execution Approval Gate
def test_auto_approve_gate():
    batch = OrderManagementSystem.generate_order_batch({}, TargetPortfolio(datetime.now(timezone.utc), "m", {"SPY": 0.5}, 21), {"SPY": 100.0}, 10000.0, "run_1")

    gate = AutoApproveGate()
    approved_batch = gate.approve_batch(batch)

    for o in approved_batch.orders:
        assert o.status == OrderStatus.APPROVED
