"""Portfolio reconciler and execution gate for the Order Management System."""

from __future__ import annotations

from ..broker.base import BrokerAdapter
from ..core.enums import ExecutionMode
from ..core.exceptions import ReconciliationError
from ..persistence.database import DatabaseManager
from ..reconciliation.engine import ReconciliationEngine
from ..reconciliation.types import (
    ReconciliationConfig,
    ReconciliationResult,
)


class ExecutionReconciliationGate:
    """Execution gate enforcing that only trusted, reconciled state permits broker order submission."""

    @staticmethod
    def enforce_gate(result: ReconciliationResult) -> None:
        """Raises ReconciliationError if reconciliation did not pass 100% cleanly."""
        if not result.passed:
            violation_summary = "; ".join(result.violations)
            raise ReconciliationError(
                f"Execution Halted: Reconciliation failed ({result.status.value}) with {len(result.issues)} issues: {violation_summary}"
            )


class PortfolioReconciler:
    """High-level portfolio state reconciler and execution gatekeeper for OMS."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        config: ReconciliationConfig | None = None,
    ) -> None:
        self._db = db_manager
        self._config = config or ReconciliationConfig()

    def reconcile(
        self,
        run_id: str,
        execution_mode: ExecutionMode,
        broker: BrokerAdapter,
        config_override: ReconciliationConfig | None = None,
    ) -> ReconciliationResult:
        """Performs a deterministic read-only reconciliation check."""
        cfg = config_override or self._config
        return ReconciliationEngine.reconcile(
            run_id=run_id,
            execution_mode=execution_mode,
            db_manager=self._db,
            broker=broker,
            config=cfg,
        )

    def reconcile_and_gate(
        self,
        run_id: str,
        execution_mode: ExecutionMode,
        broker: BrokerAdapter,
        config_override: ReconciliationConfig | None = None,
    ) -> ReconciliationResult:
        """Performs reconciliation and raises ReconciliationError if state is not matched."""
        result = self.reconcile(run_id, execution_mode, broker, config_override)
        ExecutionReconciliationGate.enforce_gate(result)
        return result
