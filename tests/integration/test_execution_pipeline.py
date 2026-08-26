"""Integration tests for the full Target -> OMS -> Approval -> PaperBroker -> Persistence pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from quant.broker.paper_broker import PaperBroker
from quant.core.enums import AssetClass, ExecutionMode, OrderStatus
from quant.core.interfaces import Instrument, TargetPortfolio
from quant.oms.approval import AutoApproveGate
from quant.oms.engine import OrderManagementSystem
from quant.persistence.database import DatabaseManager
from quant.persistence.repositories import (
    FillRepository,
    HoldingRepository,
    InstrumentRepository,
    OrderRepository,
    RunRepository,
    SnapshotRepository,
    TargetPortfolioRepository,
)


def test_full_execution_pipeline_with_persistence(tmp_path: Path):
    db_file = tmp_path / "test_pipeline.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    # 1. Initialize System Run & Instruments
    run_repo = RunRepository(db)
    run_id = "run_pipe_001"
    run_repo.create_run(run_id, ExecutionMode.PAPER, "macro_v1")

    inst_repo = InstrumentRepository(db)
    inst_repo.save_instrument(Instrument("SPY", AssetClass.EQUITY))
    inst_repo.save_instrument(Instrument("TLT", AssetClass.BOND))

    # 2. Strategy Emits TargetPortfolio
    tp_repo = TargetPortfolioRepository(db)
    now = datetime.now(timezone.utc)
    tp = TargetPortfolio(now, "macro_v1", {"SPY": 0.50, "TLT": -0.30}, rebalance_horizon=21)
    tp_repo.save_target_portfolio("tp_pipe_001", tp, run_id=run_id, nav_reference=100000.0)

    # 3. OMS Generates OrderBatch
    prices = {"SPY": 400.0, "TLT": 100.0}
    current_holdings = {}
    oms = OrderManagementSystem()
    batch = oms.generate_order_batch(
        current_holdings=current_holdings,
        target_portfolio=tp,
        current_prices=prices,
        nav=100000.0,
        run_id=run_id,
        execution_mode=ExecutionMode.PAPER,
        batch_id="batch_pipe_001",
        target_portfolio_id="tp_pipe_001",
    )

    assert len(batch.orders) == 2  # SPY buy, TLT sell/short

    # 4. Persist CREATED Orders atomically
    order_repo = OrderRepository(db)
    with db.transaction() as conn:
        for ord_item in batch.orders:
            order_repo.save_order(ord_item, execution_mode=ExecutionMode.PAPER, conn=conn)

    # 5. Approval Gate
    gate = AutoApproveGate()
    approved_batch = gate.approve_batch(batch)

    # 6. Broker Execution
    broker = PaperBroker(initial_cash=100000.0, cost_bps=10.0)
    fill_repo = FillRepository(db)
    holding_repo = HoldingRepository(db)
    snap_repo = SnapshotRepository(db)

    with db.transaction() as conn:
        for ord_item in approved_batch.orders:
            fill = broker.submit_order(ord_item, price_lookup=prices)
            assert fill is not None

            # Persist fill
            fill_repo.save_fill(fill, broker_execution_id=fill.fill_id, conn=conn)
            # Update order status to FILLED
            order_repo.update_order_status(ord_item.order_id, OrderStatus.FILLED, conn=conn)

        # Update physical holdings in persistence
        broker_positions = broker.get_positions()
        holding_repo.save_holdings(broker_positions, conn=conn)

        # Persist final PortfolioState snapshot
        state = broker.get_account_state(current_prices=prices)
        snap_repo.save_snapshot("snap_pipe_001", run_id, state, ExecutionMode.PAPER, "macro_v1", conn=conn)

    run_repo.complete_run(run_id, status="SUCCESS")

    # 7. Verification of Persisted State
    persisted_orders = order_repo.list_orders_for_run(run_id)
    assert len(persisted_orders) == 2
    assert all(o.status == OrderStatus.FILLED for o in persisted_orders)

    persisted_holdings = holding_repo.get_holdings()
    assert len(persisted_holdings) == 2
    assert persisted_holdings["SPY"].shares == 125.0  # $50,000 / $400
    assert persisted_holdings["TLT"].shares == -300.0  # -$30,000 / $100

    latest_snap = snap_repo.get_latest_snapshot("macro_v1")
    assert latest_snap is not None
    assert latest_snap["nav"] == pytest.approx(100000.0 - 80.0, abs=1e-3)  # NAV minus friction fees


def test_crash_restart_does_not_duplicate_orders(tmp_path: Path):
    db_file = tmp_path / "test_restart_dup.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    run_repo = RunRepository(db)
    run_repo.create_run("run_dup_001", ExecutionMode.PAPER, "macro_v1")
    inst_repo = InstrumentRepository(db)
    inst_repo.save_instrument(Instrument("SPY", AssetClass.EQUITY))

    order_repo = OrderRepository(db)
    tp = TargetPortfolio(datetime.now(timezone.utc), "macro_v1", {"SPY": 0.50}, 21)
    batch = OrderManagementSystem.generate_order_batch(
        {}, tp, {"SPY": 400.0}, 100000.0, "run_dup_001", batch_id="batch_dup"
    )

    # Persist first order
    order_repo.save_order(batch.orders[0], ExecutionMode.PAPER, client_order_id="batch_dup_SPY_BUY")

    # Simulate Process Restart: Attempting to save another order with same client_order_id fails
    with pytest.raises(Exception):
        order_repo.save_order(batch.orders[0], ExecutionMode.PAPER, client_order_id="batch_dup_SPY_BUY")
