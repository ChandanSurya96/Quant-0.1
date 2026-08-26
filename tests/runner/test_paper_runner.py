"""Unit tests for PaperTradingRunner execution loop, health gates, idempotency, and friction."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quant.broker.paper_broker import PaperBroker
from quant.core.enums import AssetClass
from quant.core.interfaces import Holding, Instrument
from quant.persistence.database import DatabaseManager
from quant.persistence.repositories import HoldingRepository, InstrumentRepository
from quant.runner.models import RunStatus
from quant.runner.runner import PaperTradingRunner
from quant.strategies.macro import SystematicMacroStrategy


@pytest.fixture
def test_setup(tmp_path: Path):
    db_file = tmp_path / "test_runner.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    broker = PaperBroker(initial_cash=100_000.0)
    strategy = SystematicMacroStrategy(rebalance_cadence_days=21)
    runner = PaperTradingRunner(db_manager=db, broker=broker, strategy=strategy)

    # Load 1,000 bars fixture
    df = pd.read_csv("tests/fixtures/synthetic_macro_12etf.csv", index_col=0, parse_dates=True)
    return db, broker, strategy, runner, df


def test_runner_successful_execution_and_report(test_setup):
    """Verifies a full successful paper execution cycle produces durable ledger records and reports."""
    db, broker, strategy, runner, df = test_setup
    window_df = df.iloc[:800]
    as_of_date = window_df.index[-1]

    record, report = runner.run_once(
        run_id="run_p6_success_01",
        as_of_date=as_of_date,
        market_data=window_df,
        is_rebalance_day=True,
    )

    assert record.status == RunStatus.COMPLETED
    assert record.pre_reconciliation_status == "MATCHED"
    assert record.post_reconciliation_status == "MATCHED"
    assert record.orders_count == 6  # Top 3 Long, Bottom 3 Short
    assert record.fills_count == 6
    assert record.nav == pytest.approx(100_000.0, abs=200.0)
    assert record.transaction_costs > 0.0  # Commissions recorded

    # Verify report contents
    assert report.run_id == "run_p6_success_01"
    assert len(report.orders) == 6
    assert len(report.fills) == 6
    assert report.gross_exposure == pytest.approx(1.0, abs=1e-4)


def test_runner_idempotency_prevents_duplicate_orders(test_setup):
    """Executing runner.run_once() with the same run_id produces zero duplicate orders or fills."""
    db, broker, strategy, runner, df = test_setup
    window_df = df.iloc[:800]
    as_of_date = window_df.index[-1]

    # First Execution
    rec1, rep1 = runner.run_once(
        run_id="run_p6_idemp",
        as_of_date=as_of_date,
        market_data=window_df,
        is_rebalance_day=True,
    )
    assert rec1.status == RunStatus.COMPLETED
    initial_broker_orders = len(broker.get_all_orders())
    assert initial_broker_orders == 6

    # Second Execution with same run_id -> Idempotent Guard triggers
    rec2, rep2 = runner.run_once(
        run_id="run_p6_idemp",
        as_of_date=as_of_date,
        market_data=window_df,
        is_rebalance_day=True,
    )
    assert rec2.status == RunStatus.COMPLETED
    # Orders count in broker must NOT increase
    assert len(broker.get_all_orders()) == initial_broker_orders


def test_runner_failed_data_validation_blocks_orders(test_setup):
    """Corrupted data matrix (missing ticker) causes fail-closed abort with zero orders."""
    db, broker, strategy, runner, df = test_setup
    window_df = df.iloc[:800].drop(columns=["SPY"])  # Drop required SPY
    as_of_date = window_df.index[-1]

    initial_orders_count = len(broker.get_all_orders())

    record, report = runner.run_once(
        run_id="run_p6_data_fail",
        as_of_date=as_of_date,
        market_data=window_df,
        expected_universe=df.columns.tolist(),
        is_rebalance_day=True,
    )

    assert record.status == RunStatus.VALIDATION_FAILED
    assert "rejected market data" in record.error_message
    assert record.orders_count == 0
    assert len(broker.get_all_orders()) == initial_orders_count


def test_runner_failed_pre_reconciliation_halts_execution(test_setup):
    """Pre-execution reconciliation mismatch blocks execution immediately."""
    db, broker, strategy, runner, df = test_setup
    window_df = df.iloc[:800]
    as_of_date = window_df.index[-1]

    # Corrupt internal state vs broker before run
    inst_repo = InstrumentRepository(db)
    inst_repo.save_instrument(Instrument("SPY", AssetClass.EQUITY))
    holding_repo = HoldingRepository(db)
    holding_repo.save_holdings({"SPY": Holding("SPY", 100.0, 400.0, 400.0, 40000.0)})
    broker._holdings = {"SPY": Holding("SPY", 50.0, 400.0, 400.0, 20000.0)}

    initial_broker_orders = len(broker.get_all_orders())

    record, report = runner.run_once(
        run_id="run_p6_rec_fail",
        as_of_date=as_of_date,
        market_data=window_df,
        is_rebalance_day=True,
    )

    assert record.status == RunStatus.RECONCILIATION_FAILED
    assert record.pre_reconciliation_status == "MISMATCHED"
    assert record.orders_count == 0
    assert len(broker.get_all_orders()) == initial_broker_orders
