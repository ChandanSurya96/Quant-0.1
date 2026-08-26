"""Controlled Autonomous Execution Orchestrator (P9)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pandas as pd

from ..broker.base import BrokerAdapter
from ..core.enums import AssetClass, ExecutionMode, OrderSide, OrderStatus
from ..core.interfaces import Instrument
from ..data.validation import DataValidationGate
from ..observability.alerts import AlertDispatcher
from ..observability.logging import StructuredLogger
from ..oms.approval import AutonomousApprovalGate
from ..oms.engine import OrderManagementSystem
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
from .autonomous_config import AutonomousExecutionConfig
from .autonomous_ledger import AutonomousLedgerRepository, AutonomousRunRecord
from .models import DailyPaperReport, RunStatus


class AutonomousTradingRunner:
    """Orchestrates the 14-point controlled autonomous execution cycle under strict P9 safety policy."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        broker: BrokerAdapter,
        strategy: AbstractStrategy,
        config: AutonomousExecutionConfig | None = None,
        risk_engine: RiskEngine | None = None,
        autonomous_gate: AutonomousApprovalGate | None = None,
        alert_dispatcher: AlertDispatcher | None = None,
        logger: StructuredLogger | None = None,
        reconciliation_config: ReconciliationConfig | None = None,
    ) -> None:
        self.db = db_manager
        self.broker = broker
        self.strategy = strategy
        self.config = config or AutonomousExecutionConfig(
            autonomous_execution_enabled=False,
            approval_mode="MANUAL_APPROVAL",
            broker_env="PAPER",
        )
        self.config.validate_safety_locks()

        self.risk_engine = risk_engine or RiskEngine(RiskConfig(scale_gross_leverage=True))
        self.autonomous_gate = autonomous_gate or AutonomousApprovalGate(
            autonomous_execution_enabled=self.config.autonomous_execution_enabled,
            strategy_whitelist=self.config.autonomous_strategy_whitelist,
            emergency_stop_active=self.config.emergency_stop_active,
        )
        self.alert_dispatcher = alert_dispatcher or AlertDispatcher()
        self.logger = logger or StructuredLogger("AutonomousTradingRunner")
        self.rec_config = reconciliation_config or ReconciliationConfig()
        self.ledger_repo = AutonomousLedgerRepository(db_manager)

        # Persistence repositories
        self.run_repo = RunRepository(db_manager)
        self.inst_repo = InstrumentRepository(db_manager)
        self.tp_repo = TargetPortfolioRepository(db_manager)
        self.risk_repo = RiskEvaluationRepository(db_manager)
        self.order_repo = OrderRepository(db_manager)
        self.fill_repo = FillRepository(db_manager)
        self.holding_repo = HoldingRepository(db_manager)
        self.snap_repo = SnapshotRepository(db_manager)

    def execute_daily_autonomous_cycle(
        self,
        run_id: str,
        as_of_date: pd.Timestamp | datetime,
        market_data: pd.DataFrame,
        expected_universe: list[str] | None = None,
        is_rebalance_day: bool = True,
    ) -> tuple[AutonomousRunRecord, DailyPaperReport]:
        """Executes the full 14-point controlled autonomous execution sequence."""
        now = datetime.now(timezone.utc)
        strat_id = getattr(self.strategy, "strategy_id", "systematic_macro_v1")
        trading_date = str(as_of_date.date() if hasattr(as_of_date, "date") else as_of_date)[:10]
        exec_mode = ExecutionMode.LIVE if self.config.broker_env == "LIVE" else ExecutionMode.PAPER

        # Record system run
        if not self.run_repo.run_exists(run_id):
            self.run_repo.create_run(run_id, exec_mode, strat_id)

        self.logger.info("AUTONOMOUS_RUN_STARTED", run_id=run_id, strategy_id=strat_id, trading_date=trading_date)

        # 1. Multi-Condition Autonomy Authorization Check
        if not self.config.autonomous_execution_enabled:
            reason = "AUTONOMOUS_EXECUTION_ENABLED is false. Autonomous execution is disabled."
            self.logger.warning("AUTONOMOUS_RUN_BLOCKED", run_id=run_id, reason=reason)
            rec = AutonomousRunRecord(
                run_id=run_id, trading_date=trading_date, strategy_id=strat_id,
                timestamp=now, status="BLOCKED", rejection_reason=reason,
            )
            self.ledger_repo.record_run(rec)
            self.run_repo.complete_run(run_id, "FAILED", error_message=reason)
            return rec, self._build_blocked_report(run_id, trading_date, strat_id, reason)

        if self.config.emergency_stop_active:
            reason = "EMERGENCY_STOP is active. Kill switch halts all autonomous execution."
            self.logger.critical("KILL_SWITCH_ACTIVATED", run_id=run_id, reason=reason)
            rec = AutonomousRunRecord(
                run_id=run_id, trading_date=trading_date, strategy_id=strat_id,
                timestamp=now, status="BLOCKED", rejection_reason=reason,
            )
            self.ledger_repo.record_run(rec)
            self.run_repo.complete_run(run_id, "FAILED", error_message=reason)
            return rec, self._build_blocked_report(run_id, trading_date, strat_id, reason)

        if strat_id not in self.config.autonomous_strategy_whitelist:
            reason = f"Strategy {strat_id!r} is not in autonomous whitelist {self.config.autonomous_strategy_whitelist}."
            self.logger.error("AUTONOMOUS_RUN_BLOCKED", run_id=run_id, reason=reason)
            rec = AutonomousRunRecord(
                run_id=run_id, trading_date=trading_date, strategy_id=strat_id,
                timestamp=now, status="BLOCKED", rejection_reason=reason,
            )
            self.ledger_repo.record_run(rec)
            self.run_repo.complete_run(run_id, "FAILED", error_message=reason)
            return rec, self._build_blocked_report(run_id, trading_date, strat_id, reason)

        # 2. Persistent Daily Order-Batch Limit Gate
        daily_count = self.ledger_repo.get_daily_batch_count(trading_date)
        if daily_count >= self.config.max_autonomous_order_batches_per_day:
            reason = (
                f"Daily order batch limit ({self.config.max_autonomous_order_batches_per_day}) reached "
                f"for trading date {trading_date}. Existing batches today = {daily_count}."
            )
            self.logger.warning("AUTONOMOUS_RUN_BLOCKED", run_id=run_id, reason=reason)
            rec = AutonomousRunRecord(
                run_id=run_id, trading_date=trading_date, strategy_id=strat_id,
                timestamp=now, status="BLOCKED", rejection_reason=reason,
            )
            self.ledger_repo.record_run(rec)
            self.run_repo.complete_run(run_id, "FAILED", error_message=reason)
            return rec, self._build_blocked_report(run_id, trading_date, strat_id, reason)

        # 3. Market Data Health & Validation Gate
        try:
            clean_df = DataValidationGate.validate_matrix(market_data, universe=expected_universe, mode=exec_mode)
        except Exception as e:
            reason = f"Market data validation failed: {e}"
            self.logger.error("DATA_FAILURE", run_id=run_id, error=str(e))
            rec = AutonomousRunRecord(
                run_id=run_id, trading_date=trading_date, strategy_id=strat_id,
                timestamp=now, status="REJECTED", rejection_reason=reason,
            )
            self.ledger_repo.record_run(rec)
            self.run_repo.complete_run(run_id, "FAILED", error_message=reason)
            return rec, self._build_blocked_report(run_id, trading_date, strat_id, reason)

        self.logger.info("DATA_VALIDATED", run_id=run_id, date=trading_date)

        # 4. Broker Health Gate
        broker_health = self.broker.health_check()
        if broker_health != "CONNECTED":
            reason = f"Broker health check failed: {broker_health!r}."
            self.logger.error("BROKER_FAILURE", run_id=run_id, status=broker_health)
            rec = AutonomousRunRecord(
                run_id=run_id, trading_date=trading_date, strategy_id=strat_id,
                timestamp=now, status="BLOCKED", rejection_reason=reason,
            )
            self.ledger_repo.record_run(rec)
            self.run_repo.complete_run(run_id, "FAILED", error_message=reason)
            return rec, self._build_blocked_report(run_id, trading_date, strat_id, reason)

        # Extract current prices
        current_prices = clean_df.iloc[-1].to_dict()

        # Bootstrap initial snapshot if database is empty
        if self.snap_repo.get_latest_snapshot() is None:
            init_account = self.broker.get_account_state(current_prices=current_prices)
            self.snap_repo.save_snapshot("snap_init_auto", run_id, init_account, exec_mode, strat_id)

        # 5. Pre-Trade State Reconciliation Gate
        pre_rec = ReconciliationEngine.reconcile(run_id, exec_mode, self.db, self.broker, self.rec_config)
        if not pre_rec.passed:
            reason = f"Pre-trade reconciliation failed: {[i.message for i in pre_rec.issues]}"
            self.logger.critical("RECONCILIATION_FAILURE", run_id=run_id, issues=reason)
            rec = AutonomousRunRecord(
                run_id=run_id, trading_date=trading_date, strategy_id=strat_id,
                timestamp=now, status="RECOVERY_REQUIRED", pre_reconciliation_status=pre_rec.status.value,
                rejection_reason=reason,
            )
            self.ledger_repo.record_run(rec)
            self.run_repo.complete_run(run_id, "FAILED", error_message=reason)
            return rec, self._build_blocked_report(run_id, trading_date, strat_id, reason)

        self.logger.info("PRE_TRADE_RECONCILIATION_MATCHED", run_id=run_id)

        # 6. Strategy Formulation
        target_portfolio = self.strategy.generate_target_portfolio(clean_df, as_of_date=as_of_date)
        tp_id = f"tp_{uuid.uuid4().hex[:12]}"
        self.tp_repo.save_target_portfolio(tp_id, target_portfolio, run_id=run_id)
        self.logger.info("TARGET_PORTFOLIO_CREATED", run_id=run_id, target_portfolio_id=tp_id)

        # Check instrument whitelist
        for sym in target_portfolio.target_weights:
            if sym not in self.config.autonomous_instrument_whitelist:
                reason = f"Symbol {sym!r} is outside the autonomous whitelist {self.config.autonomous_instrument_whitelist}."
                self.logger.error("AUTONOMOUS_RUN_BLOCKED", run_id=run_id, reason=reason)
                rec = AutonomousRunRecord(
                    run_id=run_id, trading_date=trading_date, strategy_id=strat_id,
                    timestamp=now, target_portfolio_id=tp_id, status="REJECTED", rejection_reason=reason,
                )
                self.ledger_repo.record_run(rec)
                self.run_repo.complete_run(run_id, "FAILED", error_message=reason)
                return rec, self._build_blocked_report(run_id, trading_date, strat_id, reason)

        # 7. RiskEngine Evaluation Gate
        account_state = self.broker.get_account_state(current_prices=current_prices)
        peak_nav = self.snap_repo.get_peak_nav(strat_id)
        if peak_nav <= 0:
            peak_nav = account_state.nav
        dec_id = f"dec_{uuid.uuid4().hex[:12]}"
        self.logger.info("RISK_EVALUATION_STARTED", run_id=run_id, decision_id=dec_id)
        risk_decision = self.risk_engine.evaluate(
            target_portfolio=target_portfolio,
            portfolio_state=account_state,
            current_prices=current_prices,
            peak_nav=peak_nav,
            portfolio_id=tp_id,
            decision_id=dec_id,
        )
        self.risk_repo.save_risk_evaluation(risk_decision)
        if not risk_decision.approved:
            reason = f"RiskEngine rejected target portfolio: {risk_decision.violations}"
            self.logger.warning("RISK_REJECTED", run_id=run_id, violations=risk_decision.violations)
            rec = AutonomousRunRecord(
                run_id=run_id, trading_date=trading_date, strategy_id=strat_id,
                timestamp=now, target_portfolio_id=tp_id, risk_decision_id=dec_id,
                status="REJECTED", rejection_reason=reason,
            )
            self.ledger_repo.record_run(rec)
            self.run_repo.complete_run(run_id, "FAILED", error_message=reason)
            return rec, self._build_blocked_report(run_id, trading_date, strat_id, reason)

        self.logger.info("RISK_APPROVED", run_id=run_id, decision_id=dec_id)

        # 8. OMS Order Batch Creation
        order_batch = OrderManagementSystem.generate_order_batch(
            current_holdings=account_state.holdings,
            target_portfolio=target_portfolio,
            current_prices=current_prices,
            nav=account_state.nav,
            run_id=run_id,
            execution_mode=exec_mode,
            target_portfolio_id=tp_id,
            risk_decision=risk_decision,
            require_risk_approval=True,
        )

        # 9. Autonomous Approval Token Generation & Approval Gate
        token = self.autonomous_gate.generate_autonomous_token(
            order_batch_id=order_batch.batch_id,
            risk_decision_id=dec_id,
            target_portfolio_id=tp_id,
            run_id=run_id,
            strategy_id=strat_id,
        )
        approved_batch = self.autonomous_gate.approve_batch(order_batch, token=token)
        self.logger.info("AUTONOMOUS_ORDER_AUTHORIZED", run_id=run_id, token_id=token.token_id, batch_id=order_batch.batch_id)

        # 10. Pre-Submission Revalidation Gate
        reval = PreSubmissionValidator.validate(
            order_batch=approved_batch,
            target_portfolio=target_portfolio,
            broker=self.broker,
            db_manager=self.db,
            approval_token=token,
            risk_engine=self.risk_engine,
            current_prices=current_prices,
            instrument_whitelist=list(self.config.autonomous_instrument_whitelist),
            allowed_order_types=list(self.config.allowed_order_types),
            live_capital_limit=self.config.max_live_capital,
            emergency_stop_active=self.config.emergency_stop_active,
            execution_mode=ExecutionMode.LIVE,
        )
        if not reval.passed:
            reason = f"Pre-submission revalidation failed: {reval.errors}"
            self.logger.error("AUTONOMOUS_RUN_BLOCKED", run_id=run_id, errors=reval.errors)
            rec = AutonomousRunRecord(
                run_id=run_id, trading_date=trading_date, strategy_id=strat_id,
                timestamp=now, target_portfolio_id=tp_id, risk_decision_id=dec_id,
                order_batch_id=order_batch.batch_id, approval_token_id=token.token_id,
                status="REJECTED", rejection_reason=reason,
            )
            self.ledger_repo.record_run(rec)
            self.run_repo.complete_run(run_id, "FAILED", error_message=reason)
            return rec, self._build_blocked_report(run_id, trading_date, strat_id, reason)

        # 11. Persist Approved Orders & Dispatch to Broker Adapter
        for o in approved_batch.orders:
            self.inst_repo.save_instrument(Instrument(symbol=o.symbol, asset_class=AssetClass.EQUITY))
            self.order_repo.save_order(o, execution_mode=exec_mode, client_order_id=o.client_order_id)
            self.broker.submit_order(o, price_lookup=current_prices)
            self.logger.info("ORDER_SUBMITTED", run_id=run_id, order_id=o.order_id, symbol=o.symbol, qty=o.quantity, side=o.side.value)

        # 12. Ingest Broker Executions & Persist Fills
        fills = self.broker.get_fills()
        total_comm = 0.0
        for f in fills:
            if self.fill_repo.get_fill_by_broker_execution_id(f.fill_id) is None:
                self.fill_repo.save_fill(f, broker_execution_id=f.fill_id)
                self.logger.info("ORDER_FILLED", run_id=run_id, fill_id=f.fill_id, symbol=f.symbol, shares=f.quantity, px=f.fill_price)
            total_comm += f.commission

        for o in approved_batch.orders:
            self.order_repo.update_order_status(o.order_id, OrderStatus.FILLED)

        # 13. Update Holdings & Marked-to-Market Snapshot
        holdings = self.broker.get_positions()
        self.holding_repo.save_holdings(holdings)
        final_account = self.broker.get_account_state(current_prices=current_prices)
        snap_id = f"snap_{uuid.uuid4().hex[:12]}"
        self.snap_repo.save_snapshot(snap_id, run_id, final_account, exec_mode, strat_id)

        # 14. Post-Execution Reconciliation Gate
        post_rec = ReconciliationEngine.reconcile(run_id, exec_mode, self.db, self.broker, self.rec_config)
        final_status = "COMPLETED" if post_rec.passed else "RECOVERY_REQUIRED"

        if post_rec.passed:
            self.logger.info("POST_TRADE_RECONCILIATION_MATCHED", run_id=run_id)
            self.logger.info("AUTONOMOUS_RUN_COMPLETED", run_id=run_id, nav=final_account.nav, cash=final_account.cash)
            self.run_repo.complete_run(run_id, "SUCCESS")
        else:
            self.logger.critical("RECONCILIATION_FAILURE", run_id=run_id, issues=[i.message for i in post_rec.issues])
            self.run_repo.complete_run(run_id, "FAILED", error_message=f"Post-reconciliation failed: {[i.message for i in post_rec.issues]}")

        active_weights = risk_decision.adjusted_weights or target_portfolio.target_weights
        gross_exp = sum(abs(w) for w in active_weights.values())
        net_exp = sum(w for w in active_weights.values())

        rec = AutonomousRunRecord(
            run_id=run_id,
            trading_date=trading_date,
            strategy_id=strat_id,
            timestamp=datetime.now(timezone.utc),
            order_batch_id=order_batch.batch_id,
            target_portfolio_id=tp_id,
            risk_decision_id=dec_id,
            approval_token_id=token.token_id,
            orders_count=len(approved_batch.orders),
            fills_count=len(approved_batch.orders),
            gross_exposure=gross_exp,
            net_exposure=net_exp,
            nav=final_account.nav,
            cash=final_account.cash,
            pre_reconciliation_status=pre_rec.status.value,
            post_reconciliation_status=post_rec.status.value,
            status=final_status,
            rejection_reason=None if post_rec.passed else f"Post-reconciliation issues: {[i.message for i in post_rec.issues]}",
        )
        self.ledger_repo.record_run(rec)

        report = DailyPaperReport(
            run_id=run_id,
            date_iso=trading_date,
            strategy_id=strat_id,
            nav=final_account.nav,
            cash=final_account.cash,
            gross_exposure=gross_exp,
            net_exposure=net_exp,
            orders=[{"symbol": o.symbol, "side": o.side.value, "quantity": o.quantity} for o in approved_batch.orders],
            fills=[{"symbol": f.symbol, "side": f.side.value, "quantity": f.quantity, "price": f.fill_price} for f in fills],
            transaction_costs=total_comm,
            borrow_costs=0.0,
            risk_decision=risk_decision.metadata,
            pre_reconciliation_status=pre_rec.status.value,
            post_reconciliation_status=post_rec.status.value,
            target_weights=dict(active_weights),
            actual_holdings={sym: h.shares for sym, h in holdings.items()},
            weight_drift={sym: final_account.realized_weights.get(sym, 0.0) - active_weights.get(sym, 0.0) for sym in active_weights},
            executed_changes={o.symbol: (o.quantity if o.side == OrderSide.BUY else -o.quantity) for o in approved_batch.orders},
            final_run_status=RunStatus.COMPLETED if post_rec.passed else RunStatus.RECOVERY_REQUIRED,
        )

        return rec, report

    def _build_blocked_report(self, run_id: str, trading_date: str, strat_id: str, reason: str) -> DailyPaperReport:
        """Constructs an empty report when autonomous execution is blocked."""
        return DailyPaperReport(
            run_id=run_id,
            date_iso=trading_date,
            strategy_id=strat_id,
            nav=0.0,
            cash=0.0,
            gross_exposure=0.0,
            net_exposure=0.0,
            final_run_status=RunStatus.VALIDATION_FAILED,
        )
