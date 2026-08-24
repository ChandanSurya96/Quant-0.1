"""Repository for instrument identity definitions."""

from __future__ import annotations

import json
import sqlite3

from ...core.enums import AssetClass
from ...core.interfaces import Instrument
from ..database import DatabaseManager


class InstrumentRepository:
    """Persists and retrieves instrument identity records."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    def save_instrument(
        self,
        instrument: Instrument,
        is_active: bool = True,
        metadata: dict | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Inserts or updates an instrument definition."""
        meta_json = json.dumps(metadata or {})
        sql = """
        INSERT INTO instruments (symbol, asset_class, currency, multiplier, tick_size, is_active, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            asset_class = excluded.asset_class,
            currency = excluded.currency,
            multiplier = excluded.multiplier,
            tick_size = excluded.tick_size,
            is_active = excluded.is_active,
            metadata_json = excluded.metadata_json;
        """
        params = (
            instrument.symbol,
            instrument.asset_class.value,
            instrument.currency,
            instrument.multiplier,
            instrument.tick_size,
            1 if is_active else 0,
            meta_json,
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            with self._db.get_connection() as c:
                c.execute(sql, params)

    def get_instrument(self, symbol: str, conn: sqlite3.Connection | None = None) -> Instrument | None:
        """Retrieves an instrument by symbol."""
        sql = "SELECT * FROM instruments WHERE symbol = ?;"
        if conn is not None:
            row = conn.execute(sql, (symbol,)).fetchone()
        else:
            with self._db.get_connection() as c:
                row = c.execute(sql, (symbol,)).fetchone()

        if not row:
            return None
        return Instrument(
            symbol=row["symbol"],
            asset_class=AssetClass(row["asset_class"]),
            currency=row["currency"],
            multiplier=float(row["multiplier"]),
            tick_size=float(row["tick_size"]),
        )

    def list_active_instruments(self, conn: sqlite3.Connection | None = None) -> list[Instrument]:
        """Lists all active instruments."""
        sql = "SELECT * FROM instruments WHERE is_active = 1 ORDER BY symbol ASC;"
        if conn is not None:
            rows = conn.execute(sql).fetchall()
        else:
            with self._db.get_connection() as c:
                rows = c.execute(sql).fetchall()

        return [
            Instrument(
                symbol=r["symbol"],
                asset_class=AssetClass(r["asset_class"]),
                currency=r["currency"],
                multiplier=float(r["multiplier"]),
                tick_size=float(r["tick_size"]),
            )
            for r in rows
        ]
