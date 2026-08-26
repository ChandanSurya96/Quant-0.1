"""Repository for physical asset holdings."""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from typing import Any

from ...core.interfaces import Holding
from ..database import DatabaseManager


class HoldingRepository:
    """Persists and retrieves physical portfolio asset holdings."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    def save_holding(
        self,
        holding: Holding,
        portfolio_id: str = "default",
        updated_at: datetime | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Upserts a single physical holding record."""
        updated_iso = (updated_at or datetime.now(timezone.utc)).isoformat()
        sql = """
        INSERT INTO physical_holdings (
            symbol, portfolio_id, shares, cost_basis, last_price, market_value, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, portfolio_id) DO UPDATE SET
            shares = excluded.shares,
            cost_basis = excluded.cost_basis,
            last_price = excluded.last_price,
            market_value = excluded.market_value,
            updated_at = excluded.updated_at;
        """
        params = (
            holding.symbol,
            portfolio_id,
            holding.shares,
            holding.cost_basis,
            holding.current_price,
            holding.market_value,
            updated_iso,
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            with self._db.get_connection() as c:
                c.execute(sql, params)

    def save_holdings(
        self,
        holdings: dict[str, Any],
        portfolio_id: str = "default",
        updated_at: datetime | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Synchronizes holdings by clearing closed positions and upserting active holdings."""
        updated_iso = (updated_at or datetime.now(timezone.utc)).isoformat()

        def _execute_sync(c: sqlite3.Connection) -> None:
            active_symbols: list[str] = []
            for sym, h in holdings.items():
                if hasattr(h, "shares"):
                    shares = float(h.shares)
                    cost_basis = float(getattr(h, "cost_basis", 0.0))
                    last_price = float(getattr(h, "current_price", 0.0))
                    market_value = float(getattr(h, "market_value", shares * last_price))
                else:
                    shares = float(h)
                    cost_basis = 0.0
                    last_price = 0.0
                    market_value = 0.0

                if abs(shares) > 1e-6:
                    active_symbols.append(sym)
                    c.execute(
                        """
                        INSERT INTO physical_holdings (
                            symbol, portfolio_id, shares, cost_basis, last_price, market_value, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(symbol, portfolio_id) DO UPDATE SET
                            shares = excluded.shares,
                            cost_basis = excluded.cost_basis,
                            last_price = excluded.last_price,
                            market_value = excluded.market_value,
                            updated_at = excluded.updated_at;
                        """,
                        (sym, portfolio_id, shares, cost_basis, last_price, market_value, updated_iso),
                    )

            if active_symbols:
                placeholders = ",".join("?" for _ in active_symbols)
                c.execute(
                    f"DELETE FROM physical_holdings WHERE portfolio_id = ? AND symbol NOT IN ({placeholders});",
                    [portfolio_id] + active_symbols,
                )
            else:
                c.execute("DELETE FROM physical_holdings WHERE portfolio_id = ?;", (portfolio_id,))

        if conn is not None:
            _execute_sync(conn)
        else:
            with self._db.get_connection() as c:
                _execute_sync(c)

    def get_holding(
        self,
        symbol: str,
        portfolio_id: str = "default",
        conn: sqlite3.Connection | None = None,
    ) -> Holding | None:
        """Retrieves a single holding by symbol and portfolio_id."""
        sql = "SELECT * FROM physical_holdings WHERE symbol = ? AND portfolio_id = ?;"
        if conn is not None:
            row = conn.execute(sql, (symbol, portfolio_id)).fetchone()
        else:
            with self._db.get_connection() as c:
                row = c.execute(sql, (symbol, portfolio_id)).fetchone()

        if not row:
            return None

        return Holding(
            symbol=row["symbol"],
            shares=float(row["shares"]),
            cost_basis=float(row["cost_basis"]),
            current_price=float(row["last_price"]),
            market_value=float(row["market_value"]),
        )

    def get_holdings(
        self,
        portfolio_id: str = "default",
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Holding]:
        """Retrieves all current physical holdings for a portfolio."""
        sql = "SELECT * FROM physical_holdings WHERE portfolio_id = ?;"
        if conn is not None:
            rows = conn.execute(sql, (portfolio_id,)).fetchall()
        else:
            with self._db.get_connection() as c:
                rows = c.execute(sql, (portfolio_id,)).fetchall()

        return {
            r["symbol"]: Holding(
                symbol=r["symbol"],
                shares=float(r["shares"]),
                cost_basis=float(r["cost_basis"]),
                current_price=float(r["last_price"]),
                market_value=float(r["market_value"]),
            )
            for r in rows
        }

    def clear_holdings(
        self,
        portfolio_id: str = "default",
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Clears all holdings for a portfolio."""
        sql = "DELETE FROM physical_holdings WHERE portfolio_id = ?;"
        if conn is not None:
            conn.execute(sql, (portfolio_id,))
        else:
            with self._db.get_connection() as c:
                c.execute(sql, (portfolio_id,))
