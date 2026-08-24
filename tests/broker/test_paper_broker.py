"""Unit tests for PaperBroker adapter."""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from quant.broker.paper_broker import PaperBroker
from quant.core.enums import ExecutionMode, OrderSide, OrderStatus, OrderType
from quant.core.interfaces import Order


# ----------------------------------------------------- 1. Market Order Buy / Sell
def test_paper_broker_market_order_buy_execution():
    broker = PaperBroker(initial_cash=100_000.0, cost_bps=10.0, slippage_bps=0.0)
    order = Order("ord_01", "run_01", "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 100.0, status=OrderStatus.APPROVED)

    fill = broker.submit_order(order, price_lookup={"SPY": 400.0})
    assert fill is not None
    assert fill.fill_price == 400.0
    assert fill.quantity == 100.0
    assert fill.commission == pytest.approx(40.0, abs=1e-4)  # $40k * 10 bps = $40

    positions = broker.get_positions()
    assert "SPY" in positions
    assert positions["SPY"].shares == 100.0
    assert broker.cash == pytest.approx(59_960.0, abs=1e-4)  # $100k - $40k - $40

    state = broker.get_account_state({"SPY": 400.0})
    assert state.nav == pytest.approx(99_960.0, abs=1e-4)


def test_paper_broker_market_order_sell_execution():
    broker = PaperBroker(initial_cash=100_000.0, cost_bps=10.0, slippage_bps=0.0)
    # Buy 100 shares first
    buy_order = Order("ord_buy", "run_01", "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 100.0, status=OrderStatus.APPROVED)
    broker.submit_order(buy_order, price_lookup={"SPY": 400.0})

    # Sell 50 shares
    sell_order = Order("ord_sell", "run_01", "macro_v1", "SPY", OrderSide.SELL, OrderType.MARKET, 50.0, status=OrderStatus.APPROVED)
    fill_sell = broker.submit_order(sell_order, price_lookup={"SPY": 400.0})

    assert fill_sell is not None
    assert fill_sell.side == OrderSide.SELL
    assert fill_sell.quantity == 50.0

    positions = broker.get_positions()
    assert positions["SPY"].shares == 50.0
    # Cash increased by $20,000 - $20 commission = $19,980
    assert broker.cash == pytest.approx(59_960.0 + 19_980.0, abs=1e-4)


# ----------------------------------------------------------- 2. Slippage Model
def test_paper_broker_buy_and_sell_slippage():
    # 5 bps slippage
    broker = PaperBroker(initial_cash=100_000.0, cost_bps=0.0, slippage_bps=5.0)

    # Buy at $100 reference price -> Exec price should be $100 * (1 + 5/10000) = $100.05
    buy_ord = Order("ord_b", "run_01", "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 100.0, status=OrderStatus.APPROVED)
    fill_b = broker.submit_order(buy_ord, price_lookup={"SPY": 100.0})
    assert fill_b.fill_price == pytest.approx(100.05, abs=1e-5)

    # Sell at $100 reference price -> Exec price should be $100 * (1 - 5/10000) = $99.95
    sell_ord = Order("ord_s", "run_01", "macro_v1", "SPY", OrderSide.SELL, OrderType.MARKET, 50.0, status=OrderStatus.APPROVED)
    fill_s = broker.submit_order(sell_ord, price_lookup={"SPY": 100.0})
    assert fill_s.fill_price == pytest.approx(99.95, abs=1e-5)


# --------------------------------------------- 3. Decomposed Commission Model
def test_paper_broker_commission_decomposition():
    # 10 bps turnover + $0.005/share + $1.00 fixed
    broker = PaperBroker(
        initial_cash=100_000.0,
        cost_bps=10.0,
        slippage_bps=0.0,
        commission_per_share=0.005,
        commission_fixed=1.00,
    )
    # Buy 200 shares @ $50 = $10,000 notional.
    # Turnover fee: $10,000 * 0.001 = $10.00
    # Share fee: 200 * 0.005 = $1.00
    # Fixed fee: $1.00
    # Total fee = $12.00
    order = Order("ord_dec", "run_01", "macro_v1", "TLT", OrderSide.BUY, OrderType.MARKET, 200.0, status=OrderStatus.APPROVED)
    fill = broker.submit_order(order, price_lookup={"TLT": 50.0})
    assert fill.commission == pytest.approx(12.00, abs=1e-5)


# ---------------------------------------------------- 4. Short Execution State
def test_paper_broker_short_accounting_lifecycle():
    broker = PaperBroker(initial_cash=100_000.0, cost_bps=10.0, slippage_bps=0.0)

    # 1. Open short 200 shares @ $100 ($20,000 proceeds, $20 fee)
    # Cash becomes $100,000 + $20,000 - $20 = $119,980.
    # Shares = -200. MV = -$20,000. NAV = $119,980 - $20,000 = $99,980.
    short_ord = Order("ord_sh", "run_01", "macro_v1", "TLT", OrderSide.SELL, OrderType.MARKET, 200.0, status=OrderStatus.APPROVED)
    fill_sh = broker.submit_order(short_ord, price_lookup={"TLT": 100.0})
    assert fill_sh.side == OrderSide.SELL

    pos = broker.get_positions()
    assert pos["TLT"].shares == -200.0
    assert broker.cash == pytest.approx(119_980.0, abs=1e-4)

    state = broker.get_account_state({"TLT": 100.0})
    assert state.nav == pytest.approx(99_980.0, abs=1e-4)

    # 2. Cover 200 shares @ $100 ($20,000 cost, $20 fee)
    cover_ord = Order("ord_cov", "run_01", "macro_v1", "TLT", OrderSide.BUY, OrderType.MARKET, 200.0, status=OrderStatus.APPROVED)
    fill_cov = broker.submit_order(cover_ord, price_lookup={"TLT": 100.0})
    assert fill_cov.side == OrderSide.BUY

    pos_after = broker.get_positions()
    assert "TLT" not in pos_after  # Position closed
    assert broker.cash == pytest.approx(99_960.0, abs=1e-4)  # $100k - $40 total fees


# -------------------------------------------------------- 5. Order Cancellation
def test_paper_broker_cancel_order():
    broker = PaperBroker(initial_cash=100_000.0)
    order = Order("ord_can", "run_01", "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 10.0, status=OrderStatus.CREATED)
    broker._orders["ord_can"] = order

    assert broker.cancel_order("ord_can") is True
    assert broker.get_order("ord_can").status == OrderStatus.CANCELLED
