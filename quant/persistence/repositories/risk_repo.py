"""Repository for pre-trade risk evaluation decisions."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from ...core.interfaces import RiskDecision
from ..database import DatabaseManager


class RiskEvaluationRepository:
    """Persists and retrieves RiskDecision records and evaluated risk metrics."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    def save_risk_evaluation(
        self,
        decision: RiskDecision,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Persists a pre-trade RiskDecision record."""
        time_iso = decision.timestamp.isoformat()
        adj_json = json.dumps(decision.adjusted_weights)
        violations_str = "; ".join(decision.violations) if decision.violations else ""
        meta_dict = {
            "metrics": decision.metrics,
            "strategy_id": decision.strategy_id,
            "violations": decision.violations,
            **(decision.metadata or {}),
        }
        meta_json = json.dumps(meta_dict)

        sql = """
        INSERT INTO risk_evaluations (
            evaluation_id, portfolio_id, evaluated_at, approved,
            adjusted_weights_json, reason, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """
        params = (
            decision.decision_id,
            decision.portfolio_id,
            time_iso,
            1 if decision.approved else 0,
            adj_json,
            violations_str,
            meta_json,
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            with self._db.get_connection() as c:
                c.execute(sql, params)

    def get_risk_evaluation(
        self,
        evaluation_id: str,
        conn: sqlite3.Connection | None = None,
    ) -> RiskDecision | None:
        """Retrieves a RiskDecision by evaluation_id."""
        sql = "SELECT * FROM risk_evaluations WHERE evaluation_id = ?;"
        if conn is not None:
            row = conn.execute(sql, (evaluation_id,)).fetchone()
        else:
            with self._db.get_connection() as c:
                row = c.execute(sql, (evaluation_id,)).fetchone()

        if not row:
            return None

        meta_dict = json.loads(row["metadata_json"] or "{}")
        metrics = meta_dict.get("metrics", {})
        violations = meta_dict.get("violations", [row["reason"]] if row["reason"] else [])

        return RiskDecision(
            decision_id=row["evaluation_id"],
            portfolio_id=row["portfolio_id"],
            strategy_id=meta_dict.get("strategy_id", ""),
            timestamp=datetime.fromisoformat(row["evaluated_at"]),
            approved=bool(row["approved"]),
            violations=violations,
            adjusted_weights=json.loads(row["adjusted_weights_json"] or "{}"),
            metrics=metrics,
            metadata=meta_dict,
        )

    def get_latest_risk_evaluation(
        self,
        portfolio_id: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> RiskDecision | None:
        """Retrieves the most recent RiskDecision."""
        if portfolio_id:
            sql = "SELECT * FROM risk_evaluations WHERE portfolio_id = ? ORDER BY evaluated_at DESC LIMIT 1;"
            params = (portfolio_id,)
        else:
            sql = "SELECT * FROM risk_evaluations ORDER BY evaluated_at DESC LIMIT 1;"
            params = ()

        if conn is not None:
            row = conn.execute(sql, params).fetchone()
        else:
            with self._db.get_connection() as c:
                row = c.execute(sql, params).fetchone()

        if not row:
            return None

        meta_dict = json.loads(row["metadata_json"] or "{}")
        metrics = meta_dict.get("metrics", {})
        violations = meta_dict.get("violations", [row["reason"]] if row["reason"] else [])

        return RiskDecision(
            decision_id=row["evaluation_id"],
            portfolio_id=row["portfolio_id"],
            strategy_id=meta_dict.get("strategy_id", ""),
            timestamp=datetime.fromisoformat(row["evaluated_at"]),
            approved=bool(row["approved"]),
            violations=violations,
            adjusted_weights=json.loads(row["adjusted_weights_json"] or "{}"),
            metrics=metrics,
            metadata=meta_dict,
        )
