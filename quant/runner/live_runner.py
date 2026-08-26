"""Controlled live execution runner with mandatory human-in-the-loop approval."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pandas as pd

from ..broker.base import BrokerAdapter
from ..core.enums import AssetClass, ExecutionMode, OrderSide, OrderStatus
from ..core.exceptions import ModeViolationError, RiskViolationError
from ..core.interfaces import Instrument, OrderBatch, RiskDecision, TargetPortfolio
from ..data.base import AbstractMarketDataProvider
from ..data.validation import DataValidationGate
from ..observability.alerts import AlertDispatcher
from ..observability.logging import StructuredLogger
from ..oms.approval import ApprovalToken, ManualApprovalGate
from ..oms.engine import OrderManagementSystem
from ..oms.preview import OrderPreview, OrderPreviewBuilder
from ..oms.revalidation import PreSubmissionValidator
from ..persistence.database import DatabaseManager
from ..persistence.repositories import (
    FillRepository,
    HoldingRepository,
    InstrumentRepository,
    OrderRepository,
    RiskEvaluationRepository,
    RunRepository,
    SnapshotRepository,
    TargetPortfolioRepository,
)
from ..reconciliation.engine import ReconciliationEngine
from ..reconciliation.types import ReconciliationConfig
from ..risk.config import RiskConfig
from ..risk.engine import RiskEngine
from ..strategies.base import AbstractStrategy
from .ledger import PaperRunLedger
from .live_config import LiveExecutionConfig
from .models import DailyPaperReport, PaperRunRecord, RunStatus


class LiveTradingRunner:
    """Orchestrates controlled, human-approved execution against Interactive Brokers."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        broker: BrokerAdapter,
        strategy: AbstractStrategy,
        config: LiveExecutionConfig | None = None,
        data_provider: AbstractMarketDataProvider | None = None,
        risk_engine: RiskEngine | None = None,
        approval_gate: ManualApprovalGate | None = None,
        alert_dispatcher: AlertDispatcher | None = None,
        logger: StructuredLogger | None = None,
        reconciliation_config: ReconciliationConfig | None = None,
    ) -> None:
        self.db = db_manager
        self.broker = broker
        self.strategy = strategy
        self.config = config or LiveExecutionConfig()
        self.config.validate_safety_locks()

        self.data_provider = data_provider
        self.risk_engine = risk_engine or RiskEngine(RiskConfig(scale_gross_leverage=True))
        self.approval_gate = approval_gate or ManualApprovalGate(default_ttl_minutes=self.config.approval_ttl_minutes)
        self.alert_dispatcher = alert_dispatcher or AlertDispatcher()
        self.logger = logger or StructuredLogger("LiveTradingRunner")
        self.rec_config = reconciliation_config or ReconciliationConfig()
        self.ledger = PaperRunLedger(db_manager)

        # Repositories
        self.run_repo = RunRepository(db_manager)
        self.inst_repo = InstrumentRepository(db_manager)
        self.tp_repo = TargetPortfolioRepository(db_manager)
        self.risk_repo = RiskEvaluationRepository(db_manager)
        self.order_repo = OrderRepository(db_manager)
        self.fill_repo = FillRepository(db_manager)
        self.holding_repo = HoldingRepository(db_manager)
        self.snap_repo = SnapshotRepository(db_manager)

    def prepare_order_preview(
        self,
        run_id: str,
        as_of_date: pd.Timestamp | datetime,
        market_data: pd.DataFrame | None = None,
        expected_universe: list[str] | None = None,
        is_rebalance_day: bool = True,
    ) -> tuple[OrderBatch, TargetPortfolio, RiskDecision, OrderPreview, dict[str, float]]:
        """Executes operational steps 1-9 and renders an immutable OrderPreview for human review."""
        now = datetime.now(timezone.utc)
        strat_id = getattr(self.strategy, "strategy_id", "live_macro_v1")
        exec_mode = ExecutionMode.LIVE if self.config.broker_env == "LIVE" else ExecutionMode.PAPER

        # Ensure system run record exists in persistence
        if not self.run_repo.run_exists(run_id):
            self.run_repo.create_run(run_id, exec_mode, strat_id)

        # 1. Health Verification
        broker_health = self.broker.health_check()
        if broker_health != "CONNECTED":
            raise ModeViolationError(f"Broker health check failed: status={broker_health!r}.")

        # 2. Pre-Reconciliation
        latest_snap = self.snap_repo.get_latest_snapshot()
        if latest_snap is None:
            init_account = self.broker.get_account_state()
            self.snap_repo.save_snapshot("snap_init_live", run_id, init_account, exec_mode, strat_id)

        rec_res = ReconciliationEngine.reconcile(run_id, exec_mode, self.db, self.broker, self.rec_config)
        if not rec_res.passed:
            raise ModeViolationError(f"Pre-execution reconciliation failed: {[i.message for i in rec_res.issues]}")

        # 3. Market Data Ingestion & Validation
        df = market_data
        if df is None and self.data_provider is not None:
            univ = expected_universe or list(self.config.instrument_whitelist)
            df = self.data_provider.fetch_daily_bars(univ, lookback_bars=756, as_of_date=as_of_date)

        universe = expected_universe or getattr(self.strategy, "universe", list(df.columns) if df is not None else list(self.config.instrument_whitelist))
        DataValidationGate.validate_matrix(df, universe, mode=exec_mode)

        # 4. Mark-to-Market & Positions
        last_row = df.iloc[-1]
        prices = {sym: float(last_row[sym]) for sym in universe if sym in last_row}
        for sym in universe:
            self.inst_repo.save_instrument(Instrument(symbol=sym, asset_class=AssetClass.EQUITY))

        account_state = self.broker.get_account_state(current_prices=prices)

        # 5. Strategy Target Generation
        tp_id = f"tp_{uuid.uuid4().hex[:12]}"
        if is_rebalance_day:
            target_portfolio = self.strategy.generate_target_portfolio(df, as_of_date=as_of_date)
        else:
            target_portfolio = TargetPortfolio(now, strat_id, account_state.realized_weights, 21, metadata={"drift_day": True})

        self.tp_repo.save_target_portfolio(tp_id, target_portfolio, run_id=run_id)

        # 6. Pre-Trade Risk Authority
        dec_id = f"dec_{uuid.uuid4().hex[:12]}"
        risk_decision = self.risk_engine.evaluate(
            target_portfolio=target_portfolio,
            portfolio_state=account_state,
            current_prices=prices,
            portfolio_id=tp_id,
            decision_id=dec_id,
        )
        self.risk_repo.save_risk_evaluation(risk_decision)
        if not risk_decision.approved:
            raise RiskViolationError(f"Pre-trade RiskEngine rejected TargetPortfolio: {risk_decision.violations}")

        # 7. OMS Order Batch Generation
        batch_id = f"batch_{uuid.uuid4().hex[:12]}"
        order_batch = OrderManagementSystem.generate_order_batch(
            current_holdings=self.broker.get_positions(),
            target_portfolio=target_portfolio,
            current_prices=prices,
            nav=account_state.nav,
            run_id=run_id,
            execution_mode=exec_mode,
            batch_id=batch_id,
            target_portfolio_id=tp_id,
            risk_decision=risk_decision,
            require_risk_approval=True,
        )

        # 8. Order Preview Building
        preview = OrderPreviewBuilder.build(
            order_batch=order_batch,
            target_portfolio=target_portfolio,
            risk_decision=risk_decision,
            current_holdings=self.broker.get_positions(),
            current_prices=prices,
            cash=account_state.cash,
            broker_constraints={"buying_power": self.broker.get_buying_power()},
        )

        return order_batch, target_portfolio, risk_decision, preview, prices

    def execute_approved_batch(
        self,
        run_id: str,
        order_batch: OrderBatch,
        target_portfolio: TargetPortfolio,
        risk_decision: RiskDecision,
        approval_token: ApprovalToken,
        current_prices: dict[str, float],
    ) -> tuple[PaperRunRecord, DailyPaperReport]:
        """Executes operational steps 10-15: approval verification, pre-submission revalidation, broker dispatch, fills, and reconciliation."""
        now = datetime.now(timezone.utc)
        strat_id = order_batch.strategy_id
        exec_mode = ExecutionMode.LIVE if self.config.broker_env == "LIVE" else ExecutionMode.PAPER

        record = PaperRunRecord(
            run_id=run_id,
            execution_mode=exec_mode,
            strategy_id=strat_id,
            start_time=now,
            target_portfolio_id=target_portfolio.metadata.get("target_portfolio_id", order_batch.target_portfolio_id),
            risk_decision_id=risk_decision.decision_id,
            order_batch_id=order_batch.batch_id,
            status=RunStatus.STARTED,
        )
        if not self.run_repo.run_exists(run_id):
            self.run_repo.create_run(run_id, exec_mode, strat_id)

        # 10. Human Approval Gate Verification
        approved_batch = self.approval_gate.approve_batch(order_batch, approval_token)

        # 11. Pre-Submission Revalidation Gate
        reval_result = PreSubmissionValidator.validate(
            order_batch=approved_batch,
            target_portfolio=target_portfolio,
            broker=self.broker,
            db_manager=self.db,
            approval_token=approval_token,
            risk_engine=self.risk_engine,
            current_prices=current_prices,
            instrument_whitelist=list(self.config.instrument_whitelist),
            allowed_order_types=list(self.config.allowed_order_types),
            live_capital_limit=self.config.live_capital_limit,
            emergency_stop_active=self.config.emergency_stop_active,
            execution_mode=exec_mode,
        )
        if not reval_result.passed:
            record.status = RunStatus.RISK_REJECTED
            record.error_message = f"Pre-submission revalidation failed: {reval_result.errors}"
            self.ledger.record_run(record)
            return record, DailyPaperReport(
                run_id=run_id,
                date_iso=str(now.date()),
                strategy_id=strat_id,
                nav=0.0,
                cash=0.0,
                gross_exposure=0.0,
                net_exposure=0.0,
                final_run_status=RunStatus.RISK_REJECTED,
            )

        # Persist approved orders to SQLite
        for o in approved_batch.orders:
            self.order_repo.save_order(o, execution_mode=exec_mode, client_order_id=o.client_order_id)

        # 12. Dispatch Orders to Broker Adapter
        record.orders_count = len(approved_batch.orders)
        for o in approved_batch.orders:
            self.broker.submit_order(o, price_lookup=current_prices)

        # 13. Monitor & Ingest Fills from Broker
        fills = self.broker.get_fills()
        total_costs = 0.0
        for f in fills:
            self.fill_repo.save_fill(f, broker_execution_id=f.fill_id)
            total_costs += f.commission

        record.fills_count = len(fills)
        record.transaction_costs = total_costs

        # Update order statuses in SQLite
        for o in approved_batch.orders:
            self.order_repo.update_order_status(o.order_id, OrderStatus.FILLED)

        # 14. Persist Updated Holdings & Portfolio Snapshot
        holdings = self.broker.get_positions()
        self.holding_repo.save_holdings(holdings)
        account_state = self.broker.get_account_state(current_prices=current_prices)
        record.nav = account_state.nav
        record.cash = account_state.cash

        active_weights = risk_decision.adjusted_weights or target_portfolio.target_weights
        record.gross_exposure = sum(abs(w) for w in active_weights.values())
        record.net_exposure = sum(w for w in active_weights.values())

        snap_id = f"snap_{uuid.uuid4().hex[:12]}"
        self.snap_repo.save_snapshot(snap_id, run_id, account_state, exec_mode, strat_id)

        # 15. Post-Execution Reconciliation
        post_rec = ReconciliationEngine.reconcile(run_id, exec_mode, self.db, self.broker, self.rec_config)
        record.pre_reconciliation_status = "MATCHED"
        record.post_reconciliation_status = post_rec.status.value

        if post_rec.passed:
            record.status = RunStatus.COMPLETED
        else:
            record.status = RunStatus.RECOVERY_REQUIRED
            record.error_message = f"Post-execution reconciliation failed: {[i.message for i in post_rec.issues]}"

        record.end_time = datetime.now(timezone.utc)
        self.ledger.record_run(record)

        report = DailyPaperReport(
            run_id=run_id,
            date_iso=str(now.date()),
            strategy_id=strat_id,
            nav=account_state.nav,
            cash=account_state.cash,
            gross_exposure=record.gross_exposure,
            net_exposure=record.net_exposure,
            orders=[{"symbol": o.symbol, "side": o.side.value, "quantity": o.quantity} for o in approved_batch.orders],
            fills=[{"symbol": f.symbol, "side": f.side.value, "quantity": f.quantity, "price": f.fill_price} for f in fills],
            transaction_costs=total_costs,
            borrow_costs=0.0,
            risk_decision=risk_decision.metadata,
            pre_reconciliation_status=record.pre_reconciliation_status,
            post_reconciliation_status=record.post_reconciliation_status,
            target_weights=dict(active_weights),
            actual_holdings={sym: h.shares for sym, h in holdings.items()},
            weight_drift={sym: account_state.realized_weights.get(sym, 0.0) - active_weights.get(sym, 0.0) for sym in active_weights},
            executed_changes={o.symbol: (o.quantity if o.side == OrderSide.BUY else -o.quantity) for o in approved_batch.orders},
            final_run_status=record.status,
        )
        return record, report
