"""Repository for order records and status updates."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from ...core.enums import ExecutionMode, OrderSide, OrderStatus, OrderType
from ...core.interfaces import Order
from ..database import DatabaseManager


class OrderRepository:
    """Persists and retrieves order lifecycle records."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    def save_order(
        self,
        order: Order,
        execution_mode: ExecutionMode,
        client_order_id: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Persists a new order."""
        created_iso = order.created_at.isoformat()
        sql = """
        INSERT INTO orders (
            order_id, client_order_id, run_id, strategy_id, symbol,
            side, order_type, quantity, limit_price, status,
            execution_mode, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        params = (
            order.order_id,
            client_order_id or order.order_id,
            order.run_id,
            order.strategy_id,
            order.symbol,
            order.side.value,
            order.order_type.value,
            order.quantity,
            order.limit_price,
            order.status.value,
            execution_mode.value,
            created_iso,
            created_iso,
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            with self._db.get_connection() as c:
                c.execute(sql, params)

    def update_order_status(
        self,
        order_id: str,
        status: OrderStatus,
        updated_at: datetime | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Updates the status of an existing order."""
        updated_iso = (updated_at or datetime.now(timezone.utc)).isoformat()
        sql = "UPDATE orders SET status = ?, updated_at = ? WHERE order_id = ?;"
        params = (status.value, updated_iso, order_id)
        if conn is not None:
            conn.execute(sql, params)
        else:
            with self._db.get_connection() as c:
                c.execute(sql, params)

    def get_order(self, order_id: str, conn: sqlite3.Connection | None = None) -> Order | None:
        """Retrieves an order by order_id."""
        sql = "SELECT * FROM orders WHERE order_id = ?;"
        if conn is not None:
            row = conn.execute(sql, (order_id,)).fetchone()
        else:
            with self._db.get_connection() as c:
                row = c.execute(sql, (order_id,)).fetchone()

        if not row:
            return None

        return Order(
            order_id=row["order_id"],
            run_id=row["run_id"],
            strategy_id=row["strategy_id"],
            symbol=row["symbol"],
            side=OrderSide(row["side"]),
            order_type=OrderType(row["order_type"]),
            quantity=float(row["quantity"]),
            limit_price=float(row["limit_price"]) if row["limit_price"] is not None else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            status=OrderStatus(row["status"]),
        )

    def get_order_by_client_id(
        self,
        client_order_id: str,
        conn: sqlite3.Connection | None = None,
    ) -> Order | None:
        """Retrieves an order by client_order_id."""
        sql = "SELECT * FROM orders WHERE client_order_id = ?;"
        if conn is not None:
            row = conn.execute(sql, (client_order_id,)).fetchone()
        else:
            with self._db.get_connection() as c:
                row = c.execute(sql, (client_order_id,)).fetchone()

        if not row:
            return None

        return Order(
            order_id=row["order_id"],
            run_id=row["run_id"],
            strategy_id=row["strategy_id"],
            symbol=row["symbol"],
            side=OrderSide(row["side"]),
            order_type=OrderType(row["order_type"]),
            quantity=float(row["quantity"]),
            limit_price=float(row["limit_price"]) if row["limit_price"] is not None else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            status=OrderStatus(row["status"]),
        )

    def list_orders_for_run(
        self,
        run_id: str,
        conn: sqlite3.Connection | None = None,
    ) -> list[Order]:
        """Lists all orders associated with a system run."""
        sql = "SELECT * FROM orders WHERE run_id = ? ORDER BY created_at ASC;"
        if conn is not None:
            rows = conn.execute(sql, (run_id,)).fetchall()
        else:
            with self._db.get_connection() as c:
                rows = c.execute(sql, (run_id,)).fetchall()

        return [
            Order(
                order_id=r["order_id"],
                run_id=r["run_id"],
                strategy_id=r["strategy_id"],
                symbol=r["symbol"],
                side=OrderSide(r["side"]),
                order_type=OrderType(r["order_type"]),
                quantity=float(r["quantity"]),
                limit_price=float(r["limit_price"]) if r["limit_price"] is not None else None,
                created_at=datetime.fromisoformat(r["created_at"]),
                status=OrderStatus(r["status"]),
            )
            for r in rows
        ]
