"""Tool definitions for the RAG agent.

These tools can be used by an LLM-driven agent to perform retrieval operations.
They wrap the core retrieval and storage services in a tool-calling interface.
"""

from __future__ import annotations

from typing import Any


def make_search_hybrid_tool(retriever, embedder):
    """Create a hybrid search tool."""
    def search_hybrid(
        query: str,
        tenant_id: str,
        k: int = 50,
        mode: str = "balanced_hybrid",
        filters: dict | None = None,
    ) -> list[dict]:
        """Execute hybrid (BM25 + dense) search with RRF fusion."""
        embedding = embedder.embed(query)
        chunks = retriever.retrieve(
            query=query,
            embedding=embedding,
            tenant_id=tenant_id,
            filters=filters or {},
            bm25_k=k,
            dense_k=k,
            mode=mode,
        )
        return [
            {
                "chunk_id": c.chunk_id,
                "doc_id": c.doc_id,
                "section_title": c.section_title,
                "text": c.semantic_text[:500],
                "rank": c.rank,
                "score": c.rerank_score,
            }
            for c in chunks
        ]

    search_hybrid.__name__ = "search_hybrid"
    return search_hybrid


def make_rerank_tool(reranker):
    """Create a rerank tool."""
    def rerank_documents(
        query: str,
        chunk_ids: list[str],
        chunks_data: list[dict],
        top_n: int = 8,
    ) -> list[dict]:
        """Rerank a set of chunks by relevance to the query."""
        from rag_system.models import Chunk
        chunks = []
        for item in chunks_data:
            chunks.append(Chunk(
                chunk_id=item["chunk_id"],
                doc_id=item.get("doc_id", ""),
                tenant_id=item.get("tenant_id", ""),
                semantic_text=item.get("text", ""),
                raw_text=item.get("text", ""),
            ))
        reranked = reranker.rerank(query, chunks, top_n)
        return [
            {
                "chunk_id": c.chunk_id,
                "text": c.semantic_text[:500],
                "rank": c.rank,
                "score": c.rerank_score,
            }
            for c in reranked
        ]

    rerank_documents.__name__ = "rerank_documents"
    return rerank_documents


def make_fetch_document_tool(document_store):
    """Create a fetch document tool."""
    def fetch_document(doc_id: str, tenant_id: str) -> dict | None:
        """Fetch a document by ID."""
        doc = document_store.get_document(doc_id, tenant_id)
        if doc is None:
            return None
        return {
            "doc_id": doc.doc_id,
            "title": doc.title,
            "source_uri": doc.source_uri,
            "chunk_count": len(doc.chunks),
        }

    fetch_document.__name__ = "fetch_document"
    return fetch_document
