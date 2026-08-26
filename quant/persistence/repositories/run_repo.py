"""Repository for execution run tracking."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from ...core.enums import ExecutionMode
from ..database import DatabaseManager


class RunRepository:
    """Persists and retrieves system execution run records."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    def create_run(
        self,
        run_id: str,
        execution_mode: ExecutionMode,
        strategy_id: str,
        started_at: datetime | None = None,
        metadata: dict | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Records a new system execution run."""
        started_iso = (started_at or datetime.now(timezone.utc)).isoformat()
        meta_json = json.dumps(metadata or {})
        sql = """
        INSERT INTO system_runs (run_id, execution_mode, strategy_id, started_at, status, metadata_json)
        VALUES (?, ?, ?, ?, 'RUNNING', ?);
        """
        if conn is not None:
            conn.execute(sql, (run_id, execution_mode.value, strategy_id, started_iso, meta_json))
        else:
            with self._db.get_connection() as c:
                c.execute(sql, (run_id, execution_mode.value, strategy_id, started_iso, meta_json))

    def complete_run(
        self,
        run_id: str,
        status: str = "SUCCESS",
        error_message: str | None = None,
        completed_at: datetime | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Marks a system execution run as completed."""
        completed_iso = (completed_at or datetime.now(timezone.utc)).isoformat()
        sql = """
        UPDATE system_runs
        SET status = ?, completed_at = ?, error_message = ?
        WHERE run_id = ?;
        """
        if conn is not None:
            conn.execute(sql, (status, completed_iso, error_message, run_id))
        else:
            with self._db.get_connection() as c:
                c.execute(sql, (status, completed_iso, error_message, run_id))

    def get_run(self, run_id: str, conn: sqlite3.Connection | None = None) -> dict | None:
        """Retrieves run details by run_id."""
        sql = "SELECT * FROM system_runs WHERE run_id = ?;"
        if conn is not None:
            row = conn.execute(sql, (run_id,)).fetchone()
        else:
            with self._db.get_connection() as c:
                row = c.execute(sql, (run_id,)).fetchone()
        return dict(row) if row else None

    def run_exists(self, run_id: str, conn: sqlite3.Connection | None = None) -> bool:
        """Checks if a run record exists."""
        return self.get_run(run_id, conn=conn) is not None

    def get_latest_run(
        self,
        strategy_id: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> dict | None:
        """Retrieves the most recent system run."""
        if strategy_id:
            sql = "SELECT * FROM system_runs WHERE strategy_id = ? ORDER BY started_at DESC LIMIT 1;"
            params = (strategy_id,)
        else:
            sql = "SELECT * FROM system_runs ORDER BY started_at DESC LIMIT 1;"
            params = ()

        if conn is not None:
            row = conn.execute(sql, params).fetchone()
        else:
            with self._db.get_connection() as c:
                row = c.execute(sql, params).fetchone()
        return dict(row) if row else None
