"""Domain models, ledger records, and report structures for paper trading runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any

from ..core.enums import ExecutionMode


class RunStatus(str, Enum):
    """Lifecycle and terminal statuses for a paper trading run."""
    STARTED = "STARTED"
    DATA_FAILED = "DATA_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    RISK_REJECTED = "RISK_REJECTED"
    RECONCILIATION_FAILED = "RECONCILIATION_FAILED"
    EXECUTED = "EXECUTED"
    COMPLETED = "COMPLETED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


@dataclass
class PaperRunRecord:
    """Persistent audit entry for a paper trading session."""
    run_id: str
    execution_mode: ExecutionMode
    strategy_id: str
    start_time: datetime
    end_time: datetime | None = None
    data_timestamp: datetime | None = None
    target_portfolio_id: str | None = None
    risk_decision_id: str | None = None
    order_batch_id: str | None = None
    orders_count: int = 0
    fills_count: int = 0
    gross_exposure: float = 0.0
    net_exposure: float = 0.0
    nav: float = 0.0
    cash: float = 0.0
    drawdown: float = 0.0
    transaction_costs: float = 0.0
    borrow_costs: float = 0.0
    pre_reconciliation_status: str = "UNKNOWN"
    post_reconciliation_status: str = "UNKNOWN"
    status: RunStatus = RunStatus.STARTED
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "execution_mode": self.execution_mode.value,
            "strategy_id": self.strategy_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "data_timestamp": self.data_timestamp.isoformat() if self.data_timestamp else None,
            "target_portfolio_id": self.target_portfolio_id,
            "risk_decision_id": self.risk_decision_id,
            "order_batch_id": self.order_batch_id,
            "orders_count": self.orders_count,
            "fills_count": self.fills_count,
            "gross_exposure": self.gross_exposure,
            "net_exposure": self.net_exposure,
            "nav": self.nav,
            "cash": self.cash,
            "drawdown": self.drawdown,
            "transaction_costs": self.transaction_costs,
            "borrow_costs": self.borrow_costs,
            "pre_reconciliation_status": self.pre_reconciliation_status,
            "post_reconciliation_status": self.post_reconciliation_status,
            "status": self.status.value,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class DailyPaperReport:
    """Human-readable and machine-readable execution report for a daily paper trading cycle."""
    run_id: str
    date_iso: str
    strategy_id: str
    nav: float
    cash: float
    gross_exposure: float
    net_exposure: float
    orders: list[dict[str, Any]] = field(default_factory=list)
    fills: list[dict[str, Any]] = field(default_factory=list)
    transaction_costs: float = 0.0
    borrow_costs: float = 0.0
    risk_decision: dict[str, Any] = field(default_factory=dict)
    pre_reconciliation_status: str = "UNKNOWN"
    post_reconciliation_status: str = "UNKNOWN"
    target_weights: dict[str, float] = field(default_factory=dict)
    actual_holdings: dict[str, float] = field(default_factory=dict)
    weight_drift: dict[str, float] = field(default_factory=dict)
    executed_changes: dict[str, float] = field(default_factory=dict)
    final_run_status: RunStatus = RunStatus.COMPLETED

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "date_iso": self.date_iso,
            "strategy_id": self.strategy_id,
            "nav": self.nav,
            "cash": self.cash,
            "gross_exposure": self.gross_exposure,
            "net_exposure": self.net_exposure,
            "orders": self.orders,
            "fills": self.fills,
            "transaction_costs": self.transaction_costs,
            "borrow_costs": self.borrow_costs,
            "risk_decision": self.risk_decision,
            "pre_reconciliation_status": self.pre_reconciliation_status,
            "post_reconciliation_status": self.post_reconciliation_status,
            "target_weights": self.target_weights,
            "actual_holdings": self.actual_holdings,
            "weight_drift": self.weight_drift,
            "executed_changes": self.executed_changes,
            "final_run_status": self.final_run_status.value,
        }

    def to_text_report(self) -> str:
        lines = [
            "=" * 60,
            f"DAILY PAPER EXECUTION REPORT — {self.date_iso}",
            "=" * 60,
            f"Run ID:            {self.run_id}",
            f"Strategy:          {self.strategy_id}",
            f"Status:            {self.final_run_status.value}",
            f"Pre-Reconciliation: {self.pre_reconciliation_status}",
            f"Post-Reconciliation:{self.post_reconciliation_status}",
            f"Portfolio NAV:     ${self.nav:,.2f}",
            f"Cash Balance:      ${self.cash:,.2f}",
            f"Gross Exposure:    {self.gross_exposure*100:.2f}%",
            f"Net Exposure:      {self.net_exposure*100:.2f}%",
            f"Orders Generated:  {len(self.orders)}",
            f"Fills Executed:    {len(self.fills)}",
            f"Transaction Costs: ${self.transaction_costs:.2f}",
            f"Borrow Costs:      ${self.borrow_costs:.2f}",
            "-" * 60,
            "Target Weights vs. Actual Holdings:",
        ]
        all_syms = sorted(set(self.target_weights.keys()) | set(self.actual_holdings.keys()))
        for sym in all_syms:
            tw = self.target_weights.get(sym, 0.0)
            aw = self.actual_holdings.get(sym, 0.0)
            drift = self.weight_drift.get(sym, aw - tw)
            chg = self.executed_changes.get(sym, 0.0)
            lines.append(f"  {sym:<6}: Target={tw:>7.2%} | Actual={aw:>7.2%} | Drift={drift:>7.2%} | Trade={chg:>+8.1f} shs")
        lines.append("=" * 60)
        return "\n".join(lines)


@dataclass
class ValidationLedgerSummary:
    """Cumulative statistics across multi-day paper validation runs."""
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    risk_rejections: int = 0
    reconciliation_failures: int = 0
    data_failures: int = 0
    broker_rejections: int = 0
    partial_fills: int = 0
    duplicate_order_attempts: int = 0
    duplicate_fill_attempts: int = 0
    restarts: int = 0
    recovery_events: int = 0
    unexplained_accounting_differences: int = 0
    cumulative_transaction_costs: float = 0.0
    cumulative_borrow_costs: float = 0.0
    cumulative_slippage: float = 0.0
    cumulative_turnover: float = 0.0
    max_drawdown: float = 0.0
    initial_nav: float = 0.0
    final_nav: float = 0.0
    nav_path: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_runs": self.total_runs,
            "successful_runs": self.successful_runs,
            "failed_runs": self.failed_runs,
            "risk_rejections": self.risk_rejections,
            "reconciliation_failures": self.reconciliation_failures,
            "data_failures": self.data_failures,
            "broker_rejections": self.broker_rejections,
            "partial_fills": self.partial_fills,
            "duplicate_order_attempts": self.duplicate_order_attempts,
            "duplicate_fill_attempts": self.duplicate_fill_attempts,
            "restarts": self.restarts,
            "recovery_events": self.recovery_events,
            "unexplained_accounting_differences": self.unexplained_accounting_differences,
            "cumulative_transaction_costs": self.cumulative_transaction_costs,
            "cumulative_borrow_costs": self.cumulative_borrow_costs,
            "cumulative_slippage": self.cumulative_slippage,
            "cumulative_turnover": self.cumulative_turnover,
            "max_drawdown": self.max_drawdown,
            "initial_nav": self.initial_nav,
            "final_nav": self.final_nav,
            "nav_path": self.nav_path,
        }
