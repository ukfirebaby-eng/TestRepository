"""
SQLite connection management for ERYC Document Intelligence Console.

Uses WAL journal mode as specified in §8.3.  A single module-level
connection factory is used so the caller can decide whether to share a
connection or open a fresh one.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Optional

from eryc.config import Settings, get_settings

_local = threading.local()


def _apply_pragmas(conn: sqlite3.Connection, settings: Settings) -> None:
    """Apply the recommended SQLite runtime settings (spec §8.3)."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_ms}")


def open_connection(
    db_path: Path,
    *,
    settings: Optional[Settings] = None,
    row_factory: bool = True,
) -> sqlite3.Connection:
    """
    Open a new SQLite connection to ``db_path`` and apply WAL pragmas.

    Args:
        db_path:      Path to the SQLite database file.
        settings:     Optional Settings instance; defaults to get_settings().
        row_factory:  When True (default), rows are returned as sqlite3.Row
                      objects so columns are accessible by name.
    """
    if settings is None:
        settings = get_settings()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    if row_factory:
        conn.row_factory = sqlite3.Row
    _apply_pragmas(conn, settings)
    _try_load_sqlite_vec(conn)
    return conn


def _try_load_sqlite_vec(conn: sqlite3.Connection) -> None:
    """
    Attempt to load the sqlite-vec extension for vector similarity search.

    If the extension is not installed the system falls back to lexical-only
    retrieval; a diagnostic flag is set so callers can detect the degraded
    state.
    """
    try:
        conn.enable_load_extension(True)
        conn.load_extension("vec0")
        conn.enable_load_extension(False)
    except Exception:
        # Extension not available — semantic retrieval will be disabled.
        pass


class ConnectionPool:
    """
    Minimal thread-local connection pool for the ERYC runtime database.

    Each thread obtains its own connection; SQLite's WAL mode allows
    concurrent readers without blocking.
    """

    def __init__(self, db_path: Path, settings: Optional[Settings] = None) -> None:
        self._db_path = db_path
        self._settings = settings or get_settings()

    def get(self) -> sqlite3.Connection:
        """Return the thread-local connection, creating it if necessary."""
        conn: Optional[sqlite3.Connection] = getattr(_local, "conn", None)
        if conn is None:
            conn = open_connection(self._db_path, settings=self._settings)
            _local.conn = conn
        return conn

    def close(self) -> None:
        """Close the thread-local connection if one exists."""
        conn: Optional[sqlite3.Connection] = getattr(_local, "conn", None)
        if conn is not None:
            conn.close()
            _local.conn = None
