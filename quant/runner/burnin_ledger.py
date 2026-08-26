"""Persistent P8.5 Burn-In Ledger repository and audit summary structures."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..core.enums import OrderSide, OrderStatus, OrderType
from ..persistence.database import DatabaseManager


@dataclass(frozen=True)
class BurnInRecord:
    """Audit record for an individual order executed during the P8.5 burn-in."""
    timestamp: datetime
    run_id: str
    order_batch_id: str
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType
    broker_order_id: str
    broker_execution_id: str
    approval_token_id: str
    risk_decision_id: str
    pre_reconciliation_status: str
    post_reconciliation_status: str
    final_order_status: OrderStatus
    success: bool
    sequence_num: int | None = None
    requested_price: float | None = None
    executed_price: float | None = None
    commission: float = 0.0
    slippage: float = 0.0
    failure_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BurnInSummary:
    """Aggregated audit metrics for the 10-order burn-in gate."""
    total_orders_attempted: int
    successful_real_paper_orders: int
    failed_orders: int
    reconciliation_match_rate: float
    total_commission_paid: float
    is_p85_complete: bool
    burnin_status: str  # e.g. "10 / 10 (COMPLETE)" or "X / 10 (IN_PROGRESS)"


class BurnInLedgerRepository:
    """SQLite-backed persistent state store for the P8.5 Burn-In Ledger."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    def record_order(self, record: BurnInRecord, conn: sqlite3.Connection | None = None) -> int:
        """Appends a new verified order record to the burn-in ledger and returns its sequence number."""
        sql = """
        INSERT INTO p85_burnin_ledger (
            timestamp, run_id, order_batch_id, symbol, side,
            quantity, order_type, requested_price, executed_price,
            broker_order_id, broker_execution_id, commission, slippage,
            approval_token_id, risk_decision_id, pre_reconciliation_status,
            post_reconciliation_status, final_order_status, success,
            failure_reason, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        params = (
            record.timestamp.isoformat(),
            record.run_id,
            record.order_batch_id,
            record.symbol,
            record.side.value,
            record.quantity,
            record.order_type.value,
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
            record.final_order_status.value,
            1 if record.success else 0,
            record.failure_reason,
            json.dumps(record.metadata),
        )
        if conn is not None:
            cur = conn.execute(sql, params)
            return cur.lastrowid
        else:
            with self._db.get_connection() as c:
                cur = c.execute(sql, params)
                return cur.lastrowid

    def get_successful_count(self, conn: sqlite3.Connection | None = None) -> int:
        """Derives the exact count of verified successful paper orders from persisted database state."""
        sql = "SELECT COUNT(*) FROM p85_burnin_ledger WHERE success = 1;"
        if conn is not None:
            return conn.execute(sql).fetchone()[0]
        with self._db.get_connection() as c:
            return c.execute(sql).fetchone()[0]

    def get_failure_count(self, conn: sqlite3.Connection | None = None) -> int:
        """Counts orders marked as failures."""
        sql = "SELECT COUNT(*) FROM p85_burnin_ledger WHERE success = 0;"
        if conn is not None:
            return conn.execute(sql).fetchone()[0]
        with self._db.get_connection() as c:
            return c.execute(sql).fetchone()[0]

    def get_all_records(self, conn: sqlite3.Connection | None = None) -> list[BurnInRecord]:
        """Retrieves all burn-in order records in sequence order."""
        sql = "SELECT * FROM p85_burnin_ledger ORDER BY sequence_num ASC;"
        rows = conn.execute(sql).fetchall() if conn is not None else self._db.get_connection().__enter__().execute(sql).fetchall()

        records = []
        for r in rows:
            row_dict = dict(r)
            records.append(
                BurnInRecord(
                    sequence_num=row_dict["sequence_num"],
                    timestamp=datetime.fromisoformat(row_dict["timestamp"]),
                    run_id=row_dict["run_id"],
                    order_batch_id=row_dict["order_batch_id"],
                    symbol=row_dict["symbol"],
                    side=OrderSide(row_dict["side"]),
                    quantity=row_dict["quantity"],
                    order_type=OrderType(row_dict["order_type"]),
                    requested_price=row_dict["requested_price"],
                    executed_price=row_dict["executed_price"],
                    broker_order_id=row_dict["broker_order_id"],
                    broker_execution_id=row_dict["broker_execution_id"],
                    commission=row_dict["commission"],
                    slippage=row_dict["slippage"],
                    approval_token_id=row_dict["approval_token_id"],
                    risk_decision_id=row_dict["risk_decision_id"],
                    pre_reconciliation_status=row_dict["pre_reconciliation_status"],
                    post_reconciliation_status=row_dict["post_reconciliation_status"],
                    final_order_status=OrderStatus(row_dict["final_order_status"]),
                    success=bool(row_dict["success"]),
                    failure_reason=row_dict["failure_reason"],
                    metadata=json.loads(row_dict["metadata_json"] or "{}"),
                )
            )
        return records

    def get_burnin_summary(self) -> BurnInSummary:
        """Aggregates burn-in progress and verification metrics."""
        records = self.get_all_records()
        total = len(records)
        succ = sum(1 for r in records if r.success)
        failed = total - succ
        comm = sum(r.commission for r in records)
        match_count = sum(1 for r in records if r.post_reconciliation_status == "MATCHED")
        rate = (match_count / total) if total > 0 else 1.0
        complete = succ >= 10 and rate == 1.0

        return BurnInSummary(
            total_orders_attempted=total,
            successful_real_paper_orders=succ,
            failed_orders=failed,
            reconciliation_match_rate=rate,
            total_commission_paid=comm,
            is_p85_complete=complete,
            burnin_status=f"{succ} / 10 ({'COMPLETE' if complete else 'IN_PROGRESS'})",
        )
