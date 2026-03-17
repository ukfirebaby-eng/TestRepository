"""Tests for hybrid retrieval (BM25 + dense + RRF)."""

import pytest

from rag_system.models import Chunk
from rag_system.retrieval.bm25 import InMemoryBM25Backend
from rag_system.retrieval.dense import InMemoryDenseBackend
from rag_system.retrieval.hybrid import HybridRetriever


def _make_chunk(
    chunk_id: str,
    tenant_id: str,
    text: str,
    embedding: list[float] | None = None,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id="doc1",
        tenant_id=tenant_id,
        semantic_text=text,
        raw_text=text,
        embedding=embedding or [],
    )


class TestBM25Backend:
    def test_basic_search(self):
        backend = InMemoryBM25Backend()
        c = _make_chunk("c1", "t1", "reciprocal rank fusion hybrid search")
        backend.index([c])
        results = backend.bm25_search("hybrid search", "t1", {"tenant_id": "t1"}, k=10)
        assert len(results) > 0
        assert results[0][0] == "c1"

    def test_no_match_returns_empty(self):
        backend = InMemoryBM25Backend()
        c = _make_chunk("c1", "t1", "machine learning neural network")
        backend.index([c])
        results = backend.bm25_search("quantum physics", "t1", {"tenant_id": "t1"}, k=10)
        assert results == []

    def test_delete_removes_chunk(self):
        backend = InMemoryBM25Backend()
        c = _make_chunk("c1", "t1", "some text to find")
        backend.index([c])
        backend.delete("doc1", "t1")
        results = backend.bm25_search("some text", "t1", {"tenant_id": "t1"}, k=10)
        assert results == []

    def test_tenant_isolation(self):
        backend = InMemoryBM25Backend()
        c1 = _make_chunk("c1", "tenant_a", "python programming language")
        c2 = _make_chunk("c2", "tenant_b", "python programming language")
        backend.index([c1, c2])
        results = backend.bm25_search("python", "tenant_a", {"tenant_id": "tenant_a"}, k=10)
        ids = [r[0] for r in results]
        assert "c1" in ids
        assert "c2" not in ids

    def test_multiple_chunks_ranked(self):
        backend = InMemoryBM25Backend()
        chunks = [
            _make_chunk("c1", "t1", "cat dog animal"),
            _make_chunk("c2", "t1", "cat cat cat feline animal"),
            _make_chunk("c3", "t1", "unrelated content"),
        ]
        backend.index(chunks)
        results = backend.bm25_search("cat", "t1", {"tenant_id": "t1"}, k=5)
        ids = [r[0] for r in results]
        assert "c3" not in ids or ids.index("c3") > ids.index("c2")


class TestDenseBackend:
    def test_cosine_similarity_search(self):
        backend = InMemoryDenseBackend()
        # Two chunks with similar embeddings
        c1 = _make_chunk("c1", "t1", "text1", embedding=[1.0, 0.0, 0.0])
        c2 = _make_chunk("c2", "t1", "text2", embedding=[0.0, 1.0, 0.0])
        backend.index([c1, c2])

        # Query close to c1
        results = backend.dense_search([0.9, 0.1, 0.0], "t1", {"tenant_id": "t1"}, k=5)
        assert results[0][0] == "c1"

    def test_no_embedding_skipped(self):
        backend = InMemoryDenseBackend()
        c = _make_chunk("c1", "t1", "text", embedding=[])
        backend.index([c])
        results = backend.dense_search([1.0, 0.0], "t1", {"tenant_id": "t1"}, k=5)
        assert results == []

    def test_empty_query_returns_empty(self):
        backend = InMemoryDenseBackend()
        c = _make_chunk("c1", "t1", "text", embedding=[1.0, 0.0])
        backend.index([c])
        results = backend.dense_search([], "t1", {"tenant_id": "t1"}, k=5)
        assert results == []


class TestHybridRetriever:
    def _setup_retriever(self) -> HybridRetriever:
        retriever = HybridRetriever()
        chunks = [
            Chunk(
                chunk_id="c1",
                doc_id="doc1",
                tenant_id="t1",
                semantic_text="reciprocal rank fusion is a hybrid search technique",
                raw_text="reciprocal rank fusion is a hybrid search technique",
                embedding=[1.0, 0.0, 0.0],
            ),
            Chunk(
                chunk_id="c2",
                doc_id="doc1",
                tenant_id="t1",
                semantic_text="BM25 is a lexical retrieval algorithm",
                raw_text="BM25 is a lexical retrieval algorithm",
                embedding=[0.0, 1.0, 0.0],
            ),
            Chunk(
                chunk_id="c3",
                doc_id="doc1",
                tenant_id="t1",
                semantic_text="dense vector search uses embeddings",
                raw_text="dense vector search uses embeddings",
                embedding=[0.0, 0.0, 1.0],
            ),
        ]
        retriever.index(chunks)
        return retriever

    def test_hybrid_returns_results(self):
        retriever = self._setup_retriever()
        results = retriever.retrieve(
            query="hybrid search fusion",
            embedding=[1.0, 0.0, 0.0],
            tenant_id="t1",
        )
        assert len(results) > 0

    def test_hybrid_results_are_chunks(self):
        retriever = self._setup_retriever()
        results = retriever.retrieve(
            query="BM25 lexical",
            embedding=[0.0, 1.0, 0.0],
            tenant_id="t1",
        )
        assert all(isinstance(r, Chunk) for r in results)

    def test_hybrid_results_have_rank(self):
        retriever = self._setup_retriever()
        results = retriever.retrieve(
            query="search",
            embedding=[1.0, 0.0, 0.0],
            tenant_id="t1",
        )
        assert all(r.rank is not None for r in results)

    def test_delete_removes_from_both_backends(self):
        retriever = self._setup_retriever()
        retriever.delete("doc1", "t1")
        results = retriever.retrieve(
            query="hybrid search",
            embedding=[1.0, 0.0, 0.0],
            tenant_id="t1",
        )
        assert results == []

    def test_lexical_first_mode(self):
        retriever = self._setup_retriever()
        results = retriever.retrieve(
            query="reciprocal rank",
            embedding=[1.0, 0.0, 0.0],
            tenant_id="t1",
            mode="lexical_first",
        )
        assert len(results) > 0
        assert results[0].chunk_id == "c1"

    def test_semantic_first_mode(self):
        retriever = self._setup_retriever()
        results = retriever.retrieve(
            query="irrelevant query",
            embedding=[0.0, 0.0, 1.0],  # close to c3
            tenant_id="t1",
            mode="semantic_first",
        )
        assert len(results) > 0
        assert results[0].chunk_id == "c3"

    def test_tenant_isolation(self):
        retriever = HybridRetriever()
        c1 = Chunk(
            chunk_id="c1", doc_id="d1", tenant_id="tenant_a",
            semantic_text="exclusive tenant A content",
            raw_text="exclusive tenant A content",
            embedding=[1.0, 0.0],
        )
        c2 = Chunk(
            chunk_id="c2", doc_id="d2", tenant_id="tenant_b",
            semantic_text="exclusive tenant B content",
            raw_text="exclusive tenant B content",
            embedding=[0.0, 1.0],
        )
        retriever.index([c1, c2])
        results = retriever.retrieve("content", [1.0, 0.0], "tenant_a")
        ids = {r.chunk_id for r in results}
        assert "c2" not in ids
