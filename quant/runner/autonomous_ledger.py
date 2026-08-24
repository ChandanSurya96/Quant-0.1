"""Persistent state store and repository for P9 Controlled Autonomous Execution Ledger."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import sqlite3
from typing import Any

from ..persistence.database import DatabaseManager


@dataclass(frozen=True)
class AutonomousRunRecord:
    """Audit record for an autonomous execution cycle."""
    run_id: str
    trading_date: str  # YYYY-MM-DD
    strategy_id: str
    timestamp: datetime
    status: str  # STARTED, APPROVED, REJECTED, EXECUTED, COMPLETED, BLOCKED, RECOVERY_REQUIRED
    order_batch_id: str | None = None
    target_portfolio_id: str | None = None
    risk_decision_id: str | None = None
    approval_token_id: str | None = None
    orders_count: int = 0
    fills_count: int = 0
    gross_exposure: float = 0.0
    net_exposure: float = 0.0
    nav: float = 0.0
    cash: float = 0.0
    pre_reconciliation_status: str = "UNKNOWN"
    post_reconciliation_status: str = "UNKNOWN"
    rejection_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AutonomousRunSummary:
    """Summary of daily autonomous operations."""
    trading_date: str
    total_runs: int
    executed_batches: int
    blocked_runs: int
    daily_limit_reached: bool
    nav: float
    cash: float
    reconciliation_matched: bool


class AutonomousLedgerRepository:
    """SQLite-backed persistent repository for P9 autonomous execution records."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    def record_run(self, record: AutonomousRunRecord, conn: sqlite3.Connection | None = None) -> None:
        """Persists or updates an autonomous run record."""
        sql = """
        INSERT OR REPLACE INTO p9_autonomous_ledger (
            run_id, trading_date, strategy_id, timestamp,
            order_batch_id, target_portfolio_id, risk_decision_id,
            approval_token_id, orders_count, fills_count,
            gross_exposure, net_exposure, nav, cash,
            pre_reconciliation_status, post_reconciliation_status,
            status, rejection_reason, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        params = (
            record.run_id,
            record.trading_date,
            record.strategy_id,
            record.timestamp.isoformat(),
            record.order_batch_id,
            record.target_portfolio_id,
            record.risk_decision_id,
            record.approval_token_id,
            record.orders_count,
            record.fills_count,
            record.gross_exposure,
            record.net_exposure,
            record.nav,
            record.cash,
            record.pre_reconciliation_status,
            record.post_reconciliation_status,
            record.status,
            record.rejection_reason,
            json.dumps(record.metadata),
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            with self._db.get_connection() as c:
                c.execute(sql, params)

    def get_daily_batch_count(self, trading_date: str, conn: sqlite3.Connection | None = None) -> int:
        """Counts the number of executed/approved order batches on a given trading date (persisted across restarts)."""
        sql = """
        SELECT COUNT(*) FROM p9_autonomous_ledger
        WHERE trading_date = ? AND status IN ('APPROVED', 'EXECUTED', 'COMPLETED');
        """
        if conn is not None:
            return conn.execute(sql, (trading_date,)).fetchone()[0]
        with self._db.get_connection() as c:
            return c.execute(sql, (trading_date,)).fetchone()[0]

    def get_run(self, run_id: str, conn: sqlite3.Connection | None = None) -> AutonomousRunRecord | None:
        """Retrieves an autonomous run record by run_id."""
        sql = "SELECT * FROM p9_autonomous_ledger WHERE run_id = ?;"
        row = conn.execute(sql, (run_id,)).fetchone() if conn is not None else self._db.get_connection().__enter__().execute(sql, (run_id,)).fetchone()
        if not row:
            return None
        row_dict = dict(row)
        return AutonomousRunRecord(
            run_id=row_dict["run_id"],
            trading_date=row_dict["trading_date"],
            strategy_id=row_dict["strategy_id"],
            timestamp=datetime.fromisoformat(row_dict["timestamp"]),
            status=row_dict["status"],
            order_batch_id=row_dict["order_batch_id"],
            target_portfolio_id=row_dict["target_portfolio_id"],
            risk_decision_id=row_dict["risk_decision_id"],
            approval_token_id=row_dict["approval_token_id"],
            orders_count=row_dict["orders_count"],
            fills_count=row_dict["fills_count"],
            gross_exposure=row_dict["gross_exposure"],
            net_exposure=row_dict["net_exposure"],
            nav=row_dict["nav"],
            cash=row_dict["cash"],
            pre_reconciliation_status=row_dict["pre_reconciliation_status"],
            post_reconciliation_status=row_dict["post_reconciliation_status"],
            rejection_reason=row_dict["rejection_reason"],
            metadata=json.loads(row_dict["metadata_json"] or "{}"),
        )

    def get_all_records(self, conn: sqlite3.Connection | None = None) -> list[AutonomousRunRecord]:
        """Retrieves all autonomous run records."""
        sql = "SELECT * FROM p9_autonomous_ledger ORDER BY timestamp ASC;"
        rows = conn.execute(sql).fetchall() if conn is not None else self._db.get_connection().__enter__().execute(sql).fetchall()
        records = []
        for r in rows:
            row_dict = dict(r)
            records.append(
                AutonomousRunRecord(
                    run_id=row_dict["run_id"],
                    trading_date=row_dict["trading_date"],
                    strategy_id=row_dict["strategy_id"],
                    timestamp=datetime.fromisoformat(row_dict["timestamp"]),
                    status=row_dict["status"],
                    order_batch_id=row_dict["order_batch_id"],
                    target_portfolio_id=row_dict["target_portfolio_id"],
                    risk_decision_id=row_dict["risk_decision_id"],
                    approval_token_id=row_dict["approval_token_id"],
                    orders_count=row_dict["orders_count"],
                    fills_count=row_dict["fills_count"],
                    gross_exposure=row_dict["gross_exposure"],
                    net_exposure=row_dict["net_exposure"],
                    nav=row_dict["nav"],
                    cash=row_dict["cash"],
                    pre_reconciliation_status=row_dict["pre_reconciliation_status"],
                    post_reconciliation_status=row_dict["post_reconciliation_status"],
                    rejection_reason=row_dict["rejection_reason"],
                    metadata=json.loads(row_dict["metadata_json"] or "{}"),
                )
            )
        return records
