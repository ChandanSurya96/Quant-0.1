"""Repository for fill and execution records."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ...core.enums import OrderSide
from ...core.interfaces import Fill
from ..database import DatabaseManager


class FillRepository:
    """Persists and retrieves fill execution records."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    def save_fill(
        self,
        fill: Fill,
        broker_execution_id: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Persists a trade fill event."""
        filled_iso = fill.timestamp.isoformat()
        sql = """
        INSERT INTO fills (
            fill_id, broker_execution_id, order_id, symbol, side,
            quantity, fill_price, commission, filled_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        params = (
            fill.fill_id,
            broker_execution_id or fill.fill_id,
            fill.order_id,
            fill.symbol,
            fill.side.value,
            fill.quantity,
            fill.fill_price,
            fill.commission,
            filled_iso,
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            with self._db.get_connection() as c:
                c.execute(sql, params)

    def get_fill(self, fill_id: str, conn: sqlite3.Connection | None = None) -> Fill | None:
        """Retrieves a fill by fill_id."""
        sql = "SELECT * FROM fills WHERE fill_id = ?;"
        if conn is not None:
            row = conn.execute(sql, (fill_id,)).fetchone()
        else:
            with self._db.get_connection() as c:
                row = c.execute(sql, (fill_id,)).fetchone()

        if not row:
            return None

        return Fill(
            fill_id=row["fill_id"],
            order_id=row["order_id"],
            symbol=row["symbol"],
            side=OrderSide(row["side"]),
            quantity=float(row["quantity"]),
            fill_price=float(row["fill_price"]),
            commission=float(row["commission"]),
            timestamp=datetime.fromisoformat(row["filled_at"]),
        )

    def get_fill_by_broker_execution_id(
        self,
        broker_execution_id: str,
        conn: sqlite3.Connection | None = None,
    ) -> Fill | None:
        """Retrieves a fill by broker execution ID (for idempotency check)."""
        sql = "SELECT * FROM fills WHERE broker_execution_id = ?;"
        if conn is not None:
            row = conn.execute(sql, (broker_execution_id,)).fetchone()
        else:
            with self._db.get_connection() as c:
                row = c.execute(sql, (broker_execution_id,)).fetchone()

        if not row:
            return None

        return Fill(
            fill_id=row["fill_id"],
            order_id=row["order_id"],
            symbol=row["symbol"],
            side=OrderSide(row["side"]),
            quantity=float(row["quantity"]),
            fill_price=float(row["fill_price"]),
            commission=float(row["commission"]),
            timestamp=datetime.fromisoformat(row["filled_at"]),
        )

    def list_fills_for_order(
        self,
        order_id: str,
        conn: sqlite3.Connection | None = None,
    ) -> list[Fill]:
        """Lists all fills associated with an order."""
        sql = "SELECT * FROM fills WHERE order_id = ? ORDER BY filled_at ASC;"
        if conn is not None:
            rows = conn.execute(sql, (order_id,)).fetchall()
        else:
            with self._db.get_connection() as c:
                rows = c.execute(sql, (order_id,)).fetchall()

        return [
            Fill(
                fill_id=r["fill_id"],
                order_id=r["order_id"],
                symbol=r["symbol"],
                side=OrderSide(r["side"]),
                quantity=float(r["quantity"]),
                fill_price=float(r["fill_price"]),
                commission=float(r["commission"]),
                timestamp=datetime.fromisoformat(r["filled_at"]),
            )
            for r in rows
        ]
