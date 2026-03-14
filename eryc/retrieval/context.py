"""
Adjacent context expansion for the ERYC retrieval pipeline.

Phase C-4: Load the chunks immediately before and after each top candidate
to provide fuller context to the answer-composition step.

Spec §9.2 stage 5 — «Load surrounding material for the highest-value chunks».
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Dict, List, Optional

from eryc.models.domain import CandidateChunk

logger = logging.getLogger(__name__)


class ContextExpander:
    """
    Enrich the top candidates with adjacent chunks from the same document version.

    Args:
        conn:   Open SQLite connection.
        window: Number of chunks to load before and after each candidate.
    """

    def __init__(self, conn: sqlite3.Connection, *, window: int = 1) -> None:
        self._conn = conn
        self._window = window

    def expand(
        self,
        candidates: List[CandidateChunk],
        *,
        max_context_chunks: int = 10,
    ) -> List[CandidateChunk]:
        """
        Return the top ``max_context_chunks`` candidates augmented with adjacent
        chunks from the same document version.

        Adjacent chunks are appended to the result list with their ``chunk_id``
        preserved so citations remain accurate.  Duplicates are deduped by
        ``chunk_id``, preserving original ranking order.
        """
        top = candidates[:max_context_chunks]
        seen_ids = {c.chunk_id for c in top}
        expanded: List[CandidateChunk] = list(top)

        for candidate in top:
            neighbours = self._load_neighbours(candidate)
            for n in neighbours:
                if n.chunk_id not in seen_ids:
                    expanded.append(n)
                    seen_ids.add(n.chunk_id)

        return expanded[:max_context_chunks]

    def _load_neighbours(self, candidate: CandidateChunk) -> List[CandidateChunk]:
        """Load the adjacent ``window`` chunks on each side of ``candidate``."""
        ordinal_row = self._conn.execute(
            "SELECT chunk_ordinal FROM chunks WHERE chunk_id = ?",
            (candidate.chunk_id,),
        ).fetchone()

        if ordinal_row is None:
            return []

        ordinal = ordinal_row["chunk_ordinal"]
        lo = ordinal - self._window
        hi = ordinal + self._window

        rows = self._conn.execute(
            """
            SELECT c.chunk_id, c.document_id, c.version_id,
                   d.canonical_title, c.section_path, c.text,
                   c.text_preview, d.source_path, d.sensitivity_level
            FROM chunks c
            JOIN documents d ON d.document_id = c.document_id
            WHERE c.version_id = ?
              AND c.chunk_ordinal BETWEEN ? AND ?
              AND c.chunk_id != ?
            ORDER BY c.chunk_ordinal
            """,
            (candidate.version_id, lo, hi, candidate.chunk_id),
        ).fetchall()

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
            )
            for row in rows
        ]
