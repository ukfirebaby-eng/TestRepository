"""Tests for the ingestion API endpoints."""

import pytest
from fastapi.testclient import TestClient

from rag_system.agent.graph import build_graph
from rag_system.api.main import create_app
from rag_system.ingestion.embedder import MockEmbedder
from rag_system.ingestion.pipeline import IngestionPipeline
from rag_system.reranking.base import MockReranker
from rag_system.retrieval.hybrid import HybridRetriever
from rag_system.storage.document_store import InMemoryDocumentStore
from rag_system.storage.index_store import InMemoryIndexStore


@pytest.fixture
def client():
    app = create_app()

    retriever = HybridRetriever()
    embedder = MockEmbedder()
    doc_store = InMemoryDocumentStore()
    idx_store = InMemoryIndexStore()

    pipeline = IngestionPipeline(
        retriever=retriever,
        document_store=doc_store,
        index_store=idx_store,
        embedder=embedder,
    )

    graph = build_graph(
        retriever=retriever,
        reranker=MockReranker(),
        embedder=embedder,
        document_store=doc_store,
    )

    app.state.retriever = retriever
    app.state.embedder = embedder
    app.state.document_store = doc_store
    app.state.index_store = idx_store
    app.state.pipeline = pipeline
    app.state.graph = graph
    app.state.settings = None

    with TestClient(app) as c:
        yield c


HEADERS = {"X-API-Key": "dev-key"}


class TestIngestEndpoint:
    def test_ingest_returns_200(self, client):
        resp = client.post(
            "/v1/ingest",
            json={"text": "Test document content.", "doc_id": "d1", "tenant_id": "t1"},
            headers=HEADERS,
        )
        assert resp.status_code == 200

    def test_ingest_response_schema(self, client):
        resp = client.post(
            "/v1/ingest",
            json={"text": "Document content here.", "doc_id": "d2", "tenant_id": "t1"},
            headers=HEADERS,
        )
        data = resp.json()
        assert data["doc_id"] == "d2"
        assert data["tenant_id"] == "t1"
        assert data["chunks_created"] >= 1
        assert data["status"] == "success"

    def test_ingest_without_api_key_returns_401(self, client):
        resp = client.post(
            "/v1/ingest",
            json={"text": "content", "doc_id": "d3", "tenant_id": "t1"},
        )
        assert resp.status_code == 401

    def test_ingest_makes_document_searchable(self, client):
        client.post(
            "/v1/ingest",
            json={
                "text": "Vector databases store high-dimensional embeddings for similarity search.",
                "doc_id": "d_vec",
                "tenant_id": "t1",
            },
            headers=HEADERS,
        )
        resp = client.post(
            "/v1/query",
            json={"query": "vector database embeddings", "tenant_id": "t1"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["answer"]) > 5

    def test_ingest_empty_text_returns_partial(self, client):
        resp = client.post(
            "/v1/ingest",
            json={"text": "", "doc_id": "d_empty", "tenant_id": "t1"},
            headers=HEADERS,
        )
        data = resp.json()
        assert data["status"] == "partial"
        assert data["chunks_created"] == 0

    def test_get_document_after_ingest(self, client):
        client.post(
            "/v1/ingest",
            json={"text": "Some important document.", "doc_id": "d_get", "tenant_id": "t1"},
            headers=HEADERS,
        )
        resp = client.get(
            "/v1/documents/d_get",
            params={"tenant_id": "t1"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["doc_id"] == "d_get"
        assert data["chunk_count"] >= 1

    def test_get_nonexistent_document_returns_404(self, client):
        resp = client.get(
            "/v1/documents/nonexistent",
            params={"tenant_id": "t1"},
            headers=HEADERS,
        )
        assert resp.status_code == 404


class TestReindexEndpoint:
    def test_reindex_returns_200(self, client):
        client.post(
            "/v1/ingest",
            json={"text": "Content to reindex.", "doc_id": "dr1", "tenant_id": "t1"},
            headers=HEADERS,
        )
        resp = client.post(
            "/v1/reindex",
            json={"tenant_id": "t1"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["queued_docs"] >= 1
