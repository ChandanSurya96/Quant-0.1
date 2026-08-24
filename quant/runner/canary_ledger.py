"""Persistent canary ledger and audit evidence store for P9.1 Controlled Autonomous Live Canary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import sqlite3
from typing import Any

from ..persistence.database import DatabaseManager


@dataclass(frozen=True)
class CanaryRecord:
    """Audit record for an autonomous live canary execution."""
    sequence_num: int | None
    timestamp: datetime
    run_id: str
    canary_run_id: str
    order_batch_id: str
    symbol: str
    side: str
    quantity: float
    order_type: str
    broker_order_id: str
    broker_execution_id: str
    approval_token_id: str
    risk_decision_id: str
    pre_reconciliation_status: str
    post_reconciliation_status: str
    final_order_status: str
    success: bool
    requested_price: float | None = None
    executed_price: float | None = None
    commission: float = 0.0
    slippage: float = 0.0
    failure_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanarySummary:
    """Summary metrics for P9.1 Autonomous Live Canary."""
    total_orders_attempted: int
    successful_executions: int
    failed_executions: int
    reconciliation_mismatches: int
    duplicate_executions_detected: int
    all_reconciliations_passed: bool
    canary_complete: bool


class CanaryLedgerRepository:
    """Persistent SQLite repository for P9.1 autonomous live canary audit records."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    def record_execution(self, record: CanaryRecord, conn: sqlite3.Connection | None = None) -> None:
        """Persists a canary execution record to SQLite."""
        sql = """
        INSERT INTO p91_canary_ledger (
            timestamp, run_id, canary_run_id, order_batch_id, symbol,
            side, quantity, order_type, requested_price, executed_price,
            broker_order_id, broker_execution_id, commission, slippage,
            approval_token_id, risk_decision_id, pre_reconciliation_status,
            post_reconciliation_status, final_order_status, success,
            failure_reason, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        params = (
            record.timestamp.isoformat(),
            record.run_id,
            record.canary_run_id,
            record.order_batch_id,
            record.symbol,
            record.side,
            record.quantity,
            record.order_type,
            record.requested_price,
            record.executed_price,
            record.broker_order_id,
            record.broker_execution_id,
            record.commission,
            record.slippage,
            record.approval_token_id,
            record.risk_decision_id,
            record.pre_reconciliation_status,
            record.post_reconciliation_status,
            record.final_order_status,
            1 if record.success else 0,
            record.failure_reason,
            json.dumps(record.metadata),
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            with self._db.get_connection() as c:
                c.execute(sql, params)

    def get_successful_count(self, conn: sqlite3.Connection | None = None) -> int:
        """Returns the verified count of successful autonomous live executions."""
        sql = "SELECT COUNT(*) FROM p91_canary_ledger WHERE success = 1;"
        if conn is not None:
            return conn.execute(sql).fetchone()[0]
        with self._db.get_connection() as c:
            return c.execute(sql).fetchone()[0]

    def get_failure_count(self, conn: sqlite3.Connection | None = None) -> int:
        """Returns the count of failed canary execution attempts."""
        sql = "SELECT COUNT(*) FROM p91_canary_ledger WHERE success = 0;"
        if conn is not None:
            return conn.execute(sql).fetchone()[0]
        with self._db.get_connection() as c:
            return c.execute(sql).fetchone()[0]

    def get_all_records(self, conn: sqlite3.Connection | None = None) -> list[CanaryRecord]:
        """Retrieves all canary records in chronological sequence."""
        sql = "SELECT * FROM p91_canary_ledger ORDER BY sequence_num ASC;"
        rows = conn.execute(sql).fetchall() if conn is not None else self._db.get_connection().__enter__().execute(sql).fetchall()
        records = []
        for r in rows:
            row_dict = dict(r)
            records.append(
                CanaryRecord(
                    sequence_num=row_dict["sequence_num"],
                    timestamp=datetime.fromisoformat(row_dict["timestamp"]),
                    run_id=row_dict["run_id"],
                    canary_run_id=row_dict["canary_run_id"],
                    order_batch_id=row_dict["order_batch_id"],
                    symbol=row_dict["symbol"],
                    side=row_dict["side"],
                    quantity=row_dict["quantity"],
                    order_type=row_dict["order_type"],
                    requested_price=row_dict["requested_price"],
                    executed_price=row_dict["executed_price"],
                    broker_order_id=row_dict["broker_order_id"],
                    broker_execution_id=row_dict["broker_execution_id"],
                    commission=row_dict["commission"],
                    slippage=row_dict["slippage"] or 0.0,
                    approval_token_id=row_dict["approval_token_id"],
                    risk_decision_id=row_dict["risk_decision_id"],
                    pre_reconciliation_status=row_dict["pre_reconciliation_status"],
                    post_reconciliation_status=row_dict["post_reconciliation_status"],
                    final_order_status=row_dict["final_order_status"],
                    success=bool(row_dict["success"]),
                    failure_reason=row_dict["failure_reason"],
                    metadata=json.loads(row_dict["metadata_json"] or "{}"),
                )
            )
        return records

    def get_canary_summary(self, conn: sqlite3.Connection | None = None) -> CanarySummary:
        """Calculates derived metrics from the persisted ledger."""
        records = self.get_all_records(conn=conn)
        total = len(records)
        succ = sum(1 for r in records if r.success)
        fail = sum(1 for r in records if not r.success)
        rec_mismatches = sum(1 for r in records if r.pre_reconciliation_status != "MATCHED" or r.post_reconciliation_status != "MATCHED")

        exec_ids = [r.broker_execution_id for r in records if r.broker_execution_id]
        duplicates = len(exec_ids) - len(set(exec_ids))

        return CanarySummary(
            total_orders_attempted=total,
            successful_executions=succ,
            failed_executions=fail,
            reconciliation_mismatches=rec_mismatches,
            duplicate_executions_detected=duplicates,
            all_reconciliations_passed=(rec_mismatches == 0 and succ > 0),
            canary_complete=(succ >= 10 and fail == 0 and rec_mismatches == 0 and duplicates == 0),
        )
