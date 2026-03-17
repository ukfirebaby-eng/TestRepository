"""BM25 lexical retrieval backend (in-memory, dev/test mode).

Uses the rank_bm25 library for BM25Okapi scoring.
In production, this would be replaced by an Elasticsearch/OpenSearch backend.
"""

from __future__ import annotations

import re
from typing import Any

from rag_system.models import Chunk
from rag_system.retrieval.base import RetrievalBackend
from rag_system.retrieval.filters import apply_filters_to_chunk


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer."""
    return re.findall(r"\b\w+\b", text.lower())


class InMemoryBM25Backend(RetrievalBackend):
    """In-memory BM25 backend using rank_bm25.

    Not thread-safe for concurrent index + search. Use a lock in production.
    """

    def __init__(self) -> None:
        self._chunks: dict[str, Chunk] = {}  # chunk_id -> Chunk
        self._bm25: Any = None
        self._indexed_ids: list[str] = []
        self._dirty = True

    def index(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            self._chunks[chunk.chunk_id] = chunk
        self._dirty = True

    def delete(self, doc_id: str, tenant_id: str) -> int:
        to_delete = [
            cid for cid, c in self._chunks.items()
            if c.doc_id == doc_id and c.tenant_id == tenant_id
        ]
        for cid in to_delete:
            del self._chunks[cid]
        if to_delete:
            self._dirty = True
        return len(to_delete)

    def _rebuild_index(self) -> None:
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as e:
            raise ImportError("rank_bm25 is required: pip install rank-bm25") from e

        self._indexed_ids = list(self._chunks.keys())
        corpus = [_tokenize(self._chunks[cid].semantic_text) for cid in self._indexed_ids]
        self._bm25 = BM25Okapi(corpus) if corpus else None
        self._dirty = False

    def bm25_search(
        self,
        query: str,
        tenant_id: str,
        filters: dict[str, Any],
        k: int,
    ) -> list[tuple[str, float]]:
        if self._dirty:
            self._rebuild_index()

        if not self._bm25 or not self._indexed_ids:
            return []

        tokens = _tokenize(query)
        raw_scores = self._bm25.get_scores(tokens)

        # Pair scores with chunk_ids and filter
        # Note: BM25Okapi can produce negative scores when a term appears in all
        # documents (IDF becomes negative). Include all non-zero-scored chunks
        # and let top-K sorting determine relevance.
        scored = [
            (self._indexed_ids[i], float(raw_scores[i]))
            for i in range(len(self._indexed_ids))
            if raw_scores[i] != 0
            and apply_filters_to_chunk(self._chunks[self._indexed_ids[i]], filters)
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def dense_search(
        self,
        embedding: list[float],
        tenant_id: str,
        filters: dict[str, Any],
        k: int,
    ) -> list[tuple[str, float]]:
        # BM25 backend does not handle dense search; delegated to DenseBackend
        return []

    def get_chunks(self, chunk_ids: list[str]) -> list[Chunk]:
        return [self._chunks[cid] for cid in chunk_ids if cid in self._chunks]

    def get_all_chunks(self, tenant_id: str) -> list[Chunk]:
        return [c for c in self._chunks.values() if c.tenant_id == tenant_id]
