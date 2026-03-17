"""Dense vector retrieval backend (in-memory, dev/test mode).

Uses numpy cosine similarity for vector search.
In production, this would be replaced by an Elasticsearch/OpenSearch kNN backend.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from rag_system.models import Chunk
from rag_system.retrieval.base import RetrievalBackend
from rag_system.retrieval.filters import apply_filters_to_chunk


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class InMemoryDenseBackend(RetrievalBackend):
    """In-memory dense vector retrieval backend using numpy."""

    def __init__(self) -> None:
        self._chunks: dict[str, Chunk] = {}  # chunk_id -> Chunk

    def index(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            self._chunks[chunk.chunk_id] = chunk

    def delete(self, doc_id: str, tenant_id: str) -> int:
        to_delete = [
            cid for cid, c in self._chunks.items()
            if c.doc_id == doc_id and c.tenant_id == tenant_id
        ]
        for cid in to_delete:
            del self._chunks[cid]
        return len(to_delete)

    def bm25_search(
        self,
        query: str,
        tenant_id: str,
        filters: dict[str, Any],
        k: int,
    ) -> list[tuple[str, float]]:
        # Dense backend does not handle BM25; delegated to BM25Backend
        return []

    def dense_search(
        self,
        embedding: list[float],
        tenant_id: str,
        filters: dict[str, Any],
        k: int,
    ) -> list[tuple[str, float]]:
        if not embedding:
            return []

        query_vec = np.array(embedding, dtype=np.float32)
        scored: list[tuple[str, float]] = []

        for chunk_id, chunk in self._chunks.items():
            if not chunk.embedding:
                continue
            if not apply_filters_to_chunk(chunk, filters):
                continue
            chunk_vec = np.array(chunk.embedding, dtype=np.float32)
            score = _cosine_similarity(query_vec, chunk_vec)
            scored.append((chunk_id, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def get_chunks(self, chunk_ids: list[str]) -> list[Chunk]:
        return [self._chunks[cid] for cid in chunk_ids if cid in self._chunks]

    def get_all_chunks(self, tenant_id: str) -> list[Chunk]:
        return [c for c in self._chunks.values() if c.tenant_id == tenant_id]
