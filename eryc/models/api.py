"""
API request and response models for ERYC Document Intelligence Console.

These models define the public contract for the REST API described in §7.2
and Appendix C of the specification.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from eryc.models.domain import (
    Citation,
    GroundingReport,
    RunDiagnostics,
    RunStatus,
    SensitivityLevel,
)


# ---------------------------------------------------------------------------
# Query endpoint  (spec §7.2 — POST /v1/query)
# ---------------------------------------------------------------------------


class QueryFilters(BaseModel):
    """Filters applied to scope a query to a subset of indexed content."""

    workspace_id: str
    collection_ids: Optional[List[str]] = None
    doc_types: Optional[List[str]] = None
    sensitivity_levels: Optional[List[SensitivityLevel]] = None
    time_from: Optional[str] = None
    time_to: Optional[str] = None
    entity_ids: Optional[List[str]] = None


class ResponseOptions(BaseModel):
    stream: bool = False
    max_citations: int = Field(default=8, ge=1, le=20)


class QueryRequest(BaseModel):
    """Request body for POST /v1/query  (spec §7.3 example payload)."""

    thread_id: Optional[str] = None
    query: str = Field(..., min_length=1, max_length=4096)
    filters: QueryFilters
    response_options: ResponseOptions = Field(default_factory=ResponseOptions)


class QueryResponse(BaseModel):
    """Successful query response  (spec Appendix C)."""

    run_id: str
    thread_id: str
    status: RunStatus
    answer: Optional[str] = None
    citations: List[Citation] = Field(default_factory=list)
    grounding: Optional[GroundingReport] = None
    diagnostics: RunDiagnostics = Field(default_factory=RunDiagnostics)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Ingest endpoint  (spec §7.2 — POST /v1/documents/ingest)
# ---------------------------------------------------------------------------


class IngestRequest(BaseModel):
    """Request body for POST /v1/documents/ingest."""

    workspace_id: str
    collection_id: Optional[str] = None
    source_path: str
    doc_type: Optional[str] = None
    sensitivity_level: SensitivityLevel = SensitivityLevel.STANDARD
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    job_id: str
    status: str
    message: str


# ---------------------------------------------------------------------------
# Run history endpoint  (spec §7.2 — GET /v1/runs/{run_id})
# ---------------------------------------------------------------------------


class RunResponse(BaseModel):
    run_id: str
    thread_id: str
    user_id: str
    query: str
    status: RunStatus
    answer: Optional[str] = None
    citations: List[Citation] = Field(default_factory=list)
    grounding: Optional[GroundingReport] = None
    diagnostics: RunDiagnostics = Field(default_factory=RunDiagnostics)
    error_message: Optional[str] = None
    started_at: str
    completed_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Feedback endpoint  (spec §7.2 — POST /v1/feedback)
# ---------------------------------------------------------------------------


class FeedbackRequest(BaseModel):
    run_id: str
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    reason_code: Optional[str] = None
    comment: Optional[str] = Field(default=None, max_length=2000)


class FeedbackResponse(BaseModel):
    feedback_id: str
    message: str


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    version: str
    db_ok: bool
    vector_search_available: bool


# ---------------------------------------------------------------------------
# Workspace / collection management
# ---------------------------------------------------------------------------


class CreateWorkspaceRequest(BaseModel):
    name: str
    domain_pack: str = "generic"


class CreateCollectionRequest(BaseModel):
    workspace_id: str
    name: str
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# Entity management
# ---------------------------------------------------------------------------


class CreateEntityRequest(BaseModel):
    """Request body for POST /v1/entities."""

    workspace_id: str
    entity_type: str
    name: str
    canonical_name: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EntityResponse(BaseModel):
    entity_id: str
    workspace_id: str
    entity_type: str
    name: str
    canonical_name: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


# ---------------------------------------------------------------------------
# Error response
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
