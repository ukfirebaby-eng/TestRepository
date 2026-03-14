"""
FTS5 and vector indexer for the ERYC ingestion pipeline.

Phase B-5 and B-6: populate the lexical and semantic search indexes after
chunking.  Vector indexing degrades gracefully when sqlite-vec is not
available (the system falls back to lexical-only retrieval).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional, Sequence

from eryc.config import Settings, get_settings
from eryc.ingestion.chunker import RawChunk

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Embedding provider
# ---------------------------------------------------------------------------


class EmbeddingProvider:
    """
    Local embedding provider using sentence-transformers.

    Falls back to a zero-vector stub when the library is not installed so
    that the ingestion pipeline can still run in environments without GPU.
    """

    def __init__(self, model_name: str, dim: int) -> None:
        self._dim = dim
        self._model = None
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(model_name)
            logger.info("Loaded embedding model: %s", model_name)
        except ImportError:
            logger.warning(
                "sentence-transformers not available; using zero-vector embeddings. "
                "Install it to enable semantic retrieval."
            )

    @property
    def dim(self) -> int:
        return self._dim

    def encode(self, texts: List[str]) -> List[List[float]]:
        """Return a list of embedding vectors, one per text."""
        if self._model is None:
            return [[0.0] * self._dim for _ in texts]
        embeddings = self._model.encode(texts, show_progress_bar=False)
        return [e.tolist() for e in embeddings]

    @property
    def available(self) -> bool:
        return self._model is not None


_provider: Optional[EmbeddingProvider] = None


def get_embedding_provider(settings: Optional[Settings] = None) -> EmbeddingProvider:
    """Return the singleton embedding provider."""
    global _provider
    if _provider is None:
        cfg = settings or get_settings()
        _provider = EmbeddingProvider(cfg.embedding_model, cfg.embedding_dim)
    return _provider


# ---------------------------------------------------------------------------
# Indexer
# ---------------------------------------------------------------------------


class Indexer:
    """
    Writes chunks to the FTS5 and (optionally) vector indexes.

    The FTS5 trigger keeps the virtual table in sync; the vector index is
    updated explicitly here.  All writes happen within a single transaction
    per batch.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        settings: Optional[Settings] = None,
    ) -> None:
        self._conn = conn
        self._settings = settings or get_settings()
        self._embedding_provider = get_embedding_provider(self._settings)
        self._vec_available = self._check_vec_available()

    def _check_vec_available(self) -> bool:
        try:
            self._conn.execute("SELECT vec_version()")
            return True
        except sqlite3.OperationalError:
            return False

    def ensure_vec_table(self) -> None:
        """Create the sqlite-vec embedding table if the extension is loaded."""
        if not self._vec_available:
            return
        dim = self._settings.embedding_dim
        try:
            self._conn.execute(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunk_embeddings
                USING vec0(
                    chunk_id TEXT PRIMARY KEY,
                    embedding FLOAT[{dim}]
                )
                """
            )
            self._conn.commit()
        except sqlite3.OperationalError as exc:
            logger.warning("Could not create chunk_embeddings table: %s", exc)
            self._vec_available = False

    def index_chunks(self, chunks: List[RawChunk]) -> None:
        """
        Persist ``chunks`` to the relational store and update the indexes.

        Expects the chunks table to exist.  The FTS5 trigger handles lexical
        indexing automatically.  Vector embeddings are written here if
        sqlite-vec is loaded.
        """
        if not chunks:
            return

        self.ensure_vec_table()
        now = datetime.now(timezone.utc).isoformat()

        with self._conn:
            # --- 1. Write chunks to the relational table ---
            self._conn.executemany(
                """
                INSERT OR REPLACE INTO chunks(
                    chunk_id, version_id, document_id, chunk_ordinal,
                    section_path, token_count, text, text_preview, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        c.chunk_id,
                        c.version_id,
                        c.document_id,
                        c.chunk_ordinal,
                        c.section_path,
                        c.token_count,
                        c.text,
                        c.text_preview,
                        json.dumps(c.metadata),
                    )
                    for c in chunks
                ],
            )

            # --- 2. Vector embeddings ---
            if self._vec_available and self._embedding_provider.available:
                self._write_embeddings(chunks, now)

        logger.info(
            "Indexed %d chunks (vector=%s)", len(chunks), self._vec_available
        )

    def _write_embeddings(self, chunks: List[RawChunk], now: str) -> None:
        """Generate and persist embedding vectors for the given chunks."""
        texts = [c.text for c in chunks]
        try:
            vectors = self._embedding_provider.encode(texts)
        except Exception as exc:
            logger.warning("Embedding generation failed: %s", exc)
            return

        try:
            self._conn.executemany(
                "INSERT OR REPLACE INTO chunk_embeddings(chunk_id, embedding) VALUES (?, ?)",
                [
                    (c.chunk_id, json.dumps(vec))
                    for c, vec in zip(chunks, vectors)
                ],
            )
        except sqlite3.OperationalError as exc:
            logger.warning("Could not write vector embeddings: %s", exc)

        # Always update the metadata tracking table.
        self._conn.executemany(
            """
            INSERT OR REPLACE INTO chunk_embeddings_meta(
                chunk_id, embedding_model, embedding_dim, indexed_at
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (
                    c.chunk_id,
                    self._settings.embedding_model,
                    self._settings.embedding_dim,
                    now,
                )
                for c in chunks
            ],
        )

    def mark_version_indexed(self, version_id: str) -> None:
        """Update the index_status and indexed_at for a document version."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE document_versions SET index_status='indexed', indexed_at=? WHERE version_id=?",
            (now, version_id),
        )
        self._conn.commit()

    def rebuild_fts(self, workspace_id: Optional[str] = None) -> None:
        """
        Rebuild the FTS5 index from the chunks table.

        If ``workspace_id`` is given only chunks belonging to that workspace
        are reindexed.  This supports the integrity tooling described in §F-4.
        """
        self._conn.execute("DELETE FROM chunks_fts")

        if workspace_id:
            self._conn.execute(
                """
                INSERT INTO chunks_fts(chunk_id, document_id, version_id,
                                       canonical_title, section_path, text)
                SELECT c.chunk_id, c.document_id, c.version_id,
                       d.canonical_title, c.section_path, c.text
                FROM chunks c
                JOIN documents d ON d.document_id = c.document_id
                WHERE d.workspace_id = ?
                """,
                (workspace_id,),
            )
        else:
            self._conn.execute(
                """
                INSERT INTO chunks_fts(chunk_id, document_id, version_id,
                                       canonical_title, section_path, text)
                SELECT c.chunk_id, c.document_id, c.version_id,
                       d.canonical_title, c.section_path, c.text
                FROM chunks c
                JOIN documents d ON d.document_id = c.document_id
                """
            )

        self._conn.commit()
        logger.info("FTS5 index rebuilt (workspace=%s)", workspace_id or "all")
