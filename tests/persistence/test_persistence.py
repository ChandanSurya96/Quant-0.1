"""Unit tests for SQLite operational state persistence layer."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

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
    TargetPortfolio,
)
from quant.persistence.database import SCHEMA_VERSION, DatabaseManager
from quant.persistence.repositories import (
    FillRepository,
    HoldingRepository,
    InstrumentRepository,
    OrderRepository,
    RunRepository,
    SnapshotRepository,
    TargetPortfolioRepository,
)


@pytest.fixture
def memory_db(tmp_path: Path) -> DatabaseManager:
    """Provides a fresh, schema-initialized database for each test."""
    db_path = tmp_path / "test_state.db"
    db = DatabaseManager(db_path)
    db.initialize_schema()
    return db


# ------------------------------------------------ 1. Schema & Version
def test_database_initialization_and_schema_version(memory_db: DatabaseManager):
    assert memory_db.get_schema_version() == SCHEMA_VERSION

    with memory_db.get_connection() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        ).fetchall()
        table_names = {r["name"] for r in tables}
        expected = {
            "schema_version",
            "system_runs",
            "instruments",
            "target_portfolios",
            "risk_evaluations",
            "orders",
            "fills",
            "physical_holdings",
            "portfolio_snapshots",
        }
        assert expected.issubset(table_names)


# ----------------------------------------------------- 2. Run CRUD
def test_system_run_crud(memory_db: DatabaseManager):
    repo = RunRepository(memory_db)
    run_id = "run_20260823_001"
    repo.create_run(run_id, ExecutionMode.PAPER, "macro_v1")

    run = repo.get_run(run_id)
    assert run is not None
    assert run["run_id"] == run_id
    assert run["execution_mode"] == "PAPER"
    assert run["status"] == "RUNNING"

    repo.complete_run(run_id, status="SUCCESS")
    updated_run = repo.get_run(run_id)
    assert updated_run["status"] == "SUCCESS"
    assert updated_run["completed_at"] is not None


# ---------------------------------------------- 3. Instrument CRUD
def test_instrument_crud(memory_db: DatabaseManager):
    repo = InstrumentRepository(memory_db)
    inst = Instrument(symbol="SPY", asset_class=AssetClass.EQUITY, currency="USD", multiplier=1.0)
    repo.save_instrument(inst, is_active=True)

    loaded = repo.get_instrument("SPY")
    assert loaded is not None
    assert loaded.symbol == "SPY"
    assert loaded.asset_class == AssetClass.EQUITY

    active_list = repo.list_active_instruments()
    assert len(active_list) == 1
    assert active_list[0].symbol == "SPY"


# ---------------------------------------- 4. TargetPortfolio CRUD
def test_target_portfolio_crud(memory_db: DatabaseManager):
    run_repo = RunRepository(memory_db)
    run_repo.create_run("run_100", ExecutionMode.RESEARCH, "macro_v1")

    port_repo = TargetPortfolioRepository(memory_db)
    now = datetime.now(timezone.utc)
    tp = TargetPortfolio(
        timestamp=now,
        strategy_id="macro_v1",
        target_weights={"SPY": 0.33, "TLT": -0.33},
        rebalance_horizon=21,
    )
    port_repo.save_target_portfolio("tp_100", tp, run_id="run_100", nav_reference=100000.0)

    loaded = port_repo.get_target_portfolio("tp_100")
    assert loaded is not None
    assert loaded.strategy_id == "macro_v1"
    assert loaded.target_weights == {"SPY": 0.33, "TLT": -0.33}
    assert loaded.rebalance_horizon == 21


# --------------------------------------------------- 5. Order CRUD
def test_order_crud(memory_db: DatabaseManager):
    run_repo = RunRepository(memory_db)
    run_repo.create_run("run_200", ExecutionMode.PAPER, "macro_v1")
    inst_repo = InstrumentRepository(memory_db)
    inst_repo.save_instrument(Instrument("SPY", AssetClass.EQUITY))

    order_repo = OrderRepository(memory_db)
    order = Order(
        order_id="ord_001",
        run_id="run_200",
        strategy_id="macro_v1",
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=50.0,
        status=OrderStatus.CREATED,
    )
    order_repo.save_order(order, ExecutionMode.PAPER, client_order_id="cl_ord_001")

    loaded = order_repo.get_order("ord_001")
    assert loaded is not None
    assert loaded.quantity == 50.0
    assert loaded.status == OrderStatus.CREATED

    order_repo.update_order_status("ord_001", OrderStatus.FILLED)
    updated = order_repo.get_order("ord_001")
    assert updated.status == OrderStatus.FILLED


# ---------------------------------------------------- 6. Fill CRUD
def test_fill_crud(memory_db: DatabaseManager):
    run_repo = RunRepository(memory_db)
    run_repo.create_run("run_300", ExecutionMode.LIVE, "macro_v1")
    inst_repo = InstrumentRepository(memory_db)
    inst_repo.save_instrument(Instrument("TLT", AssetClass.BOND))
    order_repo = OrderRepository(memory_db)
    order = Order(
        order_id="ord_300",
        run_id="run_300",
        strategy_id="macro_v1",
        symbol="TLT",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=100.0,
    )
    order_repo.save_order(order, ExecutionMode.LIVE)

    fill_repo = FillRepository(memory_db)
    fill = Fill(
        fill_id="fill_300",
        order_id="ord_300",
        symbol="TLT",
        side=OrderSide.SELL,
        quantity=100.0,
        fill_price=95.50,
        commission=1.0,
        timestamp=datetime.now(timezone.utc),
    )
    fill_repo.save_fill(fill, broker_execution_id="ib_exec_999")

    loaded = fill_repo.get_fill("fill_300")
    assert loaded is not None
    assert loaded.fill_price == 95.50
    assert loaded.quantity == 100.0

    by_broker_id = fill_repo.get_fill_by_broker_execution_id("ib_exec_999")
    assert by_broker_id is not None
    assert by_broker_id.fill_id == "fill_300"


# ------------------------------------------------- 7. Holding CRUD
def test_holding_crud(memory_db: DatabaseManager):
    inst_repo = InstrumentRepository(memory_db)
    inst_repo.save_instrument(Instrument("SPY", AssetClass.EQUITY))
    inst_repo.save_instrument(Instrument("TLT", AssetClass.BOND))

    holding_repo = HoldingRepository(memory_db)
    h_spy = Holding("SPY", shares=100.0, cost_basis=400.0, current_price=450.0, market_value=45000.0)
    h_tlt = Holding("TLT", shares=-200.0, cost_basis=100.0, current_price=95.0, market_value=-19000.0)

    holding_repo.save_holdings({"SPY": h_spy, "TLT": h_tlt})

    holdings = holding_repo.get_holdings()
    assert len(holdings) == 2
    assert holdings["SPY"].shares == 100.0
    assert holdings["TLT"].shares == -200.0  # Preserves short holdings


# ------------------------------------------------ 8. Snapshot CRUD
def test_snapshot_crud(memory_db: DatabaseManager):
    run_repo = RunRepository(memory_db)
    run_repo.create_run("run_400", ExecutionMode.PAPER, "macro_v1")
    inst_repo = InstrumentRepository(memory_db)
    inst_repo.save_instrument(Instrument("SPY", AssetClass.EQUITY))

    snap_repo = SnapshotRepository(memory_db)
    h_spy = Holding("SPY", shares=100.0, cost_basis=400.0, current_price=450.0, market_value=45000.0)
    state = PortfolioState(
        timestamp=datetime.now(timezone.utc),
        cash=55000.0,
        holdings={"SPY": h_spy},
        nav=100000.0,
        realized_weights={"SPY": 0.45},
    )

    snap_repo.save_snapshot("snap_001", "run_400", state, ExecutionMode.PAPER, "macro_v1")

    latest = snap_repo.get_latest_snapshot("macro_v1")
    assert latest is not None
    assert latest["nav"] == 100000.0
    assert latest["cash"] == 55000.0


# ----------------------------------- 9. Idempotency & Constraints
def test_duplicate_run_id_rejected(memory_db: DatabaseManager):
    repo = RunRepository(memory_db)
    repo.create_run("run_dup", ExecutionMode.RESEARCH, "macro_v1")
    with pytest.raises(sqlite3.IntegrityError):
        repo.create_run("run_dup", ExecutionMode.RESEARCH, "macro_v1")


def test_duplicate_broker_execution_id_rejected(memory_db: DatabaseManager):
    run_repo = RunRepository(memory_db)
    run_repo.create_run("run_500", ExecutionMode.LIVE, "macro_v1")
    inst_repo = InstrumentRepository(memory_db)
    inst_repo.save_instrument(Instrument("SPY", AssetClass.EQUITY))
    order_repo = OrderRepository(memory_db)
    order = Order("ord_500", "run_500", "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 10.0)
    order_repo.save_order(order, ExecutionMode.LIVE)

    fill_repo = FillRepository(memory_db)
    fill1 = Fill("fill_a", "ord_500", "SPY", OrderSide.BUY, 10.0, 450.0, 1.0, datetime.now(timezone.utc))
    fill_repo.save_fill(fill1, broker_execution_id="ib_unique_123")

    # Attempting to save another fill with same broker_execution_id must fail
    fill2 = Fill("fill_b", "ord_500", "SPY", OrderSide.BUY, 10.0, 450.0, 1.0, datetime.now(timezone.utc))
    with pytest.raises(sqlite3.IntegrityError):
        fill_repo.save_fill(fill2, broker_execution_id="ib_unique_123")


# ------------------------------------- 10. Foreign Key Enforcement
def test_foreign_key_enforcement_invalid_run(memory_db: DatabaseManager):
    inst_repo = InstrumentRepository(memory_db)
    inst_repo.save_instrument(Instrument("SPY", AssetClass.EQUITY))
    order_repo = OrderRepository(memory_db)

    # ord_invalid refers to non-existent run_id 'non_existent_run'
    order = Order("ord_inv", "non_existent_run", "macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 10.0)
    with pytest.raises(sqlite3.IntegrityError):
        order_repo.save_order(order, ExecutionMode.RESEARCH)


# -------------------------------- 11. Atomic Transactions & Rollback
def test_transaction_atomic_rollback(memory_db: DatabaseManager):
    run_repo = RunRepository(memory_db)

    try:
        with memory_db.transaction() as conn:
            run_repo.create_run("run_atomic", ExecutionMode.PAPER, "macro_v1", conn=conn)
            # Intentionally cause an integrity violation
            conn.execute("INSERT INTO system_runs (run_id) VALUES (NULL);")  # Fails NOT NULL
    except Exception:
        pass

    # Assert run_atomic was completely rolled back
    assert run_repo.get_run("run_atomic") is None


# ---------------------------------- 12. Process Restart & Recovery
def test_process_restart_state_hydration(tmp_path: Path):
    db_file = tmp_path / "test_restart_state.db"

    # 1. First Process Session
    db1 = DatabaseManager(db_file)
    db1.initialize_schema()

    run_repo1 = RunRepository(db1)
    run_repo1.create_run("run_session_1", ExecutionMode.PAPER, "macro_v1")

    inst_repo1 = InstrumentRepository(db1)
    inst_repo1.save_instrument(Instrument("SPY", AssetClass.EQUITY))
    inst_repo1.save_instrument(Instrument("TLT", AssetClass.BOND))

    holding_repo1 = HoldingRepository(db1)
    h_spy = Holding("SPY", shares=50.0, cost_basis=400.0, current_price=450.0, market_value=22500.0)
    h_tlt = Holding("TLT", shares=-100.0, cost_basis=100.0, current_price=95.0, market_value=-9500.0)
    holding_repo1.save_holdings({"SPY": h_spy, "TLT": h_tlt})

    snap_repo1 = SnapshotRepository(db1)
    state = PortfolioState(
        timestamp=datetime.now(timezone.utc),
        cash=87000.0,
        holdings={"SPY": h_spy, "TLT": h_tlt},
        nav=100000.0,
        realized_weights={"SPY": 0.225, "TLT": -0.095},
    )
    snap_repo1.save_snapshot("snap_sess_1", "run_session_1", state, ExecutionMode.PAPER, "macro_v1")
    run_repo1.complete_run("run_session_1", status="SUCCESS")

    # 2. Simulate Process Kill & Re-launch
    del db1, run_repo1, inst_repo1, holding_repo1, snap_repo1

    # 3. Second Process Session (Hydration from SQLite file)
    db2 = DatabaseManager(db_file)
    assert db2.get_schema_version() == 1

    run_repo2 = RunRepository(db2)
    latest_run = run_repo2.get_latest_run("macro_v1")
    assert latest_run is not None
    assert latest_run["run_id"] == "run_session_1"
    assert latest_run["status"] == "SUCCESS"

    holding_repo2 = HoldingRepository(db2)
    recovered_holdings = holding_repo2.get_holdings()
    assert len(recovered_holdings) == 2
    assert recovered_holdings["SPY"].shares == 50.0
    assert recovered_holdings["TLT"].shares == -100.0

    snap_repo2 = SnapshotRepository(db2)
    recovered_snap = snap_repo2.get_latest_snapshot("macro_v1")
    assert recovered_snap is not None
    assert recovered_snap["nav"] == 100000.0
    assert recovered_snap["cash"] == 87000.0


# -------------------------------- 13. Domain Isolation from SQLite
def test_domain_isolation_from_sqlite():
    """Verifies that quant.core domain contracts have zero dependency on sqlite3."""
    import quant.core.enums as core_enums
    import quant.core.interfaces as core_interfaces

    assert "sqlite3" not in dir(core_interfaces)
    assert "sqlite3" not in dir(core_enums)
