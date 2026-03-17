"""Hybrid retriever: combines BM25 + dense vector search via RRF fusion."""

from __future__ import annotations

from typing import Any, Literal

from rag_system.models import Chunk
from rag_system.retrieval.bm25 import InMemoryBM25Backend
from rag_system.retrieval.dense import InMemoryDenseBackend
from rag_system.retrieval.rrf import reciprocal_rank_fusion


class HybridRetriever:
    """Hybrid retriever combining BM25 and dense vector search with RRF fusion.

    This class owns two backends (bm25 + dense) that share the same chunk store
    for in-memory mode. Both backends are indexed whenever chunks are added.

    The retrieval mode controls the contribution of each signal:
    - balanced_hybrid: equal contribution from both BM25 and dense (default)
    - lexical_first:   BM25 gets more candidates; dense gets fewer
    - semantic_first:  dense gets more candidates; BM25 gets fewer
    """

    def __init__(
        self,
        bm25_backend: InMemoryBM25Backend | None = None,
        dense_backend: InMemoryDenseBackend | None = None,
        rrf_k: int = 60,
    ) -> None:
        self.bm25 = bm25_backend or InMemoryBM25Backend()
        self.dense = dense_backend or InMemoryDenseBackend()
        self.rrf_k = rrf_k

    def index(self, chunks: list[Chunk]) -> None:
        """Index chunks into both backends."""
        self.bm25.index(chunks)
        self.dense.index(chunks)

    def delete(self, doc_id: str, tenant_id: str) -> int:
        """Delete all chunks for a document from both backends."""
        n1 = self.bm25.delete(doc_id, tenant_id)
        self.dense.delete(doc_id, tenant_id)
        return n1

    def retrieve(
        self,
        query: str,
        embedding: list[float],
        tenant_id: str,
        filters: dict[str, Any] | None = None,
        bm25_k: int = 50,
        dense_k: int = 50,
        mode: Literal["balanced_hybrid", "lexical_first", "semantic_first"] = "balanced_hybrid",
    ) -> list[Chunk]:
        """Retrieve chunks using hybrid search with RRF fusion.

        Args:
            query: The text query for BM25 search.
            embedding: The query embedding for dense vector search.
            tenant_id: Tenant identifier for index isolation.
            filters: Additional metadata filters.
            bm25_k: Number of BM25 candidates to retrieve.
            dense_k: Number of dense candidates to retrieve.
            mode: Retrieval mode controlling the candidate allocation.

        Returns:
            List of Chunk objects sorted by RRF score (best first).
        """
        if filters is None:
            filters = {"tenant_id": tenant_id}
        else:
            filters = {"tenant_id": tenant_id, **filters}

        # Adjust candidate counts based on mode
        if mode == "lexical_first":
            actual_bm25_k = int(bm25_k * 1.5)
            actual_dense_k = int(dense_k * 0.5)
        elif mode == "semantic_first":
            actual_bm25_k = int(bm25_k * 0.5)
            actual_dense_k = int(dense_k * 1.5)
        else:  # balanced_hybrid
            actual_bm25_k = bm25_k
            actual_dense_k = dense_k

        # Run both searches
        bm25_results = self.bm25.bm25_search(query, tenant_id, filters, actual_bm25_k)
        dense_results = self.dense.dense_search(embedding, tenant_id, filters, actual_dense_k)

        bm25_ranking = [chunk_id for chunk_id, _ in bm25_results]
        dense_ranking = [chunk_id for chunk_id, _ in dense_results]

        # Fuse with RRF
        rankings: list[list[str]] = []
        if bm25_ranking:
            rankings.append(bm25_ranking)
        if dense_ranking:
            rankings.append(dense_ranking)

        if not rankings:
            return []

        fused = reciprocal_rank_fusion(rankings, k=self.rrf_k)

        # Collect all unique chunk IDs in fused order
        all_ids = [chunk_id for chunk_id, _ in fused]
        chunk_map = {c.chunk_id: c for c in self.bm25.get_chunks(all_ids)}

        # Also check dense backend for any chunks not in bm25 index
        missing = [cid for cid in all_ids if cid not in chunk_map]
        if missing:
            for c in self.dense.get_chunks(missing):
                chunk_map[c.chunk_id] = c

        result: list[Chunk] = []
        for rank_0based, (chunk_id, rrf_score) in enumerate(fused):
            chunk = chunk_map.get(chunk_id)
            if chunk:
                chunk = chunk.model_copy(
                    update={"rerank_score": rrf_score, "rank": rank_0based + 1}
                )
                result.append(chunk)

        return result

    def get_all_chunks(self, tenant_id: str) -> list[Chunk]:
        return self.bm25.get_all_chunks(tenant_id)
