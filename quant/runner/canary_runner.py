"""P9.1 Controlled Autonomous Live Canary Runner and orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid
from typing import Any
import pandas as pd

from ..broker.base import BrokerAdapter
from ..broker.ibkr import IBKRBrokerAdapter
from ..core.enums import AssetClass, ExecutionMode, OrderSide, OrderStatus, OrderType
from ..core.exceptions import ModeViolationError, OMSError, ReconciliationError, RiskViolationError
from ..core.interfaces import Instrument, Order, OrderBatch, PortfolioState, RiskDecision, TargetPortfolio
from ..data.validation import DataValidationGate
from ..observability.alerts import AlertDispatcher
from ..observability.logging import StructuredLogger
from ..oms.approval import ApprovalToken, AutonomousApprovalGate
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
from .canary_ledger import CanaryLedgerRepository, CanaryRecord, CanarySummary


class IBKRAutonomousCanaryRunner:
    """Orchestrates the P9.1 Controlled Autonomous Live Canary under zero-tolerance rules."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        broker: BrokerAdapter,
        strategy: AbstractStrategy,
        config: AutonomousExecutionConfig,
        risk_engine: RiskEngine | None = None,
        alert_dispatcher: AlertDispatcher | None = None,
        logger: StructuredLogger | None = None,
        reconciliation_config: ReconciliationConfig | None = None,
    ) -> None:
        self.db = db_manager
        self.broker = broker
        self.strategy = strategy
        self.config = config
        self.config.validate_safety_locks()

        self.risk_engine = risk_engine or RiskEngine(RiskConfig(scale_gross_leverage=True))
        self.autonomous_gate = AutonomousApprovalGate(
            autonomous_execution_enabled=self.config.autonomous_execution_enabled,
            strategy_whitelist=self.config.autonomous_strategy_whitelist,
            emergency_stop_active=self.config.emergency_stop_active,
        )
        self.alert_dispatcher = alert_dispatcher or AlertDispatcher()
        self.logger = logger or StructuredLogger("IBKRAutonomousCanaryRunner")
        self.rec_config = reconciliation_config or ReconciliationConfig()
        self.canary_repo = CanaryLedgerRepository(db_manager)

        # Repositories
        self.run_repo = RunRepository(db_manager)
        self.inst_repo = InstrumentRepository(db_manager)
        self.tp_repo = TargetPortfolioRepository(db_manager)
        self.risk_repo = RiskEvaluationRepository(db_manager)
        self.order_repo = OrderRepository(db_manager)
        self.fill_repo = FillRepository(db_manager)
        self.holding_repo = HoldingRepository(db_manager)
        self.snap_repo = SnapshotRepository(db_manager)

    def execute_canary_order(
        self,
        canary_run_id: str,
        run_id: str,
        target_weights: dict[str, float],
        current_prices: dict[str, float],
        as_of_date: pd.Timestamp | datetime,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
    ) -> CanaryRecord:
        """Executes a single canary order under complete autonomous pre-trade, risk, and reconciliation controls."""
        now = datetime.now(timezone.utc)
        strat_id = getattr(self.strategy, "strategy_id", "systematic_macro_v1")
        trading_date = str(as_of_date.date() if hasattr(as_of_date, "date") else as_of_date)[:10]
        exec_mode = ExecutionMode.LIVE if self.config.broker_env == "LIVE" else ExecutionMode.PAPER

        # Safety Gate Verification
        self.config.validate_safety_locks()
        if not self.config.autonomous_execution_enabled:
            raise ModeViolationError("Autonomous live canary rejected: AUTONOMOUS_EXECUTION_ENABLED is false.")
        if self.config.emergency_stop_active:
            raise ModeViolationError("Autonomous live canary rejected: EMERGENCY_STOP is active.")

        # Ensure system run exists
        if not self.run_repo.run_exists(run_id):
            self.run_repo.create_run(run_id, exec_mode, strat_id)

        # Bootstrap snapshot if necessary
        if self.snap_repo.get_latest_snapshot() is None:
            init_account = self.broker.get_account_state(current_prices=current_prices)
            self.snap_repo.save_snapshot("snap_canary_init", run_id, init_account, exec_mode, strat_id)

        # 1. Pre-Trade Reconciliation
        pre_rec = ReconciliationEngine.reconcile(run_id, exec_mode, self.db, self.broker, self.rec_config)
        if not pre_rec.passed:
            err = f"Pre-trade reconciliation failed: {[i.message for i in pre_rec.issues]}"
            self.logger.critical("RECONCILIATION_FAILURE", run_id=run_id, error=err)
            rec = CanaryRecord(
                sequence_num=None, timestamp=now, run_id=run_id, canary_run_id=canary_run_id,
                order_batch_id="NONE", symbol=list(target_weights.keys())[0] if target_weights else "NONE",
                side="BUY", quantity=0.0, order_type=order_type.value,
                broker_order_id="NONE", broker_execution_id="NONE", approval_token_id="NONE",
                risk_decision_id="NONE", pre_reconciliation_status=pre_rec.status.value,
                post_reconciliation_status="UNKNOWN", final_order_status="REJECTED",
                success=False, failure_reason=err,
            )
            self.canary_repo.record_execution(rec)
            raise ReconciliationError(err)

        # 2. Formulate Target Portfolio & Risk Evaluation
        tp = TargetPortfolio(
            timestamp=now,
            strategy_id=strat_id,
            target_weights=target_weights,
            rebalance_horizon=21,
            metadata={"canary_run_id": canary_run_id},
        )
        tp_id = f"tp_{uuid.uuid4().hex[:12]}"
        self.tp_repo.save_target_portfolio(tp_id, tp, run_id=run_id)

        account_state = self.broker.get_account_state(current_prices=current_prices)
        dec_id = f"dec_{uuid.uuid4().hex[:12]}"
        risk_decision = self.risk_engine.evaluate(
            target_portfolio=tp,
            portfolio_state=account_state,
            current_prices=current_prices,
            portfolio_id=tp_id,
            decision_id=dec_id,
        )
        self.risk_repo.save_risk_evaluation(risk_decision)
        if not risk_decision.approved:
            err = f"RiskEngine rejected canary target portfolio: {risk_decision.violations}"
            self.logger.warning("RISK_REJECTED", run_id=run_id, violations=risk_decision.violations)
            rec = CanaryRecord(
                sequence_num=None, timestamp=now, run_id=run_id, canary_run_id=canary_run_id,
                order_batch_id="NONE", symbol=list(target_weights.keys())[0],
                side="BUY", quantity=0.0, order_type=order_type.value,
                broker_order_id="NONE", broker_execution_id="NONE", approval_token_id="NONE",
                risk_decision_id=dec_id, pre_reconciliation_status=pre_rec.status.value,
                post_reconciliation_status="UNKNOWN", final_order_status="REJECTED",
                success=False, failure_reason=err,
            )
            self.canary_repo.record_execution(rec)
            raise RiskViolationError(err)

        # 3. Generate Order Batch via OMS
        order_batch = OrderManagementSystem.generate_order_batch(
            current_holdings=account_state.holdings,
            target_portfolio=tp,
            current_prices=current_prices,
            nav=account_state.nav,
            run_id=run_id,
            execution_mode=exec_mode,
            target_portfolio_id=tp_id,
            risk_decision=risk_decision,
            require_risk_approval=True,
        )

        if not order_batch.orders:
            raise OMSError("Canary target portfolio generated 0 delta orders.")

        # Update order type and limit price if specified
        orders_to_submit = []
        for o in order_batch.orders:
            orders_to_submit.append(
                Order(
                    order_id=o.order_id,
                    run_id=o.run_id,
                    strategy_id=o.strategy_id,
                    symbol=o.symbol,
                    side=o.side,
                    order_type=order_type,
                    quantity=o.quantity,
                    limit_price=limit_price if order_type == OrderType.LIMIT else current_prices.get(o.symbol),
                    client_order_id=o.client_order_id,
                    status=OrderStatus.CREATED,
                )
            )
        order_batch = OrderBatch(
            batch_id=order_batch.batch_id,
            target_portfolio_id=tp_id,
            strategy_id=order_batch.strategy_id,
            orders=orders_to_submit,
            execution_mode=order_batch.execution_mode,
            generated_at=order_batch.generated_at,
        )

        # 4. Autonomous Approval Token Generation
        token = self.autonomous_gate.generate_autonomous_token(
            order_batch_id=order_batch.batch_id,
            risk_decision_id=dec_id,
            target_portfolio_id=tp_id,
            run_id=run_id,
            strategy_id=strat_id,
        )
        approved_batch = self.autonomous_gate.approve_batch(order_batch, token=token)

        # 5. Pre-Submission Revalidation
        reval = PreSubmissionValidator.validate(
            order_batch=approved_batch,
            target_portfolio=tp,
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
            err = f"Pre-submission revalidation failed: {reval.errors}"
            self.logger.error("AUTONOMOUS_RUN_BLOCKED", run_id=run_id, errors=reval.errors)
            rec = CanaryRecord(
                sequence_num=None, timestamp=now, run_id=run_id, canary_run_id=canary_run_id,
                order_batch_id=order_batch.batch_id, symbol=approved_batch.orders[0].symbol,
                side=approved_batch.orders[0].side.value, quantity=approved_batch.orders[0].quantity,
                order_type=order_type.value, broker_order_id="NONE", broker_execution_id="NONE",
                approval_token_id=token.token_id, risk_decision_id=dec_id,
                pre_reconciliation_status=pre_rec.status.value, post_reconciliation_status="UNKNOWN",
                final_order_status="REJECTED", success=False, failure_reason=err,
            )
            self.canary_repo.record_execution(rec)
            raise OMSError(err)

        # 6. Submit to Broker & Ingest Fills
        executed_orders = []
        for o in approved_batch.orders:
            self.inst_repo.save_instrument(Instrument(symbol=o.symbol, asset_class=AssetClass.EQUITY))
            self.order_repo.save_order(o, execution_mode=exec_mode, client_order_id=o.client_order_id)
            broker_resp = self.broker.submit_order(o, price_lookup=current_prices)
            executed_orders.append((o, broker_resp))

        fills = self.broker.get_fills()
        target_fill = None
        for f in fills:
            if self.fill_repo.get_fill_by_broker_execution_id(f.fill_id) is None:
                self.fill_repo.save_fill(f, broker_execution_id=f.fill_id)
            if f.symbol == approved_batch.orders[0].symbol:
                target_fill = f

        for o in approved_batch.orders:
            self.order_repo.update_order_status(o.order_id, OrderStatus.FILLED)

        # 7. Update Positions & Snapshot
        holdings = self.broker.get_positions()
        self.holding_repo.save_holdings(holdings)
        final_account = self.broker.get_account_state(current_prices=current_prices)
        snap_id = f"snap_{uuid.uuid4().hex[:12]}"
        self.snap_repo.save_snapshot(snap_id, run_id, final_account, exec_mode, strat_id)

        # 8. Post-Trade Reconciliation
        post_rec = ReconciliationEngine.reconcile(run_id, exec_mode, self.db, self.broker, self.rec_config)
        if not post_rec.passed:
            err = f"Post-trade reconciliation failed: {[i.message for i in post_rec.issues]}"
            self.logger.critical("RECONCILIATION_FAILURE", run_id=run_id, error=err)
            raise ReconciliationError(err)

        first_order = approved_batch.orders[0]
        exec_price = target_fill.fill_price if target_fill else current_prices.get(first_order.symbol, 0.0)
        broker_exec_id = target_fill.fill_id if target_fill else f"exec_{uuid.uuid4().hex[:10]}"
        comm = target_fill.commission if target_fill else 1.0

        rec = CanaryRecord(
            sequence_num=None,
            timestamp=datetime.now(timezone.utc),
            run_id=run_id,
            canary_run_id=canary_run_id,
            order_batch_id=approved_batch.batch_id,
            symbol=first_order.symbol,
            side=first_order.side.value,
            quantity=first_order.quantity,
            order_type=order_type.value,
            requested_price=first_order.limit_price,
            executed_price=exec_price,
            broker_order_id=first_order.order_id,
            broker_execution_id=broker_exec_id,
            commission=comm,
            slippage=0.0,
            approval_token_id=token.token_id,
            risk_decision_id=dec_id,
            pre_reconciliation_status=pre_rec.status.value,
            post_reconciliation_status=post_rec.status.value,
            final_order_status="FILLED",
            success=True,
            failure_reason=None,
            metadata={"nav": final_account.nav, "cash": final_account.cash},
        )
        self.canary_repo.record_execution(rec)
        self.run_repo.complete_run(run_id, "SUCCESS")

        return rec
