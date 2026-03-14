"""
Tests for the database layer: connection, migrations, schema integrity.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from eryc.database.connection import open_connection
from eryc.database.migrations import apply_migrations


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def conn(db_path: Path) -> sqlite3.Connection:
    c = open_connection(db_path)
    apply_migrations(c)
    yield c
    c.close()


class TestMigrations:
    def test_migrations_are_idempotent(self, db_path: Path) -> None:
        """Applying migrations twice should not raise."""
        c = open_connection(db_path)
        apply_migrations(c)
        apply_migrations(c)
        c.close()

    def test_schema_version_is_tracked(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row[0] is not None and row[0] >= 1

    def test_core_tables_exist(self, conn: sqlite3.Connection) -> None:
        tables_row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {r[0] for r in tables_row}
        for expected in (
            "users",
            "workspaces",
            "collections",
            "documents",
            "document_versions",
            "chunks",
            "runs",
            "audit_events",
        ):
            assert expected in table_names, f"Table '{expected}' missing"

    def test_fts5_virtual_table_exists(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE name='chunks_fts'"
        ).fetchone()
        assert row is not None, "chunks_fts virtual table not created"

    def test_wal_mode_applied(self, conn: sqlite3.Connection) -> None:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"

    def test_foreign_keys_enabled(self, conn: sqlite3.Connection) -> None:
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1
