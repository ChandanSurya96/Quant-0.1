"""Tests for the accelerated 30-day continuous paper trading validation harness."""

from __future__ import annotations

from pathlib import Path
import pandas as pd
import pytest

from quant.broker.paper_broker import PaperBroker
from quant.persistence.database import DatabaseManager
from quant.runner.harness import Deterministic30DayHarness
from quant.runner.models import RunStatus
from quant.runner.runner import PaperTradingRunner
from quant.strategies.macro import SystematicMacroStrategy


@pytest.fixture
def harness_setup(tmp_path: Path):
    db_file = tmp_path / "test_30day.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    broker = PaperBroker(initial_cash=100_000.0)
    strategy = SystematicMacroStrategy(rebalance_cadence_days=21)
    runner = PaperTradingRunner(db_manager=db, broker=broker, strategy=strategy)
    harness = Deterministic30DayHarness(runner=runner, rebalance_cadence_days=21)

    df = pd.read_csv("tests/fixtures/synthetic_macro_12etf.csv", index_col=0, parse_dates=True)
    return db, broker, strategy, harness, df


def test_deterministic_30day_harness_runs_to_completion(harness_setup):
    """Executes 30 consecutive daily paper runs with zero unexplained state changes."""
    db, broker, strategy, harness, df = harness_setup

    results, summary = harness.run_validation(
        daily_prices_df=df,
        lookback_bars=756,
        total_days=30,
    )

    assert len(results) == 30
    assert summary.total_runs == 30
    assert summary.successful_runs == 30
    assert summary.failed_runs == 0
    assert summary.reconciliation_failures == 0
    assert summary.risk_rejections == 0
    assert summary.data_failures == 0

    # Verify that every run was marked COMPLETED with 100% matched reconciliation
    for day_num, (record, report) in enumerate(results, start=1):
        assert record.status == RunStatus.COMPLETED
        assert record.pre_reconciliation_status == "MATCHED"
        assert record.post_reconciliation_status == "MATCHED"
        assert report.final_run_status == RunStatus.COMPLETED

        # Check rebalance schedule vs drift days
        if day_num in (1, 22):  # Scheduled rebalance days
            assert record.orders_count in (6, 7)
            assert record.fills_count == record.orders_count
        else:  # Intra-month weight drift days (ZERO trades)
            assert record.orders_count == 0
            assert record.fills_count == 0

    # Verify cumulative accounting integrity
    assert summary.cumulative_transaction_costs > 0.0
    assert summary.initial_nav > 0.0
    assert summary.final_nav > 0.0
    assert len(summary.nav_path) == 30
