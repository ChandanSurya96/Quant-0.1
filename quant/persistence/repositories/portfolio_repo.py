"""Repository for strategy-generated target portfolios."""

from __future__ import annotations

from datetime import datetime
import json
import sqlite3

from ...core.interfaces import TargetPortfolio
from ..database import DatabaseManager


class TargetPortfolioRepository:
    """Persists and retrieves target portfolio allocation records."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    def save_target_portfolio(
        self,
        portfolio_id: str,
        target_portfolio: TargetPortfolio,
        run_id: str,
        nav_reference: float | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Persists a strategy-generated TargetPortfolio."""
        weights_json = json.dumps(target_portfolio.target_weights)
        meta_json = json.dumps(target_portfolio.metadata)
        created_iso = target_portfolio.timestamp.isoformat()

        sql = """
        INSERT INTO target_portfolios (
            portfolio_id, run_id, strategy_id, created_at, rebalance_horizon,
            weights_json, nav_reference, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        params = (
            portfolio_id,
            run_id,
            target_portfolio.strategy_id,
            created_iso,
            target_portfolio.rebalance_horizon,
            weights_json,
            nav_reference,
            meta_json,
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            with self._db.get_connection() as c:
                c.execute(sql, params)

    def get_target_portfolio(
        self,
        portfolio_id: str,
        conn: sqlite3.Connection | None = None,
    ) -> TargetPortfolio | None:
        """Retrieves a TargetPortfolio by portfolio_id."""
        sql = "SELECT * FROM target_portfolios WHERE portfolio_id = ?;"
        if conn is not None:
            row = conn.execute(sql, (portfolio_id,)).fetchone()
        else:
            with self._db.get_connection() as c:
                row = c.execute(sql, (portfolio_id,)).fetchone()

        if not row:
            return None

        return TargetPortfolio(
            timestamp=datetime.fromisoformat(row["created_at"]),
            strategy_id=row["strategy_id"],
            target_weights=json.loads(row["weights_json"]),
            rebalance_horizon=int(row["rebalance_horizon"]),
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    def get_latest_target_portfolio(
        self,
        strategy_id: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> TargetPortfolio | None:
        """Retrieves the most recent TargetPortfolio."""
        if strategy_id:
            sql = "SELECT * FROM target_portfolios WHERE strategy_id = ? ORDER BY created_at DESC LIMIT 1;"
            params = (strategy_id,)
        else:
            sql = "SELECT * FROM target_portfolios ORDER BY created_at DESC LIMIT 1;"
            params = ()

        if conn is not None:
            row = conn.execute(sql, params).fetchone()
        else:
            with self._db.get_connection() as c:
                row = c.execute(sql, params).fetchone()

        if not row:
            return None

        return TargetPortfolio(
            timestamp=datetime.fromisoformat(row["created_at"]),
            strategy_id=row["strategy_id"],
            target_weights=json.loads(row["weights_json"]),
            rebalance_horizon=int(row["rebalance_horizon"]),
            metadata=json.loads(row["metadata_json"] or "{}"),
        )
