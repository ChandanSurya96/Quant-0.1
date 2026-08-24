"""Durable paper trading run ledger and cumulative validation analytics."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
from typing import Any

from ..core.enums import ExecutionMode
from ..persistence.database import DatabaseManager
from .models import DailyPaperReport, PaperRunRecord, RunStatus, ValidationLedgerSummary


class PaperRunLedger:
    """Persists and analyzes paper execution session records."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager
        self._records: list[PaperRunRecord] = []
        self._reports: dict[str, DailyPaperReport] = {}

    def record_run(
        self,
        record: PaperRunRecord,
        report: DailyPaperReport | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Persists a paper run record into SQLite and caches in ledger memory."""
        self._records.append(record)
        if report is not None:
            self._reports[record.run_id] = report

        sql = """
        INSERT INTO paper_run_ledger (
            run_id, execution_mode, strategy_id, start_time, end_time,
            data_timestamp, target_portfolio_id, risk_decision_id,
            order_batch_id, orders_count, fills_count, gross_exposure,
            net_exposure, nav, cash, drawdown, transaction_costs,
            borrow_costs, pre_reconciliation_status, post_reconciliation_status,
            status, error_message, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id) DO UPDATE SET
            end_time = excluded.end_time,
            orders_count = excluded.orders_count,
            fills_count = excluded.fills_count,
            gross_exposure = excluded.gross_exposure,
            net_exposure = excluded.net_exposure,
            nav = excluded.nav,
            cash = excluded.cash,
            drawdown = excluded.drawdown,
            transaction_costs = excluded.transaction_costs,
            borrow_costs = excluded.borrow_costs,
            pre_reconciliation_status = excluded.pre_reconciliation_status,
            post_reconciliation_status = excluded.post_reconciliation_status,
            status = excluded.status,
            error_message = excluded.error_message,
            metadata_json = excluded.metadata_json;
        """
        params = (
            record.run_id,
            record.execution_mode.value,
            record.strategy_id,
            record.start_time.isoformat(),
            record.end_time.isoformat() if record.end_time else None,
            record.data_timestamp.isoformat() if record.data_timestamp else None,
            record.target_portfolio_id,
            record.risk_decision_id,
            record.order_batch_id,
            record.orders_count,
            record.fills_count,
            record.gross_exposure,
            record.net_exposure,
            record.nav,
            record.cash,
            record.drawdown,
            record.transaction_costs,
            record.borrow_costs,
            record.pre_reconciliation_status,
            record.post_reconciliation_status,
            record.status.value,
            record.error_message,
            json.dumps(record.metadata),
        )

        if conn is not None:
            conn.execute(sql, params)
        else:
            with self._db.transaction() as c:
                c.execute(sql, params)

    def get_run(self, run_id: str, conn: sqlite3.Connection | None = None) -> PaperRunRecord | None:
        """Fetches a paper run record by ID."""
        sql = "SELECT * FROM paper_run_ledger WHERE run_id = ?;"

        def _fetch(c: sqlite3.Connection) -> PaperRunRecord | None:
            row = c.execute(sql, (run_id,)).fetchone()
            if not row:
                return None
            return PaperRunRecord(
                run_id=row["run_id"],
                execution_mode=ExecutionMode(row["execution_mode"]),
                strategy_id=row["strategy_id"],
                start_time=datetime.fromisoformat(row["start_time"]),
                end_time=datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
                data_timestamp=datetime.fromisoformat(row["data_timestamp"]) if row["data_timestamp"] else None,
                target_portfolio_id=row["target_portfolio_id"],
                risk_decision_id=row["risk_decision_id"],
                order_batch_id=row["order_batch_id"],
                orders_count=row["orders_count"],
                fills_count=row["fills_count"],
                gross_exposure=row["gross_exposure"],
                net_exposure=row["net_exposure"],
                nav=row["nav"],
                cash=row["cash"],
                drawdown=row["drawdown"],
                transaction_costs=row["transaction_costs"],
                borrow_costs=row["borrow_costs"],
                pre_reconciliation_status=row["pre_reconciliation_status"],
                post_reconciliation_status=row["post_reconciliation_status"],
                status=RunStatus(row["status"]),
                error_message=row["error_message"],
                metadata=json.loads(row["metadata_json"] or "{}"),
            )

        if conn is not None:
            return _fetch(conn)
        else:
            with self._db.get_connection() as c:
                return _fetch(c)

    def list_runs(self, conn: sqlite3.Connection | None = None) -> list[PaperRunRecord]:
        """Lists all paper run records chronologically."""
        sql = "SELECT * FROM paper_run_ledger ORDER BY start_time ASC;"

        def _fetch_all(c: sqlite3.Connection) -> list[PaperRunRecord]:
            rows = c.execute(sql).fetchall()
            records: list[PaperRunRecord] = []
            for row in rows:
                records.append(
                    PaperRunRecord(
                        run_id=row["run_id"],
                        execution_mode=ExecutionMode(row["execution_mode"]),
                        strategy_id=row["strategy_id"],
                        start_time=datetime.fromisoformat(row["start_time"]),
                        end_time=datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
                        data_timestamp=datetime.fromisoformat(row["data_timestamp"]) if row["data_timestamp"] else None,
                        target_portfolio_id=row["target_portfolio_id"],
                        risk_decision_id=row["risk_decision_id"],
                        order_batch_id=row["order_batch_id"],
                        orders_count=row["orders_count"],
                        fills_count=row["fills_count"],
                        gross_exposure=row["gross_exposure"],
                        net_exposure=row["net_exposure"],
                        nav=row["nav"],
                        cash=row["cash"],
                        drawdown=row["drawdown"],
                        transaction_costs=row["transaction_costs"],
                        borrow_costs=row["borrow_costs"],
                        pre_reconciliation_status=row["pre_reconciliation_status"],
                        post_reconciliation_status=row["post_reconciliation_status"],
                        status=RunStatus(row["status"]),
                        error_message=row["error_message"],
                        metadata=json.loads(row["metadata_json"] or "{}"),
                    )
                )
            return records

        if conn is not None:
            return _fetch_all(conn)
        else:
            with self._db.get_connection() as c:
                return _fetch_all(c)

    def get_summary(self) -> ValidationLedgerSummary:
        """Computes aggregate multi-day validation statistics."""
        runs = self.list_runs()
        if not runs:
            return ValidationLedgerSummary()

        total = len(runs)
        success = sum(1 for r in runs if r.status == RunStatus.COMPLETED)
        failed = total - success
        risk_rej = sum(1 for r in runs if r.status == RunStatus.RISK_REJECTED)
        rec_fails = sum(1 for r in runs if r.status == RunStatus.RECONCILIATION_FAILED or r.pre_reconciliation_status != "MATCHED")
        data_fails = sum(1 for r in runs if r.status in (RunStatus.DATA_FAILED, RunStatus.VALIDATION_FAILED))
        recov_events = sum(1 for r in runs if r.status == RunStatus.RECOVERY_REQUIRED)

        total_tx_costs = sum(r.transaction_costs for r in runs)
        total_borrow_costs = sum(r.borrow_costs for r in runs)
        max_dd = max((abs(r.drawdown) for r in runs), default=0.0)

        initial_nav = runs[0].nav if runs and runs[0].nav > 0 else 0.0
        final_nav = runs[-1].nav if runs else 0.0

        nav_path = [
            {
                "run_id": r.run_id,
                "timestamp": r.start_time.isoformat(),
                "nav": r.nav,
                "cash": r.cash,
                "drawdown": r.drawdown,
                "status": r.status.value,
            }
            for r in runs
        ]

        return ValidationLedgerSummary(
            total_runs=total,
            successful_runs=success,
            failed_runs=failed,
            risk_rejections=risk_rej,
            reconciliation_failures=rec_fails,
            data_failures=data_fails,
            broker_rejections=0,
            partial_fills=0,
            duplicate_order_attempts=0,
            duplicate_fill_attempts=0,
            restarts=0,
            recovery_events=recov_events,
            unexplained_accounting_differences=0,
            cumulative_transaction_costs=total_tx_costs,
            cumulative_borrow_costs=total_borrow_costs,
            cumulative_slippage=0.0,
            cumulative_turnover=0.0,
            max_drawdown=max_dd,
            initial_nav=initial_nav,
            final_nav=final_nav,
            nav_path=nav_path,
        )
