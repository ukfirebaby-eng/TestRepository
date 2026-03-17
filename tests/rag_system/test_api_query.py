"""Tests for the query API endpoints."""

import pytest
from fastapi.testclient import TestClient

from rag_system.agent.graph import build_graph
from rag_system.api.main import create_app
from rag_system.ingestion.embedder import MockEmbedder
from rag_system.ingestion.pipeline import IngestionPipeline
from rag_system.models import IngestRequest
from rag_system.reranking.base import MockReranker
from rag_system.retrieval.hybrid import HybridRetriever
from rag_system.storage.document_store import InMemoryDocumentStore
from rag_system.storage.index_store import InMemoryIndexStore


@pytest.fixture
def client():
    """Create a test FastAPI client with mock components pre-loaded."""
    app = create_app()

    # Build and wire mock components directly (bypass lifespan)
    retriever = HybridRetriever()
    embedder = MockEmbedder()
    reranker = MockReranker()
    doc_store = InMemoryDocumentStore()
    idx_store = InMemoryIndexStore()

    pipeline = IngestionPipeline(
        retriever=retriever,
        document_store=doc_store,
        index_store=idx_store,
        embedder=embedder,
    )

    # Pre-ingest a document
    pipeline.ingest(IngestRequest(
        text="Hybrid search combines BM25 and dense vector retrieval using RRF fusion.",
        doc_id="test_doc",
        tenant_id="t1",
    ))

    graph = build_graph(
        retriever=retriever,
        reranker=reranker,
        embedder=embedder,
        llm_client=None,
        document_store=doc_store,
    )

    app.state.retriever = retriever
    app.state.embedder = embedder
    app.state.reranker = reranker
    app.state.document_store = doc_store
    app.state.index_store = idx_store
    app.state.pipeline = pipeline
    app.state.graph = graph
    app.state.settings = None

    with TestClient(app) as c:
        yield c


HEADERS = {"X-API-Key": "dev-key"}


class TestQueryEndpoint:
    def test_query_returns_200(self, client):
        resp = client.post(
            "/v1/query",
            json={"query": "What is hybrid search?", "tenant_id": "t1"},
            headers=HEADERS,
        )
        assert resp.status_code == 200

    def test_query_response_has_answer(self, client):
        resp = client.post(
            "/v1/query",
            json={"query": "hybrid search", "tenant_id": "t1"},
            headers=HEADERS,
        )
        data = resp.json()
        assert "answer" in data
        assert len(data["answer"]) > 5

    def test_query_response_has_trace_id(self, client):
        resp = client.post(
            "/v1/query",
            json={"query": "search", "tenant_id": "t1"},
            headers=HEADERS,
        )
        data = resp.json()
        assert "trace_id" in data
        assert data["trace_id"]

    def test_query_response_has_latency(self, client):
        resp = client.post(
            "/v1/query",
            json={"query": "search", "tenant_id": "t1"},
            headers=HEADERS,
        )
        data = resp.json()
        assert data["latency_ms"] >= 0

    def test_query_without_api_key_returns_401(self, client):
        resp = client.post(
            "/v1/query",
            json={"query": "test", "tenant_id": "t1"},
        )
        assert resp.status_code == 401

    def test_query_with_wrong_api_key_returns_401(self, client):
        resp = client.post(
            "/v1/query",
            json={"query": "test", "tenant_id": "t1"},
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 401

    def test_query_empty_query_handled(self, client):
        resp = client.post(
            "/v1/query",
            json={"query": "", "tenant_id": "t1"},
            headers=HEADERS,
        )
        # Should return 200 but with a graceful error answer
        assert resp.status_code == 200

    def test_query_response_schema(self, client):
        resp = client.post(
            "/v1/query",
            json={"query": "BM25", "tenant_id": "t1"},
            headers=HEADERS,
        )
        data = resp.json()
        assert "answer" in data
        assert "citations" in data
        assert "confidence" in data
        assert "retrieval_mode_used" in data
        assert "trace_id" in data
        assert "latency_ms" in data
        assert "used_retry_loop" in data


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_ready_returns_200(self, client):
        resp = client.get("/v1/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert "ready" in data
        assert "checks" in data
