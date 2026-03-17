"""Ingestion pipeline: parse → chunk → embed → index.

Orchestrates the full ingestion flow for a document.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from rag_system.ingestion.chunker import Chunker
from rag_system.ingestion.embedder import BaseEmbedder, MockEmbedder
from rag_system.ingestion.metadata import classify_document_type, compute_acl_tags, extract_metadata
from rag_system.ingestion.parsers.html import HTMLParser
from rag_system.ingestion.parsers.pdf import PDFParser
from rag_system.ingestion.parsers.text import TextParser
from rag_system.models import Document, IngestRequest, IngestResponse

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """End-to-end document ingestion pipeline."""

    def __init__(
        self,
        retriever=None,  # HybridRetriever
        document_store=None,  # InMemoryDocumentStore
        index_store=None,  # InMemoryIndexStore
        object_store=None,  # LocalObjectStore (optional)
        embedder: BaseEmbedder | None = None,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
    ) -> None:
        self.retriever = retriever
        self.document_store = document_store
        self.index_store = index_store
        self.object_store = object_store
        self.embedder = embedder or MockEmbedder()
        self.chunker = Chunker(chunk_size=chunk_size, overlap=chunk_overlap)

        self._parsers = {
            "text": TextParser(),
            "html": HTMLParser(),
            "pdf": PDFParser(),
            "markdown": TextParser(),
        }

    def ingest(self, request: IngestRequest) -> IngestResponse:
        """Ingest a document from text or URL content."""
        trace_id = f"ingest-{request.doc_id}"

        # Resolve content
        if request.text is not None:
            content = request.text.encode("utf-8")
            source_uri = request.source_uri or request.doc_id
        else:
            raise ValueError("Either 'text' must be provided in IngestRequest")

        doc_type = classify_document_type(source_uri, content)
        if request.document_type and request.document_type != "text":
            doc_type = request.document_type

        metadata = extract_metadata(
            content=content,
            source_uri=source_uri,
            document_type=doc_type,
            extra=request.metadata,
        )
        acl_tags = compute_acl_tags(request.tenant_id, metadata, request.acl_tags or None)

        # Parse
        parser = self._parsers.get(doc_type, self._parsers["text"])
        parsed = parser.parse(content, source_uri=source_uri)

        # Chunk
        chunks = self.chunker.chunk_document(
            doc=parsed,
            doc_id=request.doc_id,
            tenant_id=request.tenant_id,
            acl_tags=acl_tags,
            document_type=doc_type,
            source_uri=source_uri,
            extra_metadata=request.metadata,
        )

        if not chunks:
            return IngestResponse(
                doc_id=request.doc_id,
                tenant_id=request.tenant_id,
                chunks_created=0,
                status="partial",
                trace_id=trace_id,
            )

        # Embed
        texts = [c.semantic_text for c in chunks]
        embeddings = self.embedder.embed_texts(texts)
        for chunk, emb in zip(chunks, embeddings):
            chunk.embedding = emb

        # Build document record
        doc = Document(
            doc_id=request.doc_id,
            tenant_id=request.tenant_id,
            title=request.title or parsed.title,
            source_uri=source_uri,
            document_type=doc_type,
            acl_tags=acl_tags,
            metadata=metadata,
            chunks=chunks,
        )

        # Remove old version if reindexing
        if self.index_store:
            old_ids = self.index_store.get_chunk_ids(request.tenant_id, request.doc_id)
            if old_ids and self.retriever:
                self.retriever.delete(request.doc_id, request.tenant_id)

        # Persist
        if self.document_store:
            self.document_store.save_document(doc)

        if self.retriever:
            self.retriever.index(chunks)

        if self.index_store:
            self.index_store.record_indexed(
                request.tenant_id,
                request.doc_id,
                [c.chunk_id for c in chunks],
            )

        if self.object_store:
            self.object_store.put(
                request.tenant_id, request.doc_id, "raw", content
            )

        logger.info(
            "Ingested doc=%s tenant=%s chunks=%d",
            request.doc_id, request.tenant_id, len(chunks),
        )

        return IngestResponse(
            doc_id=request.doc_id,
            tenant_id=request.tenant_id,
            chunks_created=len(chunks),
            status="success",
            trace_id=trace_id,
        )

    def reindex(self, tenant_id: str, doc_ids: list[str] | None = None) -> int:
        """Reindex documents. Returns number of documents reindexed."""
        if not self.document_store:
            return 0

        docs = self.document_store.list_documents(tenant_id)
        if doc_ids is not None:
            docs = [d for d in docs if d.doc_id in set(doc_ids)]

        reindexed = 0
        for doc in docs:
            if not doc.chunks:
                continue
            # Re-embed and re-index
            texts = [c.semantic_text for c in doc.chunks]
            embeddings = self.embedder.embed_texts(texts)
            for chunk, emb in zip(doc.chunks, embeddings):
                chunk.embedding = emb

            if self.retriever:
                self.retriever.delete(doc.doc_id, tenant_id)
                self.retriever.index(doc.chunks)

            if self.index_store:
                self.index_store.record_indexed(
                    tenant_id, doc.doc_id, [c.chunk_id for c in doc.chunks]
                )
            reindexed += 1

        return reindexed
