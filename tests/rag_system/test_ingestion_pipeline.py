"""Tests for the ingestion pipeline."""

import pytest

from rag_system.ingestion.pipeline import IngestionPipeline
from rag_system.models import IngestRequest
from rag_system.retrieval.hybrid import HybridRetriever
from rag_system.storage.document_store import InMemoryDocumentStore
from rag_system.storage.index_store import InMemoryIndexStore


def _make_pipeline() -> IngestionPipeline:
    retriever = HybridRetriever()
    doc_store = InMemoryDocumentStore()
    idx_store = InMemoryIndexStore()
    return IngestionPipeline(
        retriever=retriever,
        document_store=doc_store,
        index_store=idx_store,
    )


class TestIngestionPipeline:
    def test_ingest_text_success(self):
        pipeline = _make_pipeline()
        req = IngestRequest(
            text="This is a test document about retrieval augmented generation.",
            doc_id="doc1",
            tenant_id="t1",
        )
        response = pipeline.ingest(req)
        assert response.doc_id == "doc1"
        assert response.tenant_id == "t1"
        assert response.chunks_created >= 1
        assert response.status == "success"

    def test_ingested_doc_searchable(self):
        pipeline = _make_pipeline()
        req = IngestRequest(
            text="Reciprocal rank fusion combines multiple retrieval methods.",
            doc_id="doc1",
            tenant_id="t1",
        )
        pipeline.ingest(req)
        from rag_system.ingestion.embedder import MockEmbedder
        emb = MockEmbedder().embed("reciprocal rank fusion")
        results = pipeline.retriever.retrieve("reciprocal rank fusion", emb, "t1")
        assert len(results) > 0

    def test_ingest_persists_to_document_store(self):
        pipeline = _make_pipeline()
        req = IngestRequest(text="Hello world.", doc_id="d1", tenant_id="t1")
        pipeline.ingest(req)
        doc = pipeline.document_store.get_document("d1", "t1")
        assert doc is not None
        assert doc.doc_id == "d1"
        assert len(doc.chunks) >= 1

    def test_ingest_records_in_index_store(self):
        pipeline = _make_pipeline()
        req = IngestRequest(text="Hello world.", doc_id="d1", tenant_id="t1")
        pipeline.ingest(req)
        chunk_ids = pipeline.index_store.get_chunk_ids("t1", "d1")
        assert len(chunk_ids) >= 1

    def test_reindex_updates_embeddings(self):
        pipeline = _make_pipeline()
        req = IngestRequest(text="Original content.", doc_id="d1", tenant_id="t1")
        pipeline.ingest(req)
        n = pipeline.reindex("t1")
        assert n == 1

    def test_ingest_empty_text_returns_partial(self):
        pipeline = _make_pipeline()
        req = IngestRequest(text="", doc_id="d1", tenant_id="t1")
        response = pipeline.ingest(req)
        assert response.chunks_created == 0
        assert response.status == "partial"

    def test_ingest_acl_tags_stored_on_chunks(self):
        pipeline = _make_pipeline()
        req = IngestRequest(
            text="Confidential document content.",
            doc_id="d1",
            tenant_id="t1",
            acl_tags=["confidential"],
        )
        pipeline.ingest(req)
        doc = pipeline.document_store.get_document("d1", "t1")
        assert doc is not None
        for chunk in doc.chunks:
            assert "confidential" in chunk.acl_tags

    def test_reindex_with_specific_doc_ids(self):
        pipeline = _make_pipeline()
        for i in range(3):
            pipeline.ingest(IngestRequest(
                text=f"Document {i} content.",
                doc_id=f"d{i}",
                tenant_id="t1",
            ))
        n = pipeline.reindex("t1", doc_ids=["d0", "d1"])
        assert n == 2
