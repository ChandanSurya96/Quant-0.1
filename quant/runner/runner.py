"""Paper trading runner orchestrating the complete production execution loop."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from ..broker.base import BrokerAdapter
from ..core.enums import AssetClass, ExecutionMode, OrderStatus
from ..core.interfaces import Instrument, TargetPortfolio
from ..data.base import MarketDataProvider
from ..data.validation import DataValidationGate
from ..observability.alerts import Alert, AlertDispatcher
from ..observability.events import AlertSeverity, EventType
from ..observability.health import check_broker_health, check_persistence_health, check_risk_health
from ..observability.logging import StructuredLogger
from ..oms.approval import AutoApproveGate, ExecutionApprovalGate
from ..oms.engine import OrderManagementSystem
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
from ..strategies.base import BaseStrategy
from .ledger import PaperRunLedger
from .models import DailyPaperReport, PaperRunRecord, RunStatus


class PaperTradingRunner:
    """Orchestrates daily paper execution, health checks, risk controls, and reconciliation."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        broker: BrokerAdapter,
        strategy: BaseStrategy,
        data_provider: MarketDataProvider | None = None,
        risk_engine: RiskEngine | None = None,
        approval_gate: ExecutionApprovalGate | None = None,
        alert_dispatcher: AlertDispatcher | None = None,
        logger: StructuredLogger | None = None,
        reconciliation_config: ReconciliationConfig | None = None,
    ) -> None:
        self.db = db_manager
        self.broker = broker
        self.strategy = strategy
        self.data_provider = data_provider
        self.risk_engine = risk_engine or RiskEngine(RiskConfig(scale_gross_leverage=True))
        self.approval_gate = approval_gate or AutoApproveGate()
        self.alert_dispatcher = alert_dispatcher or AlertDispatcher()
        self.logger = logger or StructuredLogger("PaperTradingRunner")
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

    def run_once(
        self,
        run_id: str | None = None,
        as_of_date: datetime | str | None = None,
        market_data: pd.DataFrame | None = None,
        current_prices: dict[str, float] | None = None,
        expected_universe: list[str] | None = None,
        is_rebalance_day: bool = True,
        available_borrows: set[str] | dict[str, bool] | None = None,
    ) -> tuple[PaperRunRecord, DailyPaperReport]:
        """Executes a single daily paper trading cycle with full fail-closed gating."""
        r_id = run_id or f"run_paper_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        now = datetime.now(timezone.utc)
        strat_id = self.strategy.strategy_id

        # ------------------------------------------------ 1. Idempotency Check
        existing_run = self.ledger.get_run(r_id)
        if existing_run is not None and existing_run.status == RunStatus.COMPLETED:
            # Return existing completed run record without duplicate execution
            report = self.ledger._reports.get(r_id) or DailyPaperReport(
                run_id=r_id,
                date_iso=str(as_of_date or now.date()),
                strategy_id=strat_id,
                nav=existing_run.nav,
                cash=existing_run.cash,
                gross_exposure=existing_run.gross_exposure,
                net_exposure=existing_run.net_exposure,
                final_run_status=RunStatus.COMPLETED,
            )
            return existing_run, report

        # Initialize durable run record
        self.run_repo.create_run(r_id, ExecutionMode.PAPER, strat_id)
        record = PaperRunRecord(
            run_id=r_id,
            execution_mode=ExecutionMode.PAPER,
            strategy_id=strat_id,
            start_time=now,
            status=RunStatus.STARTED,
        )

        # ------------------------------------------------ 2. System Health Check
        persistence_h = check_persistence_health(self.db)
        broker_h = check_broker_health(self.broker)
        risk_h = check_risk_health(self.risk_engine)
        if not (persistence_h.is_healthy and broker_h.is_healthy and risk_h.is_healthy):
            self.logger.warning("Unhealthy system components detected during run pre-check.")

        # Bootstrap initial snapshot if database is brand new (Day 1 initial state)
        if self.snap_repo.get_latest_snapshot() is None and not self.holding_repo.get_holdings():
            initial_state = self.broker.get_account_state()
            self.snap_repo.save_snapshot(
                snapshot_id=f"snap_init_{r_id}",
                run_id=r_id,
                state=initial_state,
                execution_mode=ExecutionMode.PAPER,
                strategy_id=strat_id,
            )

        # ------------------------------------------------ 3. Pre-Execution Reconciliation
        pre_rec = ReconciliationEngine.reconcile(
            run_id=r_id,
            execution_mode=ExecutionMode.PAPER,
            db_manager=self.db,
            broker=self.broker,
            config=self.rec_config,
        )
        record.pre_reconciliation_status = pre_rec.status.value

        if not pre_rec.passed:
            record.status = RunStatus.RECONCILIATION_FAILED
            record.error_message = f"Pre-execution reconciliation failed with {len(pre_rec.issues)} issues."
            self.alert_dispatcher.dispatch(
                Alert(
                    severity=AlertSeverity.CRITICAL,
                    event_type=EventType.SYSTEM_RECOVERY_REQUIRED,
                    component="PaperTradingRunner",
                    message=record.error_message,
                    run_id=r_id,
                )
            )
            self._finalize_and_record(record)
            return record, self._build_empty_report(record, as_of_date)

        # ------------------------------------------------ 4. Market Data Ingestion & Validation
        df = market_data
        universe = expected_universe or getattr(self.strategy, "universe", list(df.columns) if df is not None else ["SPY", "TLT"])
        if df is None:
            if self.data_provider is None:
                record.status = RunStatus.DATA_FAILED
                record.error_message = "No market data or DataProvider supplied. Zero orders."
                self._finalize_and_record(record)
                return record, self._build_empty_report(record, as_of_date)

            try:
                # Fetch daily bars from data provider
                df = self.data_provider.fetch_daily_bars(universe, start_date="2020-01-01")
            except Exception as e:
                record.status = RunStatus.DATA_FAILED
                record.error_message = f"Data provider download failed: {e}"
                self._finalize_and_record(record)
                return record, self._build_empty_report(record, as_of_date)

        # Validate market data matrix fail-closed
        try:
            DataValidationGate.validate_matrix(df, universe, mode=ExecutionMode.PAPER)
        except Exception as e:
            record.status = RunStatus.VALIDATION_FAILED
            record.error_message = f"DataValidationGate rejected market data: {e}"
            self._finalize_and_record(record)
            return record, self._build_empty_report(record, as_of_date)

        # ------------------------------------------------ 5. Price Extraction & Mark-to-Market
        if current_prices:
            prices = dict(current_prices)
        else:
            last_row = df.iloc[-1]
            prices = {sym: float(last_row[sym]) for sym in universe if sym in last_row}

        # Save active instruments into persistence
        for sym in universe:
            self.inst_repo.save_instrument(Instrument(symbol=sym, asset_class=AssetClass.EQUITY))

        # Mark broker positions to market
        account_state = self.broker.get_account_state(current_prices=prices)
        record.nav = account_state.nav
        record.cash = account_state.cash

        # ------------------------------------------------ 6. Strategy Target Portfolio Generation
        tp_id = f"tp_{uuid.uuid4().hex[:12]}"
        if is_rebalance_day:
            target_portfolio = self.strategy.generate_target_portfolio(df, as_of_date=as_of_date)
        else:
            # On non-rebalance drift days, retain current realized weights (0 delta trades)
            target_portfolio = TargetPortfolio(
                timestamp=now,
                strategy_id=strat_id,
                target_weights=account_state.realized_weights,
                rebalance_horizon=21,
                metadata={"drift_day": True},
            )

        self.tp_repo.save_target_portfolio(tp_id, target_portfolio, run_id=r_id)
        record.target_portfolio_id = tp_id

        # ------------------------------------------------ 7. Pre-Trade Risk Evaluation
        d_id = f"dec_{uuid.uuid4().hex[:12]}"
        risk_decision = self.risk_engine.evaluate(
            target_portfolio=target_portfolio,
            portfolio_state=account_state,
            current_prices=prices,
            portfolio_id=tp_id,
            decision_id=d_id,
            available_borrows=available_borrows,
        )
        self.risk_repo.save_risk_evaluation(risk_decision)
        record.risk_decision_id = d_id
        active_weights = risk_decision.adjusted_weights if risk_decision.adjusted_weights else target_portfolio.target_weights
        record.gross_exposure = sum(abs(w) for w in active_weights.values())
        record.net_exposure = sum(w for w in active_weights.values())
        record.drawdown = risk_decision.metrics.get("drawdown", 0.0)

        if not risk_decision.approved:
            record.status = RunStatus.RISK_REJECTED
            record.error_message = f"RiskEngine rejected TargetPortfolio: {risk_decision.violations}"
            self._finalize_and_record(record)
            return record, self._build_empty_report(record, as_of_date, target_portfolio, risk_decision)

        # ------------------------------------------------ 8. OMS Order Batch Generation
        current_holdings = self.broker.get_positions()
        batch_id = f"batch_{uuid.uuid4().hex[:12]}"
        if is_rebalance_day:
            order_batch = OrderManagementSystem.generate_order_batch(
                current_holdings=current_holdings,
                target_portfolio=target_portfolio,
                current_prices=prices,
                nav=account_state.nav,
                run_id=r_id,
                execution_mode=ExecutionMode.PAPER,
                batch_id=batch_id,
                target_portfolio_id=tp_id,
                risk_decision=risk_decision,
                require_risk_approval=True,
            )
        else:
            # On intra-month drift days, zero orders are generated
            from ..core.interfaces import OrderBatch
            order_batch = OrderBatch(
                batch_id=batch_id,
                target_portfolio_id=tp_id,
                strategy_id=strat_id,
                orders=[],
                execution_mode=ExecutionMode.PAPER,
                generated_at=now,
                metadata={"drift_day": True, "risk_decision_id": d_id, "run_id": r_id},
            )

        record.order_batch_id = batch_id
        record.orders_count = len(order_batch.orders)

        # Save orders to SQLite
        for o in order_batch.orders:
            self.order_repo.save_order(o, execution_mode=ExecutionMode.PAPER, client_order_id=o.client_order_id)

        # ------------------------------------------------ 9. Approval Gate & Broker Execution
        approved_batch = self.approval_gate.request_approval(order_batch)
        fills_executed = []
        executed_trade_deltas: dict[str, float] = {}

        if approved_batch is not None:
            for ord_item in approved_batch.orders:
                # Update order to SUBMITTED
                self.order_repo.update_order_status(ord_item.order_id, OrderStatus.SUBMITTED)
                fill = self.broker.submit_order(ord_item, price_lookup=prices)
                if fill is not None:
                    self.fill_repo.save_fill(fill, broker_execution_id=fill.fill_id)
                    self.order_repo.update_order_status(ord_item.order_id, OrderStatus.FILLED)
                    fills_executed.append(fill)
                    executed_trade_deltas[fill.symbol] = fill.quantity if fill.side.value == "BUY" else -fill.quantity

        record.fills_count = len(fills_executed)
        record.transaction_costs = sum(f.commission for f in fills_executed)

        # ------------------------------------------------ 10. Holdings Sync & Snapshot Persistence
        updated_positions = self.broker.get_positions()
        self.holding_repo.save_holdings(updated_positions)

        final_account_state = self.broker.get_account_state(current_prices=prices)
        record.nav = final_account_state.nav
        record.cash = final_account_state.cash

        snap_id = f"snap_{r_id}"
        self.snap_repo.save_snapshot(
            snapshot_id=snap_id,
            run_id=r_id,
            state=final_account_state,
            execution_mode=ExecutionMode.PAPER,
            strategy_id=strat_id,
        )

        # ------------------------------------------------ 11. Post-Execution Reconciliation
        post_rec = ReconciliationEngine.reconcile(
            run_id=r_id,
            execution_mode=ExecutionMode.PAPER,
            db_manager=self.db,
            broker=self.broker,
            config=self.rec_config,
        )
        record.post_reconciliation_status = post_rec.status.value

        if post_rec.passed:
            record.status = RunStatus.COMPLETED
        else:
            record.status = RunStatus.RECOVERY_REQUIRED
            record.error_message = f"Post-execution reconciliation failed with {len(post_rec.issues)} issues."

        # ------------------------------------------------ 12. Finalize Record & Build Report
        self._finalize_and_record(record)

        report = DailyPaperReport(
            run_id=r_id,
            date_iso=str(as_of_date or now.date()),
            strategy_id=strat_id,
            nav=final_account_state.nav,
            cash=final_account_state.cash,
            gross_exposure=record.gross_exposure,
            net_exposure=record.net_exposure,
            orders=[{"symbol": o.symbol, "side": o.side.value, "quantity": o.quantity} for o in order_batch.orders],
            fills=[{"symbol": f.symbol, "side": f.side.value, "quantity": f.quantity, "price": f.fill_price} for f in fills_executed],
            transaction_costs=record.transaction_costs,
            borrow_costs=record.borrow_costs,
            risk_decision=risk_decision.metadata,
            pre_reconciliation_status=record.pre_reconciliation_status,
            post_reconciliation_status=record.post_reconciliation_status,
            target_weights=dict(target_portfolio.target_weights),
            actual_holdings={sym: h.shares for sym, h in updated_positions.items()},
            weight_drift={sym: final_account_state.realized_weights.get(sym, 0.0) - target_portfolio.target_weights.get(sym, 0.0) for sym in universe},
            executed_changes=executed_trade_deltas,
            final_run_status=record.status,
        )

        return record, report

    def _finalize_and_record(self, record: PaperRunRecord) -> None:
        record.end_time = datetime.now(timezone.utc)
        self.run_repo.complete_run(
            record.run_id,
            "SUCCESS" if record.status == RunStatus.COMPLETED else "FAILED",
            error_message=record.error_message,
        )
        self.ledger.record_run(record)

    def _build_empty_report(
        self,
        record: PaperRunRecord,
        as_of_date: datetime | str | None,
        target_portfolio: TargetPortfolio | None = None,
        risk_decision: Any | None = None,
    ) -> DailyPaperReport:
        now = datetime.now(timezone.utc)
        return DailyPaperReport(
            run_id=record.run_id,
            date_iso=str(as_of_date or now.date()),
            strategy_id=record.strategy_id,
            nav=record.nav,
            cash=record.cash,
            gross_exposure=record.gross_exposure,
            net_exposure=record.net_exposure,
            orders=[],
            fills=[],
            risk_decision=risk_decision.metadata if risk_decision else {},
            pre_reconciliation_status=record.pre_reconciliation_status,
            post_reconciliation_status=record.post_reconciliation_status,
            target_weights=dict(target_portfolio.target_weights) if target_portfolio else {},
            actual_holdings={},
            final_run_status=record.status,
        )
