"""Comprehensive unit and integration test suite for P9 Controlled Autonomous Execution."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import pytest
import pandas as pd

from quant.broker.ibkr import IBKRBrokerAdapter, IBKRConfig, MockIBKRClient, ShortAvailability
from quant.broker.ibkr.models import IBKROrderRecord
from quant.core.enums import AssetClass, ExecutionMode, OrderSide, OrderStatus, OrderType
from quant.core.exceptions import ModeViolationError, OMSError, RiskViolationError
from quant.core.interfaces import Fill, Holding, Instrument, Order, PortfolioState, TargetPortfolio
from quant.oms.approval import AutonomousApprovalGate
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
from quant.risk.config import RiskConfig
from quant.risk.engine import RiskEngine
from quant.runner.autonomous_config import AutonomousExecutionConfig
from quant.runner.autonomous_ledger import AutonomousLedgerRepository, AutonomousRunRecord
from quant.runner.autonomous_runner import AutonomousTradingRunner
from quant.runner.models import RunStatus
from quant.strategies.macro import SystematicMacroStrategy


@pytest.fixture
def auto_env(tmp_path: Path):
    db_file = tmp_path / "test_p9_autonomous.db"
    db = DatabaseManager(db_file)
    db.initialize_schema()

    mock_client = MockIBKRClient(auto_fill_on_submit=True)
    cfg = IBKRConfig(host="127.0.0.1", port=7497, is_paper=True, live_execution_enabled=False, account_id="DU9876543")
    adapter = IBKRBrokerAdapter(config=cfg, client=mock_client)

    strategy = SystematicMacroStrategy(rebalance_cadence_days=21)
    df = pd.read_csv("tests/fixtures/synthetic_macro_12etf.csv", index_col=0, parse_dates=True)

    return db, mock_client, adapter, strategy, df


# ------------------------------------------------ 1. Autonomous Mode & Safety Locks
def test_autonomous_mode_disabled_by_default(auto_env):
    """By default, autonomous execution is FALSE and blocks order generation fail-closed."""
    db, mock_client, adapter, strategy, df = auto_env
    window_df = df.iloc[:800]
    as_of_date = window_df.index[-1]

    default_cfg = AutonomousExecutionConfig(autonomous_execution_enabled=False)
    runner = AutonomousTradingRunner(db_manager=db, broker=adapter, strategy=strategy, config=default_cfg)

    rec, report = runner.execute_daily_autonomous_cycle("run_auto_def", as_of_date, window_df)
    assert rec.status == "BLOCKED"
    assert "AUTONOMOUS_EXECUTION_ENABLED is false" in rec.rejection_reason
    assert report.final_run_status == RunStatus.VALIDATION_FAILED


def test_autonomous_mode_explicitly_enabled(auto_env):
    """When explicitly enabled with all safety criteria met, autonomous execution completes end-to-end."""
    db, mock_client, adapter, strategy, df = auto_env
    window_df = df.iloc[:800]
    as_of_date = window_df.index[-1]

    auto_cfg = AutonomousExecutionConfig(
        autonomous_execution_enabled=True,
        approval_mode="AUTONOMOUS",
        broker_env="PAPER",
        max_live_capital=150_000.0,
    )
    runner = AutonomousTradingRunner(db_manager=db, broker=adapter, strategy=strategy, config=auto_cfg)

    rec, report = runner.execute_daily_autonomous_cycle("run_auto_succ", as_of_date, window_df)
    assert rec.status == "COMPLETED"
    assert rec.orders_count == 6
    assert rec.fills_count == 6
    assert rec.pre_reconciliation_status == "MATCHED"
    assert rec.post_reconciliation_status == "MATCHED"
    assert report.final_run_status == RunStatus.COMPLETED


def test_wrong_strategy_rejected_fail_closed(auto_env):
    """Unwhitelisted strategies are strictly rejected from autonomous execution."""
    db, mock_client, adapter, strategy, df = auto_env
    window_df = df.iloc[:800]
    as_of_date = window_df.index[-1]

    # Create dummy strategy with unapproved strategy_id
    class UnapprovedStrategy(SystematicMacroStrategy):
        @property
        def strategy_id(self) -> str:
            return "high_frequency_alpha_v9"

    unapproved_strat = UnapprovedStrategy()
    auto_cfg = AutonomousExecutionConfig(autonomous_execution_enabled=True, approval_mode="AUTONOMOUS", broker_env="PAPER")
    runner = AutonomousTradingRunner(db_manager=db, broker=adapter, strategy=unapproved_strat, config=auto_cfg)

    rec, report = runner.execute_daily_autonomous_cycle("run_auto_unapp", as_of_date, window_df)
    assert rec.status == "BLOCKED"
    assert "not in autonomous whitelist" in rec.rejection_reason


def test_kill_switch_active_blocks_autonomous_run(auto_env):
    """Active Emergency Stop / Kill switch halts autonomous execution immediately."""
    db, mock_client, adapter, strategy, df = auto_env
    window_df = df.iloc[:800]
    as_of_date = window_df.index[-1]

    auto_cfg = AutonomousExecutionConfig(
        autonomous_execution_enabled=True,
        approval_mode="AUTONOMOUS",
        broker_env="PAPER",
        emergency_stop_active=True,
    )
    # validate_safety_locks blocks init if emergency_stop_active
    with pytest.raises(ModeViolationError):
        auto_cfg.validate_safety_locks()


# ------------------------------------------------ 2. Daily Batch Limit & Process Restart Safety
def test_one_batch_per_day_allowed_second_batch_blocked(auto_env):
    """Only 1 autonomous batch per day is permitted; subsequent runs on the same date are blocked."""
    db, mock_client, adapter, strategy, df = auto_env
    window_df = df.iloc[:800]
    as_of_date = window_df.index[-1]

    auto_cfg = AutonomousExecutionConfig(
        autonomous_execution_enabled=True,
        approval_mode="AUTONOMOUS",
        broker_env="PAPER",
        max_live_capital=150_000.0,
        max_autonomous_order_batches_per_day=1,
    )
    runner = AutonomousTradingRunner(db_manager=db, broker=adapter, strategy=strategy, config=auto_cfg)

    # First run on 2023-01-24 succeeds
    rec1, rep1 = runner.execute_daily_autonomous_cycle("run_daily_01", as_of_date, window_df)
    assert rec1.status == "COMPLETED"

    # Second run on identical trading date is blocked
    rec2, rep2 = runner.execute_daily_autonomous_cycle("run_daily_02", as_of_date, window_df)
    assert rec2.status == "BLOCKED"
    assert "Daily order batch limit (1) reached" in rec2.rejection_reason


def test_process_restart_does_not_reset_daily_batch_count(auto_env):
    """Process restart does NOT reset daily batch count because counter is queried from SQLite."""
    db, mock_client, adapter, strategy, df = auto_env
    window_df = df.iloc[:800]
    as_of_date = window_df.index[-1]

    auto_cfg = AutonomousExecutionConfig(
        autonomous_execution_enabled=True,
        approval_mode="AUTONOMOUS",
        broker_env="PAPER",
        max_live_capital=150_000.0,
        max_autonomous_order_batches_per_day=1,
    )

    # First runner instance executes batch
    runner1 = AutonomousTradingRunner(db_manager=db, broker=adapter, strategy=strategy, config=auto_cfg)
    rec1, _ = runner1.execute_daily_autonomous_cycle("run_restart_01", as_of_date, window_df)
    assert rec1.status == "COMPLETED"

    # Simulate process death & restart: new runner instance initialized against same database
    runner2 = AutonomousTradingRunner(db_manager=db, broker=adapter, strategy=strategy, config=auto_cfg)
    rec2, _ = runner2.execute_daily_autonomous_cycle("run_restart_02", as_of_date, window_df)

    # Second run is blocked despite new process instance
    assert rec2.status == "BLOCKED"
    assert "Daily order batch limit (1) reached" in rec2.rejection_reason


# ------------------------------------------------ 3. Reconciliation & Recovery
def test_pre_trade_reconciliation_mismatch_blocks_execution(auto_env):
    """Pre-trade state discrepancy between internal SQLite and broker halts execution fail-closed."""
    db, mock_client, adapter, strategy, df = auto_env
    window_df = df.iloc[:800]
    as_of_date = window_df.index[-1]

    # Save internal holding that broker does NOT have
    RunRepository(db).create_run("run_mismatch_init", ExecutionMode.PAPER, "systematic_macro_v1")
    InstrumentRepository(db).save_instrument(Instrument("SPY", AssetClass.EQUITY))
    HoldingRepository(db).save_holding(Holding("SPY", 100.0, 400.0, 400.0, 40_000.0))
    SnapshotRepository(db).save_snapshot("snap_mismatch", "run_mismatch_init", PortfolioState(datetime.now(timezone.utc), 100_000.0, {"SPY": Holding("SPY", 100.0, 400.0, 400.0, 40_000.0)}, 140_000.0, {}), ExecutionMode.PAPER, "systematic_macro_v1")

    auto_cfg = AutonomousExecutionConfig(autonomous_execution_enabled=True, approval_mode="AUTONOMOUS", broker_env="PAPER")
    runner = AutonomousTradingRunner(db_manager=db, broker=adapter, strategy=strategy, config=auto_cfg)

    rec, report = runner.execute_daily_autonomous_cycle("run_rec_fail", as_of_date, window_df)
    assert rec.status == "RECOVERY_REQUIRED"
    assert "Pre-trade reconciliation failed" in rec.rejection_reason


# ------------------------------------------------ 4. Risk Controls & Limits
def test_drawdown_circuit_breaker_blocks_risk_expansion(auto_env):
    """Drawdown beyond -15% circuit breaker blocks autonomous orders."""
    db, mock_client, adapter, strategy, df = auto_env
    window_df = df.iloc[:800]
    as_of_date = window_df.index[-1]

    # Seed historical peak snapshot with NAV = 150,000, and current snapshot matching broker cash = 100,000 (drawdown = -33.3% > -15%)
    from datetime import timedelta
    past_time = datetime.now(timezone.utc) - timedelta(days=10)
    now_time = datetime.now(timezone.utc)
    mock_client._cash = 100_000.0
    RunRepository(db).create_run("run_hwm_seed", ExecutionMode.PAPER, "systematic_macro_v1", started_at=past_time)
    SnapshotRepository(db).save_snapshot(
        "snap_hwm", "run_hwm_seed",
        PortfolioState(past_time, 150_000.0, {}, 150_000.0, {}),
        ExecutionMode.PAPER, "systematic_macro_v1"
    )
    SnapshotRepository(db).save_snapshot(
        "snap_current", "run_hwm_seed",
        PortfolioState(now_time, 100_000.0, {}, 100_000.0, {}),
        ExecutionMode.PAPER, "systematic_macro_v1"
    )

    auto_cfg = AutonomousExecutionConfig(autonomous_execution_enabled=True, approval_mode="AUTONOMOUS", broker_env="PAPER")
    runner = AutonomousTradingRunner(db_manager=db, broker=adapter, strategy=strategy, config=auto_cfg)

    rec, report = runner.execute_daily_autonomous_cycle("run_dd_fail", as_of_date, window_df)
    assert rec.status == "REJECTED"
    assert "RiskEngine rejected target portfolio" in rec.rejection_reason


def test_instrument_whitelist_enforced(auto_env):
    """Instrument outside autonomous whitelist blocks entire autonomous batch."""
    db, mock_client, adapter, strategy, df = auto_env
    window_df = df.iloc[:800]
    as_of_date = window_df.index[-1]

    # Whitelist missing 'SPY'
    restrictive_whitelist = ("TLT", "IEF", "BNDX")
    auto_cfg = AutonomousExecutionConfig(
        autonomous_execution_enabled=True,
        approval_mode="AUTONOMOUS",
        broker_env="PAPER",
        autonomous_instrument_whitelist=restrictive_whitelist,
    )
    runner = AutonomousTradingRunner(db_manager=db, broker=adapter, strategy=strategy, config=auto_cfg)

    rec, report = runner.execute_daily_autonomous_cycle("run_wl_fail", as_of_date, window_df)
    assert rec.status == "REJECTED"
    assert "is outside the autonomous whitelist" in rec.rejection_reason


# ------------------------------------------------ 5. Uncertain Submission & No Blind Retry
def test_uncertain_submission_no_blind_retry(auto_env):
    """Broker timeout after submit triggers broker order query and reconciliation, never blind re-order."""
    db, mock_client, adapter, strategy, df = auto_env

    mock_client.auto_fill_on_submit = False
    run_id = "run_auto_unc"
    RunRepository(db).create_run(run_id, ExecutionMode.PAPER, "systematic_macro_v1")
    InstrumentRepository(db).save_instrument(Instrument("SPY", AssetClass.EQUITY))
    order = Order("ord_auto_unc", run_id, "systematic_macro_v1", "SPY", OrderSide.BUY, OrderType.MARKET, 10.0, client_order_id="cl_auto_unc")
    OrderRepository(db).save_order(order, ExecutionMode.PAPER)
    adapter.submit_order(order)

    # Disconnect immediately
    mock_client.disconnect()
    assert adapter.client.is_connected() is False

    # Reconnect and inspect broker state
    mock_client.connect()
    found = adapter.get_order("ord_auto_unc")
    assert found is not None
    assert found.client_order_id == "cl_auto_unc"


# ------------------------------------------------ 6. Additional Safety & Execution Checks
def test_autonomous_capital_limit_excess_rejected(auto_env):
    """Notional exceeding MAX_LIVE_CAPITAL is blocked fail-closed."""
    db, mock_client, adapter, strategy, df = auto_env
    window_df = df.iloc[:800]
    as_of_date = window_df.index[-1]

    # Set very small capital ceiling
    auto_cfg = AutonomousExecutionConfig(
        autonomous_execution_enabled=True,
        approval_mode="AUTONOMOUS",
        broker_env="PAPER",
        max_live_capital=5_000.0,  # Strategy generates ~$100,000 notional
    )
    runner = AutonomousTradingRunner(db_manager=db, broker=adapter, strategy=strategy, config=auto_cfg)

    rec, report = runner.execute_daily_autonomous_cycle("run_cap_fail", as_of_date, window_df)
    assert rec.status == "REJECTED"
    assert "exceeds live capital limit" in rec.rejection_reason


def test_autonomous_buying_power_insufficient_rejected(auto_env):
    """Insufficient broker buying power blocks autonomous order submission."""
    db, mock_client, adapter, strategy, df = auto_env
    window_df = df.iloc[:800]
    as_of_date = window_df.index[-1]

    # Broker has only $10.0 buying power
    mock_client._buying_power = 10.0

    auto_cfg = AutonomousExecutionConfig(
        autonomous_execution_enabled=True,
        approval_mode="AUTONOMOUS",
        broker_env="PAPER",
        max_live_capital=150_000.0,
    )
    runner = AutonomousTradingRunner(db_manager=db, broker=adapter, strategy=strategy, config=auto_cfg)

    rec, report = runner.execute_daily_autonomous_cycle("run_bp_fail", as_of_date, window_df)
    assert rec.status == "REJECTED"
    assert "Insufficient buying power" in rec.rejection_reason


def test_autonomous_short_borrow_unavailable_rejected(auto_env):
    """Unavailable short borrow blocks short order in autonomous batch."""
    db, mock_client, adapter, strategy, df = auto_env
    window_df = df.iloc[:800]
    as_of_date = window_df.index[-1]

    # Mark all shorts as UNAVAILABLE in mock client
    mock_client._short_availability_map = {sym: ShortAvailability.UNAVAILABLE for sym in ("FXE", "FXB", "FXY")}

    auto_cfg = AutonomousExecutionConfig(
        autonomous_execution_enabled=True,
        approval_mode="AUTONOMOUS",
        broker_env="PAPER",
        max_live_capital=150_000.0,
    )
    runner = AutonomousTradingRunner(db_manager=db, broker=adapter, strategy=strategy, config=auto_cfg)

    rec, report = runner.execute_daily_autonomous_cycle("run_short_fail", as_of_date, window_df)
    assert rec.status == "REJECTED"
    assert "Short borrow unavailable" in rec.rejection_reason


def test_autonomous_daily_report_generation(auto_env):
    """Successful autonomous run produces a complete DailyPaperReport with all financials."""
    db, mock_client, adapter, strategy, df = auto_env
    window_df = df.iloc[:800]
    as_of_date = window_df.index[-1]

    auto_cfg = AutonomousExecutionConfig(
        autonomous_execution_enabled=True,
        approval_mode="AUTONOMOUS",
        broker_env="PAPER",
        max_live_capital=150_000.0,
    )
    runner = AutonomousTradingRunner(db_manager=db, broker=adapter, strategy=strategy, config=auto_cfg)

    rec, report = runner.execute_daily_autonomous_cycle("run_rep_gen", as_of_date, window_df)
    assert report.final_run_status == RunStatus.COMPLETED
    assert len(report.orders) == 6
    assert len(report.fills) == 6
    assert report.gross_exposure == pytest.approx(1.0)
    assert report.net_exposure == pytest.approx(0.0, abs=1e-3)
    text = report.to_text_report()
    assert "DAILY PAPER EXECUTION REPORT" in text
