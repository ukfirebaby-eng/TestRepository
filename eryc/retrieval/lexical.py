"""
FTS5 lexical retrieval service.

Phase C-1: Full-text search using SQLite FTS5 with the porter stemmer.
Supports structured filters (workspace, collection, doc_type, sensitivity,
time range) as described in spec §9.2 stage 1.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Dict, List, Optional

from eryc.models.domain import CandidateChunk

logger = logging.getLogger(__name__)


class LexicalRetriever:
    """
    Execute FTS5 queries against the ``chunks_fts`` virtual table.

    Args:
        conn:   Open SQLite connection with WAL mode and FTS5 available.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

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
        Run a porter-stemmed full-text search and return ranked candidates.

        The FTS5 query is constructed from the user query with special
        characters escaped.  Structured filters are applied as JOIN conditions
        on the relational tables.

        Returns candidates with ``lexical_rank`` set to their BM25 rank (1-based).
        """
        fts_query = self._build_fts_query(query)
        params: List[Any] = [workspace_id, fts_query]

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
        if time_from:
            filter_clauses.append("d.created_at >= ?")
            params.append(time_from)
        if time_to:
            filter_clauses.append("d.created_at <= ?")
            params.append(time_to)

        entity_join = ""
        if entity_ids:
            placeholders = ",".join("?" * len(entity_ids))
            entity_join = f"""
                JOIN chunk_entities ce ON ce.chunk_id = f.chunk_id
                    AND ce.entity_id IN ({placeholders})
            """
            params.extend(entity_ids)

        where_extra = ""
        if filter_clauses:
            where_extra = " AND " + " AND ".join(filter_clauses)

        params.append(limit)

        sql = f"""
            SELECT
                f.chunk_id,
                c.document_id,
                c.version_id,
                d.canonical_title,
                c.section_path,
                c.text,
                c.text_preview,
                d.source_path,
                d.sensitivity_level,
                rank
            FROM chunks_fts f
            JOIN chunks c ON c.chunk_id = f.chunk_id
            JOIN documents d ON d.document_id = c.document_id
            {entity_join}
            WHERE d.workspace_id = ?
              AND chunks_fts MATCH ?
              {where_extra}
            ORDER BY rank
            LIMIT ?
        """

        try:
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            logger.warning("FTS5 query failed: %s", exc)
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
                lexical_rank=idx + 1,
            )
            for idx, row in enumerate(rows)
        ]

    @staticmethod
    def _build_fts_query(query: str) -> str:
        """
        Escape the user query for FTS5 and construct a MATCH expression.

        Special FTS5 characters are removed; terms are joined with implicit
        AND so all words must appear.
        """
        # Strip FTS5 special characters.
        cleaned = query.replace('"', "").replace("'", "").replace("*", "")
        terms = [t.strip() for t in cleaned.split() if t.strip()]
        if not terms:
            return '""'
        # Wrap multi-word queries in a phrase search for precision.
        if len(terms) > 1:
            phrase = " ".join(terms)
            return f'"{phrase}" OR ' + " ".join(terms)
        return terms[0]
