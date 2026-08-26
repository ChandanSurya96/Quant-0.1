"""Crash recovery manager and state machine."""

from __future__ import annotations

from typing import Tuple

from ..broker.base import BrokerAdapter
from ..core.enums import ExecutionMode, OrderStatus
from ..observability.alerts import Alert, AlertDispatcher
from ..observability.events import AlertSeverity, EventType
from ..persistence.database import DatabaseManager
from ..persistence.repositories.fill_repo import FillRepository
from ..persistence.repositories.holding_repo import HoldingRepository
from ..persistence.repositories.order_repo import OrderRepository
from ..persistence.repositories.snapshot_repo import SnapshotRepository
from .engine import ReconciliationEngine
from .types import (
    ReconciliationConfig,
    ReconciliationIssueType,
    ReconciliationResult,
    RecoveryState,
)


class RecoveryManager:
    """Manages crash recovery transitions, idempotent internal state synchronization, and execution gating."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        alert_dispatcher: AlertDispatcher | None = None,
    ) -> None:
        self.db = db_manager
        self.alert_dispatcher = alert_dispatcher or AlertDispatcher()
        self.state = RecoveryState.HEALTHY

    def reconcile_and_recover(
        self,
        run_id: str,
        execution_mode: ExecutionMode,
        broker: BrokerAdapter,
        config: ReconciliationConfig | None = None,
    ) -> Tuple[RecoveryState, ReconciliationResult]:
        """Executes idempotent crash recovery and reconciliation against the external broker authority.

        State Flow:
            HEALTHY -> RECONCILING -> MATCHED -> EXECUTION_PERMITTED
            or
            MISMATCHED -> (Idempotent State Ingestion) -> MATCHED -> EXECUTION_PERMITTED
            or
            UNRESOLVED MISMATCH -> RECOVERY_REQUIRED (Execution Blocked)
        """
        self.state = RecoveryState.RECONCILING

        # 1. Initial Reconciliation Check
        result = ReconciliationEngine.reconcile(
            run_id=run_id,
            execution_mode=execution_mode,
            db_manager=self.db,
            broker=broker,
            config=config,
        )

        if result.is_matched:
            self.state = RecoveryState.EXECUTION_PERMITTED
            return self.state, result

        # 2. Attempt Idempotent Internal State Synchronization
        # (e.g. process died after broker fill but before fill/holdings were persisted to SQLite)
        fill_repo = FillRepository(self.db)
        order_repo = OrderRepository(self.db)
        holding_repo = HoldingRepository(self.db)
        snap_repo = SnapshotRepository(self.db)

        has_missing_fills = any(
            issue.issue_type == ReconciliationIssueType.FILL_MISSING_INTERNAL
            for issue in result.issues
        )

        if has_missing_fills:
            broker_fills = broker.get_fills()
            with self.db.transaction() as conn:
                for f in broker_fills:
                    existing = fill_repo.get_fill(f.fill_id, conn=conn)
                    if existing is None:
                        existing = fill_repo.get_fill_by_broker_execution_id(f.fill_id, conn=conn)
                    if existing is None:
                        fill_repo.save_fill(f, broker_execution_id=f.fill_id, conn=conn)
                        order_repo.update_order_status(f.order_id, OrderStatus.FILLED, conn=conn)

                # Synchronize holdings and snapshot to match broker confirmed state
                broker_positions = broker.get_positions()
                holding_repo.save_holdings(broker_positions, conn=conn)

                broker_state = broker.get_account_state()
                snap_repo.save_snapshot(
                    snapshot_id=f"snap_recov_{result.reconciliation_id}",
                    run_id=run_id,
                    state=broker_state,
                    execution_mode=execution_mode,
                    strategy_id="recovery",
                    conn=conn,
                )

        # 3. Post-Synchronization Verification
        post_result = ReconciliationEngine.reconcile(
            run_id=run_id,
            execution_mode=execution_mode,
            db_manager=self.db,
            broker=broker,
            config=config,
        )

        if post_result.is_matched:
            self.state = RecoveryState.EXECUTION_PERMITTED
            return self.state, post_result

        # 4. Unresolved Mismatch -> Fail Closed (No automated corrective trading)
        self.state = RecoveryState.RECOVERY_REQUIRED
        self.alert_dispatcher.dispatch(
            Alert(
                severity=AlertSeverity.CRITICAL,
                event_type=EventType.SYSTEM_RECOVERY_REQUIRED,
                component="RecoveryManager",
                message=f"Reconciliation failure! Found {len(post_result.issues)} unresolved discrepancies.",
                run_id=run_id,
                details={"issues_count": len(post_result.issues), "issues": [i.to_dict() for i in post_result.issues]},
            )
        )
        return self.state, post_result
