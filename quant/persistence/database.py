"""SQLite database connection and transaction manager."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from typing import Generator

SCHEMA_VERSION = 1
DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


class DatabaseManager:
    """Manages SQLite database connections, schema versioning, and atomic transactions."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = os.getenv("QUANT_STATE_DB", ":memory:")
        self.db_path = str(db_path)
        self._shared_conn: sqlite3.Connection | None = None

        if self.db_path == ":memory:":
            self._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._shared_conn.row_factory = sqlite3.Row
            self._shared_conn.execute("PRAGMA foreign_keys = ON;")

    def get_connection(self) -> sqlite3.Connection:
        """Returns a configured SQLite connection with foreign keys enabled."""
        if self._shared_conn is not None:
            return self._shared_conn

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def initialize_schema(self, schema_path: Path | str | None = None) -> None:
        """Initializes database schema and records schema version."""
        path = Path(schema_path) if schema_path else DEFAULT_SCHEMA_PATH
        if not path.exists():
            raise FileNotFoundError(f"Schema file not found at {path}")

        schema_sql = path.read_text(encoding="utf-8")
        conn = self.get_connection()
        try:
            conn.executescript(schema_sql)
            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (?, ?);",
                (SCHEMA_VERSION, now_iso),
            )
            conn.commit()
        finally:
            if self._shared_conn is None:
                conn.close()

    def get_schema_version(self) -> int:
        """Returns the active schema version."""
        conn = self.get_connection()
        try:
            cur = conn.execute("SELECT MAX(version) FROM schema_version;")
            row = cur.fetchone()
            if row is None or row[0] is None:
                return 0
            return int(row[0])
        finally:
            if self._shared_conn is None:
                conn.close()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Provides an atomic transaction context manager."""
        conn = self.get_connection()
        is_shared = self._shared_conn is not None
        try:
            conn.execute("BEGIN;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            if not is_shared:
                conn.close()
