"""Shared Pydantic models for the RAG system."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Core document / chunk models
# ---------------------------------------------------------------------------

class Chunk(BaseModel):
    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    doc_id: str
    tenant_id: str
    section_title: str = ""
    breadcrumbs: list[str] = Field(default_factory=list)
    source_uri: str = ""
    version: str = "1"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    acl_tags: list[str] = Field(default_factory=list)
    document_type: str = "text"
    semantic_text: str
    raw_text: str
    embedding: list[float] = Field(default_factory=list)
    keyword_fields: dict[str, Any] = Field(default_factory=dict)
    # Reranking score (set after rerank step)
    rerank_score: float | None = None
    # Position in final ranked list
    rank: int | None = None


class Document(BaseModel):
    doc_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    title: str = ""
    source_uri: str = ""
    document_type: str = "text"
    version: str = "1"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    acl_tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    chunks: list[Chunk] = Field(default_factory=list)
    is_deleted: bool = False


# ---------------------------------------------------------------------------
# Query / answer models
# ---------------------------------------------------------------------------

class Citation(BaseModel):
    chunk_id: str
    doc_id: str
    section_title: str = ""
    source_uri: str = ""
    excerpt: str = ""
    rank: int | None = None


class QueryRequest(BaseModel):
    query: str
    tenant_id: str
    user_id: str = "anonymous"
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    retrieval_mode: Literal["balanced_hybrid", "lexical_first", "semantic_first"] = "balanced_hybrid"
    filters: dict[str, Any] = Field(default_factory=dict)
    max_chunks: int | None = None
    stream: bool = False


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = 1.0
    retrieval_mode_used: str = "balanced_hybrid"
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    latency_ms: float = 0.0
    used_retry_loop: bool = False
    evidence_sufficient: bool = True
    query_classification: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Ingestion models
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    text: str | None = None
    url: str | None = None
    doc_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    title: str = ""
    source_uri: str = ""
    document_type: str = "text"
    acl_tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    doc_id: str
    tenant_id: str
    chunks_created: int
    status: Literal["success", "partial", "failed"] = "success"
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class ReindexRequest(BaseModel):
    tenant_id: str
    doc_ids: list[str] | None = None  # None = reindex all


class ReindexResponse(BaseModel):
    queued_docs: int
    status: str = "queued"


# ---------------------------------------------------------------------------
# Retrieval internal models
# ---------------------------------------------------------------------------

class RetrievalAttempt(BaseModel):
    attempt_number: int
    query: str
    mode: str
    filters: dict[str, Any] = Field(default_factory=dict)
    bm25_candidates: int = 0
    dense_candidates: int = 0
    fused_candidates: int = 0
    reranked_candidates: int = 0
    latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# Eval models
# ---------------------------------------------------------------------------

class EvalRequest(BaseModel):
    dataset_name: str = "default"
    tenant_id: str = "eval"
    max_queries: int | None = None


class EvalResult(BaseModel):
    dataset_name: str
    num_queries: int
    ndcg_at_10: float
    citation_precision: float
    faithfulness: float
    avg_latency_ms: float
    loop_rate: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Health models
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"] = "ok"
    version: str = "0.1.0"
    backend: str = "memory"
    components: dict[str, str] = Field(default_factory=dict)


class ReadyResponse(BaseModel):
    ready: bool
    checks: dict[str, bool] = Field(default_factory=dict)
