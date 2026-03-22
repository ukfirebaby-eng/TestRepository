"""
Schema migrations for the ERYC runtime database.

Each migration is identified by an integer version number.  The system
applies all outstanding migrations in order on startup.  Migrations are
never re-applied; the ``schema_version`` table tracks the current level.

All DDL follows the schema specified in §8 of the ERYC specification,
including the FTS5 and sqlite-vec structures described in Appendix A and B.
"""

from __future__ import annotations

import sqlite3
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Migration registry
# Each entry is (version: int, description: str, sql_statements: List[str]).
# ---------------------------------------------------------------------------

_MIGRATIONS: List[Tuple[int, str, List[str]]] = [
    (
        1,
        "Core runtime schema",
        [
            # ----------------------------------------------------------
            # Schema version tracker
            # ----------------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version     INTEGER PRIMARY KEY,
                applied_at  TEXT    NOT NULL
            )
            """,
            # ----------------------------------------------------------
            # Users and roles  (spec §8.1)
            # ----------------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id     TEXT PRIMARY KEY,
                username    TEXT NOT NULL UNIQUE,
                role        TEXT NOT NULL DEFAULT 'user',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
            """,
            # ----------------------------------------------------------
            # Workspaces  (spec §8.1 / Appendix A)
            # ----------------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS workspaces (
                workspace_id    TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                domain_pack     TEXT NOT NULL DEFAULT 'generic',
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
            """,
            # ----------------------------------------------------------
            # User ↔ workspace membership
            # ----------------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS workspace_members (
                workspace_id    TEXT NOT NULL REFERENCES workspaces(workspace_id),
                user_id         TEXT NOT NULL REFERENCES users(user_id),
                role            TEXT NOT NULL DEFAULT 'member',
                joined_at       TEXT NOT NULL,
                PRIMARY KEY (workspace_id, user_id)
            )
            """,
            # ----------------------------------------------------------
            # Collections  (optional subset boundary)
            # ----------------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS collections (
                collection_id   TEXT PRIMARY KEY,
                workspace_id    TEXT NOT NULL REFERENCES workspaces(workspace_id),
                name            TEXT NOT NULL,
                description     TEXT,
                created_at      TEXT NOT NULL
            )
            """,
            # ----------------------------------------------------------
            # Documents  (spec §8.1 / Appendix A)
            # ----------------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS documents (
                document_id         TEXT PRIMARY KEY,
                workspace_id        TEXT NOT NULL REFERENCES workspaces(workspace_id),
                collection_id       TEXT REFERENCES collections(collection_id),
                doc_type            TEXT NOT NULL,
                canonical_title     TEXT NOT NULL,
                current_version_id  TEXT,
                source_path         TEXT,
                sensitivity_level   TEXT NOT NULL DEFAULT 'standard',
                access_scope        TEXT NOT NULL DEFAULT 'workspace',
                created_at          TEXT NOT NULL,
                updated_at          TEXT NOT NULL
            )
            """,
            # ----------------------------------------------------------
            # Document versions  (immutable; version-pinned citations)
            # ----------------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS document_versions (
                version_id      TEXT PRIMARY KEY,
                document_id     TEXT NOT NULL REFERENCES documents(document_id),
                version_number  INTEGER NOT NULL,
                content_hash    TEXT NOT NULL,
                parsed_at       TEXT,
                indexed_at      TEXT,
                index_status    TEXT NOT NULL DEFAULT 'pending',
                created_at      TEXT NOT NULL
            )
            """,
            # ----------------------------------------------------------
            # Chunks  (retrievable segments — Appendix A)
            # ----------------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id        TEXT PRIMARY KEY,
                version_id      TEXT NOT NULL REFERENCES document_versions(version_id),
                document_id     TEXT NOT NULL REFERENCES documents(document_id),
                chunk_ordinal   INTEGER NOT NULL,
                section_path    TEXT NOT NULL,
                token_count     INTEGER NOT NULL,
                text            TEXT NOT NULL,
                text_preview    TEXT NOT NULL,
                metadata_json   TEXT NOT NULL DEFAULT '{}'
            )
            """,
            # ----------------------------------------------------------
            # Entities and chunk-entity links
            # ----------------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS entities (
                entity_id       TEXT PRIMARY KEY,
                workspace_id    TEXT NOT NULL REFERENCES workspaces(workspace_id),
                entity_type     TEXT NOT NULL,
                name            TEXT NOT NULL,
                canonical_name  TEXT NOT NULL,
                metadata_json   TEXT NOT NULL DEFAULT '{}',
                created_at      TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS chunk_entities (
                chunk_id    TEXT NOT NULL REFERENCES chunks(chunk_id),
                entity_id   TEXT NOT NULL REFERENCES entities(entity_id),
                span_text   TEXT,
                PRIMARY KEY (chunk_id, entity_id)
            )
            """,
            # ----------------------------------------------------------
            # Query threads and runs
            # ----------------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS query_threads (
                thread_id       TEXT PRIMARY KEY,
                workspace_id    TEXT NOT NULL REFERENCES workspaces(workspace_id),
                user_id         TEXT NOT NULL REFERENCES users(user_id),
                title           TEXT,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id              TEXT PRIMARY KEY,
                thread_id           TEXT NOT NULL REFERENCES query_threads(thread_id),
                user_id             TEXT NOT NULL REFERENCES users(user_id),
                query               TEXT NOT NULL,
                filters_json        TEXT NOT NULL DEFAULT '{}',
                status              TEXT NOT NULL DEFAULT 'pending',
                query_class         TEXT,
                retrieval_mode      TEXT,
                retrieval_rounds    INTEGER NOT NULL DEFAULT 0,
                answer              TEXT,
                grounding_json      TEXT,
                diagnostics_json    TEXT NOT NULL DEFAULT '{}',
                error_message       TEXT,
                started_at          TEXT NOT NULL,
                completed_at        TEXT
            )
            """,
            # ----------------------------------------------------------
            # Citations and retrieval attempts
            # ----------------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS run_citations (
                citation_id     TEXT PRIMARY KEY,
                run_id          TEXT NOT NULL REFERENCES runs(run_id),
                chunk_id        TEXT NOT NULL REFERENCES chunks(chunk_id),
                document_id     TEXT NOT NULL REFERENCES documents(document_id),
                version_id      TEXT NOT NULL REFERENCES document_versions(version_id),
                title           TEXT NOT NULL,
                locator         TEXT,
                source_path     TEXT,
                snippet         TEXT,
                ordinal         INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS retrieval_attempts (
                attempt_id      TEXT PRIMARY KEY,
                run_id          TEXT NOT NULL REFERENCES runs(run_id),
                round_number    INTEGER NOT NULL,
                mode            TEXT NOT NULL,
                query_used      TEXT NOT NULL,
                filters_json    TEXT NOT NULL DEFAULT '{}',
                result_count    INTEGER NOT NULL DEFAULT 0,
                diagnostics_json TEXT NOT NULL DEFAULT '{}',
                executed_at     TEXT NOT NULL
            )
            """,
            # ----------------------------------------------------------
            # Ingest jobs
            # ----------------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS ingest_jobs (
                job_id          TEXT PRIMARY KEY,
                workspace_id    TEXT NOT NULL REFERENCES workspaces(workspace_id),
                collection_id   TEXT REFERENCES collections(collection_id),
                source_path     TEXT NOT NULL,
                doc_type        TEXT,
                sensitivity_level TEXT NOT NULL DEFAULT 'standard',
                status          TEXT NOT NULL DEFAULT 'queued',
                document_id     TEXT REFERENCES documents(document_id),
                error_message   TEXT,
                queued_at       TEXT NOT NULL,
                started_at      TEXT,
                completed_at    TEXT
            )
            """,
            # ----------------------------------------------------------
            # Audit events  (spec §10)
            # ----------------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id        TEXT PRIMARY KEY,
                event_type      TEXT NOT NULL,
                user_id         TEXT,
                workspace_id    TEXT,
                resource_type   TEXT,
                resource_id     TEXT,
                details_json    TEXT NOT NULL DEFAULT '{}',
                occurred_at     TEXT NOT NULL
            )
            """,
            # ----------------------------------------------------------
            # Feedback events
            # ----------------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS feedback_events (
                feedback_id     TEXT PRIMARY KEY,
                run_id          TEXT NOT NULL REFERENCES runs(run_id),
                user_id         TEXT NOT NULL REFERENCES users(user_id),
                rating          INTEGER,
                reason_code     TEXT,
                comment         TEXT,
                submitted_at    TEXT NOT NULL
            )
            """,
            # ----------------------------------------------------------
            # Indexes on frequently filtered columns
            # ----------------------------------------------------------
            "CREATE INDEX IF NOT EXISTS idx_documents_workspace ON documents(workspace_id)",
            "CREATE INDEX IF NOT EXISTS idx_documents_collection ON documents(collection_id)",
            "CREATE INDEX IF NOT EXISTS idx_chunks_version ON chunks(version_id)",
            "CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id)",
            "CREATE INDEX IF NOT EXISTS idx_runs_thread ON runs(thread_id)",
            "CREATE INDEX IF NOT EXISTS idx_runs_user ON runs(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_audit_events_type ON audit_events(event_type)",
            "CREATE INDEX IF NOT EXISTS idx_audit_events_user ON audit_events(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_ingest_jobs_status ON ingest_jobs(status)",
        ],
    ),
    (
        2,
        "FTS5 and vector search structures",
        [
            # ----------------------------------------------------------
            # FTS5 virtual table for lexical retrieval  (Appendix B)
            # ----------------------------------------------------------
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                chunk_id    UNINDEXED,
                document_id UNINDEXED,
                version_id  UNINDEXED,
                canonical_title,
                section_path,
                text,
                tokenize = 'porter unicode61'
            )
            """,
            # Trigger to keep FTS5 in sync with the chunks table
            """
            CREATE TRIGGER IF NOT EXISTS chunks_fts_insert
            AFTER INSERT ON chunks BEGIN
                INSERT INTO chunks_fts(
                    chunk_id, document_id, version_id,
                    canonical_title, section_path, text
                )
                SELECT
                    NEW.chunk_id, NEW.document_id, NEW.version_id,
                    d.canonical_title, NEW.section_path, NEW.text
                FROM documents d WHERE d.document_id = NEW.document_id;
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS chunks_fts_delete
            AFTER DELETE ON chunks BEGIN
                DELETE FROM chunks_fts WHERE chunk_id = OLD.chunk_id;
            END
            """,
        ],
    ),
    (
        3,
        "Vector embeddings table",
        [
            # chunk_embeddings is created by the indexer when sqlite-vec
            # is available.  We create a simple fallback table here so the
            # schema is consistent regardless of whether the extension loads.
            """
            CREATE TABLE IF NOT EXISTS chunk_embeddings_meta (
                chunk_id        TEXT PRIMARY KEY REFERENCES chunks(chunk_id),
                embedding_model TEXT NOT NULL,
                embedding_dim   INTEGER NOT NULL,
                indexed_at      TEXT NOT NULL
            )
            """,
        ],
    ),
    (
        4,
        "Temporal Knowledge Graph — nodes, edges, temporal metadata, friction items",
        [
            # ----------------------------------------------------------
            # Graph nodes: tasks, goals, phases, resources
            # ----------------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS graph_nodes (
                node_id         TEXT PRIMARY KEY,
                workspace_id    TEXT NOT NULL REFERENCES workspaces(workspace_id),
                node_type       TEXT NOT NULL,
                name            TEXT NOT NULL,
                description     TEXT,
                phase           TEXT,
                document_id     TEXT REFERENCES documents(document_id),
                chunk_id        TEXT REFERENCES chunks(chunk_id),
                metadata_json   TEXT NOT NULL DEFAULT '{}',
                created_at      TEXT NOT NULL
            )
            """,
            # ----------------------------------------------------------
            # Directed edges: structural dependencies between nodes
            # ----------------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS graph_edges (
                edge_id         TEXT PRIMARY KEY,
                workspace_id    TEXT NOT NULL REFERENCES workspaces(workspace_id),
                source_node_id  TEXT NOT NULL REFERENCES graph_nodes(node_id),
                target_node_id  TEXT NOT NULL REFERENCES graph_nodes(node_id),
                edge_type       TEXT NOT NULL DEFAULT 'depends_on',
                weight          REAL NOT NULL DEFAULT 1.0,
                metadata_json   TEXT NOT NULL DEFAULT '{}',
                created_at      TEXT NOT NULL
            )
            """,
            # ----------------------------------------------------------
            # Temporal metadata: scheduling data per node
            # ----------------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS temporal_metadata (
                node_id         TEXT PRIMARY KEY REFERENCES graph_nodes(node_id),
                planned_start   TEXT,
                planned_end     TEXT,
                actual_start    TEXT,
                actual_end      TEXT,
                duration_days   REAL,
                slack_days      REAL,
                updated_at      TEXT NOT NULL
            )
            """,
            # ----------------------------------------------------------
            # Friction items: structural (red) and temporal (yellow) conflicts
            # ----------------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS friction_items (
                friction_id     TEXT PRIMARY KEY,
                workspace_id    TEXT NOT NULL REFERENCES workspaces(workspace_id),
                friction_type   TEXT NOT NULL,
                severity        TEXT NOT NULL DEFAULT 'medium',
                source_node_id  TEXT REFERENCES graph_nodes(node_id),
                target_node_id  TEXT REFERENCES graph_nodes(node_id),
                description     TEXT NOT NULL,
                chunk_id        TEXT REFERENCES chunks(chunk_id),
                resolved        INTEGER NOT NULL DEFAULT 0,
                resolved_at     TEXT,
                created_at      TEXT NOT NULL
            )
            """,
            # Indexes for graph traversal and reporting
            "CREATE INDEX IF NOT EXISTS idx_graph_nodes_workspace ON graph_nodes(workspace_id)",
            "CREATE INDEX IF NOT EXISTS idx_graph_nodes_type ON graph_nodes(node_type)",
            "CREATE INDEX IF NOT EXISTS idx_graph_nodes_phase ON graph_nodes(phase)",
            "CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges(source_node_id)",
            "CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges(target_node_id)",
            "CREATE INDEX IF NOT EXISTS idx_graph_edges_workspace ON graph_edges(workspace_id)",
            "CREATE INDEX IF NOT EXISTS idx_friction_workspace ON friction_items(workspace_id)",
            "CREATE INDEX IF NOT EXISTS idx_friction_type ON friction_items(friction_type)",
            "CREATE INDEX IF NOT EXISTS idx_friction_severity ON friction_items(severity)",
            "CREATE INDEX IF NOT EXISTS idx_friction_resolved ON friction_items(resolved)",
        ],
    ),
]


def apply_migrations(conn: sqlite3.Connection) -> None:
    """
    Apply all outstanding schema migrations to ``conn``.

    This function is idempotent; it will only apply migrations with a version
    number higher than the current ``schema_version``.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version     INTEGER PRIMARY KEY,
            applied_at  TEXT    NOT NULL
        )
        """
    )
    conn.commit()

    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current_version: int = row[0] if row[0] is not None else 0

    for version, description, statements in _MIGRATIONS:
        if version <= current_version:
            continue

        logger.info("Applying migration %d: %s", version, description)
        for sql in statements:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as exc:
                # Some DDL is advisory (e.g. sqlite-vec tables) — log and continue.
                logger.warning("Migration %d statement skipped: %s", version, exc)

        conn.execute(
            "INSERT INTO schema_version(version, applied_at) VALUES (?, datetime('now'))",
            (version,),
        )
        conn.commit()
        logger.info("Migration %d applied.", version)
