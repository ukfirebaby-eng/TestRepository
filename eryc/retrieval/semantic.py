"""
Semantic retrieval service using sqlite-vec.

Phase C-2: Nearest-neighbour vector search with filtered join-back to the
relational tables.  Degrades gracefully to an empty result set when
sqlite-vec is not available.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from eryc.ingestion.indexer import get_embedding_provider
from eryc.models.domain import CandidateChunk

logger = logging.getLogger(__name__)


class SemanticRetriever:
    """
    Execute vector-similarity queries against the ``chunk_embeddings`` table.

    Args:
        conn:   Open SQLite connection (may or may not have sqlite-vec loaded).
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._available = self._check_available()

    def _check_available(self) -> bool:
        try:
            self._conn.execute("SELECT vec_version()")
            return True
        except sqlite3.OperationalError:
            return False

    @property
    def available(self) -> bool:
        return self._available

    def search(
        self,
        query: str,
        *,
        workspace_id: str,
        limit: int = 20,
        collection_ids: Optional[List[str]] = None,
        doc_types: Optional[List[str]] = None,
        sensitivity_levels: Optional[List[str]] = None,
        time_from: Optional[str] = None,
        time_to: Optional[str] = None,
        entity_ids: Optional[List[str]] = None,
    ) -> List[CandidateChunk]:
        """
        Embed ``query`` and return the nearest ``limit`` chunks by cosine distance.

        Returns an empty list if sqlite-vec is not loaded or embeddings
        have not been generated for the corpus.  Semantic rank is 1-based.
        """
        if not self._available:
            logger.debug("Semantic retrieval unavailable — sqlite-vec not loaded")
            return []

        provider = get_embedding_provider()
        if not provider.available:
            logger.debug("Semantic retrieval unavailable — embedding model not loaded")
            return []

        try:
            vector = provider.encode([query])[0]
        except Exception as exc:
            logger.warning("Embedding generation failed: %s", exc)
            return []

        vector_json = json.dumps(vector)
        params: List[Any] = [vector_json, workspace_id]

        filter_clauses = []
        if collection_ids:
            placeholders = ",".join("?" * len(collection_ids))
            filter_clauses.append(f"d.collection_id IN ({placeholders})")
            params.extend(collection_ids)
        if doc_types:
            placeholders = ",".join("?" * len(doc_types))
            filter_clauses.append(f"d.doc_type IN ({placeholders})")
            params.extend(doc_types)
        if sensitivity_levels:
            placeholders = ",".join("?" * len(sensitivity_levels))
            filter_clauses.append(f"d.sensitivity_level IN ({placeholders})")
            params.extend(sensitivity_levels)

        where_extra = ""
        if filter_clauses:
            where_extra = " AND " + " AND ".join(filter_clauses)

        params.append(limit)

        sql = f"""
            SELECT
                e.chunk_id,
                e.distance,
                c.document_id,
                c.version_id,
                d.canonical_title,
                c.section_path,
                c.text,
                c.text_preview,
                d.source_path,
                d.sensitivity_level
            FROM chunk_embeddings e
            JOIN chunks c ON c.chunk_id = e.chunk_id
            JOIN documents d ON d.document_id = c.document_id
            WHERE e.embedding MATCH ?
              AND k = {limit}
              AND d.workspace_id = ?
              {where_extra}
            ORDER BY e.distance
        """

        try:
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            logger.warning("Semantic query failed: %s", exc)
            return []

        return [
            CandidateChunk(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                version_id=row["version_id"],
                canonical_title=row["canonical_title"],
                section_path=row["section_path"],
                text=row["text"],
                text_preview=row["text_preview"],
                source_path=row["source_path"],
                sensitivity_level=row["sensitivity_level"],
                semantic_rank=idx + 1,
            )
            for idx, row in enumerate(rows)
        ]
