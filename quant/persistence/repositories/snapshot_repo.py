"""Repository for portfolio mark-to-market state snapshots."""

from __future__ import annotations

import json
import sqlite3

from ...core.enums import ExecutionMode
from ...core.interfaces import PortfolioState
from ..database import DatabaseManager


class SnapshotRepository:
    """Persists and retrieves point-in-time portfolio mark-to-market snapshots."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    def save_snapshot(
        self,
        snapshot_id: str,
        run_id: str,
        state: PortfolioState,
        execution_mode: ExecutionMode,
        strategy_id: str,
        realized_pnl: float = 0.0,
        unrealized_pnl: float = 0.0,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Persists a PortfolioState snapshot."""
        weights_json = json.dumps(state.realized_weights)
        time_iso = state.timestamp.isoformat()

        gross_exp = sum(abs(h.market_value) for h in state.holdings.values())
        net_exp = sum(h.market_value for h in state.holdings.values())

        sql = """
        INSERT INTO portfolio_snapshots (
            snapshot_id, run_id, timestamp, execution_mode, strategy_id,
            nav, cash, gross_exposure, net_exposure, realized_pnl,
            unrealized_pnl, realized_weights_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        params = (
            snapshot_id,
            run_id,
            time_iso,
            execution_mode.value,
            strategy_id,
            state.nav,
            state.cash,
            gross_exp,
            net_exp,
            realized_pnl,
            unrealized_pnl,
            weights_json,
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            with self._db.get_connection() as c:
                c.execute(sql, params)

    def get_snapshot(
        self,
        snapshot_id: str,
        conn: sqlite3.Connection | None = None,
    ) -> dict | None:
        """Retrieves a snapshot by snapshot_id."""
        sql = "SELECT * FROM portfolio_snapshots WHERE snapshot_id = ?;"
        if conn is not None:
            row = conn.execute(sql, (snapshot_id,)).fetchone()
        else:
            with self._db.get_connection() as c:
                row = c.execute(sql, (snapshot_id,)).fetchone()

        return dict(row) if row else None

    def get_latest_snapshot(
        self,
        strategy_id: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> dict | None:
        """Retrieves the most recent portfolio snapshot."""
        if strategy_id:
            sql = "SELECT * FROM portfolio_snapshots WHERE strategy_id = ? ORDER BY timestamp DESC LIMIT 1;"
            params = (strategy_id,)
        else:
            sql = "SELECT * FROM portfolio_snapshots ORDER BY timestamp DESC LIMIT 1;"
            params = ()

        if conn is not None:
            row = conn.execute(sql, params).fetchone()
        else:
            with self._db.get_connection() as c:
                row = c.execute(sql, params).fetchone()

        return dict(row) if row else None

    def get_peak_nav(
        self,
        strategy_id: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> float:
        """Retrieves the maximum historical NAV recorded for a strategy."""
        if strategy_id:
            sql = "SELECT MAX(nav) FROM portfolio_snapshots WHERE strategy_id = ?;"
            params = (strategy_id,)
        else:
            sql = "SELECT MAX(nav) FROM portfolio_snapshots;"
            params = ()

        if conn is not None:
            res = conn.execute(sql, params).fetchone()[0]
        else:
            with self._db.get_connection() as c:
                res = c.execute(sql, params).fetchone()[0]
        return float(res) if res is not None else 0.0
