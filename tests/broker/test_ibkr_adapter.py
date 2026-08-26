"""Comprehensive unit and integration test suite for Interactive Brokers adapter (P7)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from quant.broker.ibkr import (
    IBKRBrokerAdapter,
    IBKRConfig,
    IBKRLiveSafetyLockedError,
    IBKRShortUnavailableError,
    MockIBKRClient,
    ShortAvailability,
)
from quant.core.enums import AssetClass, ExecutionMode, OrderSide, OrderStatus, OrderType
from quant.core.interfaces import Instrument, Order, PortfolioState, TargetPortfolio
from quant.oms.engine import OrderManagementSystem
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
from quant.risk.engine import RiskEngine


@pytest.fixture
def mock_client() -> MockIBKRClient:
    cfg = IBKRConfig(host="127.0.0.1", port=7497, is_paper=True, live_execution_enabled=False)
    return MockIBKRClient(cfg)


@pytest.fixture
def ibkr_adapter(mock_client: MockIBKRClient) -> IBKRBrokerAdapter:
    cfg = IBKRConfig(host="127.0.0.1", port=7497, is_paper=True, live_execution_enabled=False)
    return IBKRBrokerAdapter(config=cfg, client=mock_client)


# ------------------------------------------------ 1. Connectivity Tests
def test_ibkr_successful_connection(ibkr_adapter: IBKRBrokerAdapter):
    """Adapter connects successfully in paper mode and reports CONNECTED."""
    assert ibkr_adapter.client.is_connected() is True
    assert ibkr_adapter.health_check() == "CONNECTED"


def test_ibkr_disconnect_and_reconnect(ibkr_adapter: IBKRBrokerAdapter):
    """Adapter tracks disconnect and reconnect transitions."""
    ibkr_adapter.client.disconnect()
    assert ibkr_adapter.client.is_connected() is False

    ibkr_adapter.client.connect()
    assert ibkr_adapter.client.is_connected() is True


def test_ibkr_live_safety_lock_blocks_unauthorized_live_connection():
    """Live connection without live_execution_enabled=True is blocked fail-closed."""
    cfg = IBKRConfig(host="127.0.0.1", port=7496, is_paper=False, live_execution_enabled=False)
    with pytest.raises(IBKRLiveSafetyLockedError):
        IBKRBrokerAdapter(config=cfg)


# ------------------------------------------------ 2. Order Submissions
def test_ibkr_market_buy_submission(ibkr_adapter: IBKRBrokerAdapter):
    """Submitting a market BUY returns None (asynchronous boundary) and tracks order in IBKR."""
    order = Order(
        order_id="ord_buy_1",
        run_id="run_ibkr_1",
        strategy_id="macro_v1",
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=50.0,
        client_order_id="cl_buy_1",
    )
    fill = ibkr_adapter.submit_order(order)
    assert fill is None  # Asynchronous acknowledgment

    tracked = ibkr_adapter.get_order("ord_buy_1")
    assert tracked is not None
    assert tracked.symbol == "SPY"
    assert tracked.side == OrderSide.BUY
    assert tracked.quantity == 50.0
    assert tracked.status == OrderStatus.SUBMITTED


def test_ibkr_market_sell_submission(ibkr_adapter: IBKRBrokerAdapter, mock_client: MockIBKRClient):
    """Submitting a long liquidation SELL succeeds when position exists."""
    mock_client._positions["SPY"] = (100.0, 400.0, 400.0)

    order = Order(
        order_id="ord_sell_1",
        run_id="run_ibkr_1",
        strategy_id="macro_v1",
        symbol="SPY",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=50.0,
        client_order_id="cl_sell_1",
    )
    fill = ibkr_adapter.submit_order(order)
    assert fill is None


def test_ibkr_invalid_order_quantity(ibkr_adapter: IBKRBrokerAdapter):
    """Submitting order with non-positive quantity fails immediately."""
    with pytest.raises(ValueError):
        Order("ord_bad", "run_1", "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 0.0)


# ------------------------------------------------ 3. Short Borrow Availability
def test_ibkr_short_locate_available(ibkr_adapter: IBKRBrokerAdapter, mock_client: MockIBKRClient):
    """Short sale proceeds when short locate is AVAILABLE."""
    mock_client._short_availability_map["TLT"] = ShortAvailability.AVAILABLE

    order = Order(
        order_id="ord_short_1",
        run_id="run_ibkr_1",
        strategy_id="macro_v1",
        symbol="TLT",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=50.0,
        client_order_id="cl_short_1",
    )
    fill = ibkr_adapter.submit_order(order)
    assert fill is None


def test_ibkr_short_locate_unavailable_rejects_order(ibkr_adapter: IBKRBrokerAdapter, mock_client: MockIBKRClient):
    """Short sale is rejected when short locate is UNAVAILABLE."""
    mock_client._short_availability_map["TLT"] = ShortAvailability.UNAVAILABLE

    order = Order(
        order_id="ord_short_unavail",
        run_id="run_ibkr_1",
        strategy_id="macro_v1",
        symbol="TLT",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=50.0,
        client_order_id="cl_short_unavail",
    )
    with pytest.raises(IBKRShortUnavailableError) as exc_info:
        ibkr_adapter.submit_order(order)
    assert "Short borrow unavailable" in str(exc_info.value)


def test_ibkr_short_locate_unknown_fails_closed(ibkr_adapter: IBKRBrokerAdapter, mock_client: MockIBKRClient):
    """Short sale fails closed when short locate is UNKNOWN."""
    mock_client._short_availability_map["TLT"] = ShortAvailability.UNKNOWN

    order = Order(
        order_id="ord_short_unk",
        run_id="run_ibkr_1",
        strategy_id="macro_v1",
        symbol="TLT",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=50.0,
        client_order_id="cl_short_unk",
    )
    with pytest.raises(IBKRShortUnavailableError) as exc_info:
        ibkr_adapter.submit_order(order)
    assert "failing closed" in str(exc_info.value).lower()


# ------------------------------------------------ 4. Partial Fills & Execution Ingestion
def test_ibkr_multiple_partial_fills_and_full_fill(ibkr_adapter: IBKRBrokerAdapter, mock_client: MockIBKRClient):
    """Demonstrates asynchronous execution: submit 100 shares -> fill 40 -> fill 35 -> fill 25 -> FILLED."""
    order = Order("ord_pf_1", "run_1", "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 100.0, client_order_id="cl_pf_1")
    ibkr_adapter.submit_order(order)

    # Initial state: SUBMITTED
    assert ibkr_adapter.get_order("ord_pf_1").status == OrderStatus.SUBMITTED

    # Partial Fill 1: 40 shares @ 400.0
    mock_client.inject_partial_fill(10001, fill_shares=40.0, fill_price=400.0, commission=1.0, exec_id="e1")
    assert ibkr_adapter.get_order("ord_pf_1").status == OrderStatus.PARTIALLY_FILLED
    assert len(ibkr_adapter.get_fills()) == 1

    # Partial Fill 2: 35 shares @ 400.50
    mock_client.inject_partial_fill(10001, fill_shares=35.0, fill_price=400.50, commission=1.0, exec_id="e2")
    assert ibkr_adapter.get_order("ord_pf_1").status == OrderStatus.PARTIALLY_FILLED
    assert len(ibkr_adapter.get_fills()) == 2

    # Final Partial Fill 3: 25 shares @ 401.00 -> Order becomes FILLED
    mock_client.inject_partial_fill(10001, fill_shares=25.0, fill_price=401.00, commission=1.0, exec_id="e3")
    assert ibkr_adapter.get_order("ord_pf_1").status == OrderStatus.FILLED
    assert len(ibkr_adapter.get_fills()) == 3

    # Position in broker is now 100 shares SPY
    positions = ibkr_adapter.get_positions()
    assert positions["SPY"].shares == 100.0


def test_ibkr_duplicate_execution_id_idempotency(ibkr_adapter: IBKRBrokerAdapter, mock_client: MockIBKRClient):
    """Duplicate execution ID from broker is ignored idempotently."""
    order = Order("ord_dup_1", "run_1", "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 50.0, client_order_id="cl_dup_1")
    ibkr_adapter.submit_order(order)

    mock_client.inject_partial_fill(10001, fill_shares=50.0, fill_price=400.0, commission=1.0, exec_id="exec_unique_01")
    fills1 = ibkr_adapter.get_fills()
    assert len(fills1) == 1

    # Inject duplicate execution
    mock_client.inject_partial_fill(10001, fill_shares=50.0, fill_price=400.0, commission=1.0, exec_id="exec_unique_01")
    fills2 = ibkr_adapter.get_fills()
    assert len(fills2) == 1  # No duplicate fill created


# ------------------------------------------------ 5. End-to-End Integration Scenario
def test_ibkr_end_to_end_integration_flow(tmp_path: Path):
    """Full execution pipeline: TargetPortfolio -> RiskEngine -> OMS -> IBKR Adapter -> Fills -> SQLite -> Reconciliation."""
    db_file = tmp_path / "test_ibkr_integration.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    run_id = "run_ibkr_e2e"
    RunRepository(db).create_run(run_id, ExecutionMode.PAPER, "macro_v1")
    InstrumentRepository(db).save_instrument(Instrument("SPY", AssetClass.EQUITY))

    # Initialize mock broker client with $100k cash
    mock_client = MockIBKRClient()
    adapter = IBKRBrokerAdapter(client=mock_client)

    # Initial state snapshot
    SnapshotRepository(db).save_snapshot(
        "snap_init_ibkr", run_id, PortfolioState(datetime.now(timezone.utc), 100_000.0, {}, 100_000.0, {}),
        ExecutionMode.PAPER, "macro_v1"
    )

    # Step 1: Strategy Target Portfolio (20% SPY)
    now = datetime.now(timezone.utc)
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.20}, 21)

    # Step 2: Risk Engine Approval
    risk_engine = RiskEngine()
    dec = risk_engine.evaluate(tp, adapter.get_account_state(), portfolio_id="tp_ibkr_01")
    assert dec.approved is True

    # Step 3: OMS Order Batch Generation
    order_batch = OrderManagementSystem.generate_order_batch(
        current_holdings=adapter.get_positions(),
        target_portfolio=tp,
        current_prices={"SPY": 400.0},
        nav=100_000.0,
        run_id=run_id,
        target_portfolio_id="tp_ibkr_01",
        risk_decision=dec,
        require_risk_approval=True,
    )
    assert len(order_batch.orders) == 1
    ord_to_submit = order_batch.orders[0]  # 50 shares SPY

    # Step 4: Persist Order in SQLite & Submit to IBKR Adapter
    OrderRepository(db).save_order(ord_to_submit, ExecutionMode.PAPER)
    adapter.submit_order(ord_to_submit)

    # Step 5: Asynchronous Broker Execution (Partial Fill 1 + Partial Fill 2)
    mock_client.inject_partial_fill(10001, fill_shares=30.0, fill_price=400.0, commission=1.0, exec_id="e_p1")
    mock_client.inject_partial_fill(10001, fill_shares=20.0, fill_price=400.0, commission=1.0, exec_id="e_p2")

    # Step 6: Fill Ingestion & SQLite Synchronization
    fills = adapter.get_fills()
    assert len(fills) == 2
    for f in fills:
        FillRepository(db).save_fill(f, broker_execution_id=f.fill_id)

    OrderRepository(db).update_order_status(ord_to_submit.order_id, OrderStatus.FILLED)
    HoldingRepository(db).save_holdings(adapter.get_positions())

    # Save post-execution snapshot
    broker_state = adapter.get_account_state()
    SnapshotRepository(db).save_snapshot("snap_post_ibkr", run_id, broker_state, ExecutionMode.PAPER, "macro_v1")

    # Step 7: Post-Execution Reconciliation
    rec_result = ReconciliationEngine.reconcile(run_id, ExecutionMode.PAPER, db, adapter)
    assert rec_result.passed is True
    assert rec_result.status.value == "MATCHED"


# ------------------------------------------------ 6. Buying Power & Margin Queries
def test_ibkr_buying_power_query(ibkr_adapter: IBKRBrokerAdapter, mock_client: MockIBKRClient):
    """Buying power returns float value when connected, None when disconnected."""
    assert ibkr_adapter.get_buying_power() == 200_000.0

    mock_client.disconnect()
    assert ibkr_adapter.get_buying_power() is None


# ------------------------------------------------ 7. Disconnect and Reconnect Reconciliation
def test_ibkr_disconnect_after_fill_and_reconnect_reconciliation(tmp_path: Path):
    """Disconnect occurs after fill; reconnection allows querying executions and completing reconciliation."""
    db_file = tmp_path / "test_ibkr_reconnect.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    run_id = "run_ibkr_recon"
    RunRepository(db).create_run(run_id, ExecutionMode.PAPER, "macro_v1")
    InstrumentRepository(db).save_instrument(Instrument("SPY", AssetClass.EQUITY))

    mock_client = MockIBKRClient()
    adapter = IBKRBrokerAdapter(client=mock_client)

    # Submit order
    order = Order("ord_recon_1", run_id, "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 50.0, client_order_id="cl_recon_1")
    OrderRepository(db).save_order(order, ExecutionMode.PAPER)
    adapter.submit_order(order)

    # Broker fills order
    mock_client.inject_partial_fill(10001, fill_shares=50.0, fill_price=400.0, commission=1.0, exec_id="e_recon_1")

    # Network drops
    mock_client.disconnect()
    assert adapter.client.is_connected() is False

    # Reconnect
    mock_client.connect()
    assert adapter.client.is_connected() is True

    # Fill ingestion succeeds after reconnect
    fills = adapter.get_fills()
    assert len(fills) == 1
    FillRepository(db).save_fill(fills[0], broker_execution_id="e_recon_1")
    OrderRepository(db).update_order_status("ord_recon_1", OrderStatus.FILLED)
    HoldingRepository(db).save_holdings(adapter.get_positions())

    SnapshotRepository(db).save_snapshot("snap_post_recon", run_id, adapter.get_account_state(), ExecutionMode.PAPER, "macro_v1")
    rec_res = ReconciliationEngine.reconcile(run_id, ExecutionMode.PAPER, db, adapter)
    assert rec_res.passed is True


# ------------------------------------------------ 8. Timeout No Blind Retry & Duplicate Client Order ID
def test_ibkr_duplicate_client_order_id_prevents_duplicate_broker_submission(ibkr_adapter: IBKRBrokerAdapter):
    """Submitting with identical client_order_id returns original broker order without duplicating."""
    order1 = Order("ord_1", "run_1", "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 50.0, client_order_id="cl_same_id")
    ibkr_adapter.submit_order(order1)
    orders_count_1 = len(ibkr_adapter.client.get_order_records())

    order2 = Order("ord_2", "run_1", "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 50.0, client_order_id="cl_same_id")
    ibkr_adapter.submit_order(order2)
    orders_count_2 = len(ibkr_adapter.client.get_order_records())

    assert orders_count_1 == orders_count_2 == 1


# ------------------------------------------------ 9. Mapper Direct Conversions
def test_ibkr_mapper_conversions():
    """Verifies direct translation between IBKR representations and domain models."""
    from quant.broker.ibkr.mapper import IBKRMapper
    from quant.broker.ibkr.models import IBKRExecutionRecord

    # Order status mapping
    assert IBKRMapper.to_domain_order_status("Submitted") == OrderStatus.SUBMITTED
    assert IBKRMapper.to_domain_order_status("PartiallyFilled") == OrderStatus.PARTIALLY_FILLED
    assert IBKRMapper.to_domain_order_status("Filled") == OrderStatus.FILLED
    assert IBKRMapper.to_domain_order_status("Cancelled") == OrderStatus.CANCELLED
    assert IBKRMapper.to_domain_order_status("Inactive") == OrderStatus.REJECTED
    assert IBKRMapper.to_domain_order_status("WeirdUnmappedState") == OrderStatus.UNKNOWN

    # Execution mapping
    now = datetime.now(timezone.utc)
    rec = IBKRExecutionRecord("e_99", "ord_1", "cl_1", "SPY", "BOT", 10.0, 400.0, 1.0, now)
    fill = IBKRMapper.to_domain_fill(rec)
    assert fill.symbol == "SPY"
    assert fill.side == OrderSide.BUY
    assert fill.quantity == 10.0
    assert fill.fill_price == 400.0
    assert fill.commission == 1.0
