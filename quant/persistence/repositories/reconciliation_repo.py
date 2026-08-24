"""Repository for portfolio reconciliation results and issues."""

from __future__ import annotations

from datetime import datetime
import json
import sqlite3
import uuid

from ...core.enums import ExecutionMode
from ...reconciliation.types import (
    ReconciliationIssue,
    ReconciliationIssueType,
    ReconciliationResult,
    ReconciliationStatus,
)
from ..database import DatabaseManager


class ReconciliationRepository:
    """Persists and retrieves ReconciliationResult records and discrepancies."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    def save_reconciliation_result(
        self,
        result: ReconciliationResult,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Persists a ReconciliationResult and all child issues in an atomic transaction."""
        time_iso = result.timestamp.isoformat()
        summary_dict = {
            "internal_holdings": result.internal_holdings,
            "broker_positions": result.broker_positions,
            "internal_cash": result.internal_cash,
            "broker_cash": result.broker_cash,
            "internal_nav": result.internal_nav,
            "broker_nav": result.broker_nav,
        }
        summary_json = json.dumps(summary_dict)

        sql_run = """
        INSERT INTO reconciliation_runs (
            reconciliation_id, run_id, timestamp, execution_mode,
            status, issues_count, summary_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """
        run_params = (
            result.reconciliation_id,
            result.run_id,
            time_iso,
            result.execution_mode.value,
            result.status.value,
            len(result.issues),
            summary_json,
        )

        def _execute_save(c: sqlite3.Connection) -> None:
            c.execute(sql_run, run_params)
            for issue in result.issues:
                issue_id = f"iss_{uuid.uuid4().hex[:12]}"
                sql_issue = """
                INSERT INTO reconciliation_issues (
                    issue_id, reconciliation_id, issue_type, symbol,
                    order_id, fill_id, internal_value, broker_value,
                    discrepancy, message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """
                c.execute(
                    sql_issue,
                    (
                        issue_id,
                        result.reconciliation_id,
                        issue.issue_type.value,
                        issue.symbol,
                        issue.order_id,
                        issue.fill_id,
                        float(issue.internal_value) if isinstance(issue.internal_value, (int, float)) else None,
                        float(issue.broker_value) if isinstance(issue.broker_value, (int, float)) else None,
                        issue.discrepancy,
                        issue.message,
                    ),
                )

        if conn is not None:
            _execute_save(conn)
        else:
            with self._db.transaction() as c:
                _execute_save(c)

    def get_reconciliation_result(
        self,
        reconciliation_id: str,
        conn: sqlite3.Connection | None = None,
    ) -> ReconciliationResult | None:
        """Retrieves a ReconciliationResult by reconciliation_id."""
        sql_run = "SELECT * FROM reconciliation_runs WHERE reconciliation_id = ?;"
        sql_issues = "SELECT * FROM reconciliation_issues WHERE reconciliation_id = ?;"

        def _fetch(c: sqlite3.Connection) -> ReconciliationResult | None:
            row = c.execute(sql_run, (reconciliation_id,)).fetchone()
            if not row:
                return None
            issue_rows = c.execute(sql_issues, (reconciliation_id,)).fetchall()
            issues = [
                ReconciliationIssue(
                    issue_type=ReconciliationIssueType(i["issue_type"]),
                    symbol=i["symbol"],
                    order_id=i["order_id"],
                    fill_id=i["fill_id"],
                    internal_value=i["internal_value"],
                    broker_value=i["broker_value"],
                    discrepancy=i["discrepancy"],
                    message=i["message"],
                )
                for i in issue_rows
            ]
            summary = json.loads(row["summary_json"] or "{}")
            return ReconciliationResult(
                reconciliation_id=row["reconciliation_id"],
                run_id=row["run_id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                execution_mode=ExecutionMode(row["execution_mode"]),
                status=ReconciliationStatus(row["status"]),
                issues=issues,
                internal_holdings=summary.get("internal_holdings", {}),
                broker_positions=summary.get("broker_positions", {}),
                internal_cash=summary.get("internal_cash", 0.0),
                broker_cash=summary.get("broker_cash", 0.0),
                internal_nav=summary.get("internal_nav", 0.0),
                broker_nav=summary.get("broker_nav", 0.0),
            )

        if conn is not None:
            return _fetch(conn)
        else:
            with self._db.get_connection() as c:
                return _fetch(c)
