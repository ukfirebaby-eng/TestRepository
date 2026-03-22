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
    EdgeType,
    FrictionSeverity,
    FrictionType,
    GroundingReport,
    NodeType,
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
# Graph management (nodes / edges / temporal metadata / friction)
# ---------------------------------------------------------------------------


class CreateNodeRequest(BaseModel):
    workspace_id: str
    node_type: NodeType
    name: str
    description: Optional[str] = None
    phase: Optional[str] = None
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NodeResponse(BaseModel):
    node_id: str
    workspace_id: str
    node_type: NodeType
    name: str
    description: Optional[str] = None
    phase: Optional[str] = None
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


class CreateEdgeRequest(BaseModel):
    workspace_id: str
    source_node_id: str
    target_node_id: str
    edge_type: EdgeType = EdgeType.DEPENDS_ON
    weight: float = 1.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EdgeResponse(BaseModel):
    edge_id: str
    workspace_id: str
    source_node_id: str
    target_node_id: str
    edge_type: EdgeType
    weight: float
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


class SetTemporalMetadataRequest(BaseModel):
    planned_start: Optional[str] = None
    planned_end: Optional[str] = None
    actual_start: Optional[str] = None
    actual_end: Optional[str] = None
    duration_days: Optional[float] = None
    slack_days: Optional[float] = None


class TemporalMetadataResponse(BaseModel):
    node_id: str
    planned_start: Optional[str] = None
    planned_end: Optional[str] = None
    actual_start: Optional[str] = None
    actual_end: Optional[str] = None
    duration_days: Optional[float] = None
    slack_days: Optional[float] = None
    updated_at: str


class CreateFrictionRequest(BaseModel):
    workspace_id: str
    friction_type: FrictionType
    severity: FrictionSeverity = FrictionSeverity.MEDIUM
    source_node_id: Optional[str] = None
    target_node_id: Optional[str] = None
    description: str
    chunk_id: Optional[str] = None


class FrictionItemResponse(BaseModel):
    friction_id: str
    workspace_id: str
    friction_type: FrictionType
    severity: FrictionSeverity
    source_node_id: Optional[str] = None
    target_node_id: Optional[str] = None
    description: str
    chunk_id: Optional[str] = None
    provenance_text: Optional[str] = None   # snippet from the originating chunk
    resolved: bool
    resolved_at: Optional[str] = None
    created_at: str


# ---------------------------------------------------------------------------
# Strategic reports
# ---------------------------------------------------------------------------


class VulnerabilityNode(BaseModel):
    node_id: str
    name: str
    node_type: str
    phase: Optional[str]
    in_degree: int
    centrality_score: float
    cascade_size: int
    cascade_depth: int
    risk_level: str     # "critical" | "high" | "medium" | "low"


class VulnerabilityReport(BaseModel):
    workspace_id: str
    generated_at: str
    total_nodes: int
    total_edges: int
    nodes: List[VulnerabilityNode]


class RiskCascadeNode(BaseModel):
    node_id: str
    name: str
    node_type: str
    phase: Optional[str]
    cascade_size: int
    cascade_depth: int
    systemic_vulnerability_index: float


class RiskCascadeReport(BaseModel):
    workspace_id: str
    generated_at: str
    nodes: List[RiskCascadeNode]


class UnmappedNode(BaseModel):
    node_id: str
    name: str
    node_type: str
    phase: Optional[str]
    reason: str


class GQMAlignmentReport(BaseModel):
    workspace_id: str
    generated_at: str
    total_operational_nodes: int
    mapped_count: int
    unmapped_count: int
    alignment_ratio: float
    unmapped_nodes: List[UnmappedNode]


# ---------------------------------------------------------------------------
# Tactical reports
# ---------------------------------------------------------------------------


class ScheduleCollisionEntry(BaseModel):
    successor_node_id: str
    successor_name: str
    predecessor_node_id: str
    predecessor_name: str
    predecessor_planned_end: Optional[str]
    successor_planned_start: Optional[str]
    overlap_days: float
    phase: Optional[str]


class ScheduleCollapseReport(BaseModel):
    workspace_id: str
    generated_at: str
    total_collisions: int
    collisions: List[ScheduleCollisionEntry]


class BottleneckNode(BaseModel):
    node_id: str
    name: str
    phase: Optional[str]
    structural_friction_count: int
    temporal_friction_count: int
    total_friction: int
    critical_count: int
    priority_score: float
    triage_rank: int


class BottleneckTriageReport(BaseModel):
    workspace_id: str
    generated_at: str
    bottlenecks: List[BottleneckNode]


class ITDOPhase(BaseModel):
    phase: str
    critical_paradox_count: int
    total_friction_count: int
    trigger_fired: bool
    recommended_action: str


class ITDOReport(BaseModel):
    workspace_id: str
    generated_at: str
    itdo_threshold: int
    phases: List[ITDOPhase]


# ---------------------------------------------------------------------------
# Operational reports
# ---------------------------------------------------------------------------


class FrictionQueueReport(BaseModel):
    workspace_id: str
    generated_at: str
    total_unresolved: int
    items: List[FrictionItemResponse]


class DocumentTrustScore(BaseModel):
    document_id: str
    canonical_title: str
    total_nodes: int
    friction_generating_nodes: int
    trust_score: float          # 0.0 – 1.0
    trust_debt: float           # 1.0 - trust_score
    risk_band: str              # "low" | "medium" | "high" | "critical"


class TrustScoreReport(BaseModel):
    workspace_id: str
    generated_at: str
    documents: List[DocumentTrustScore]


# ---------------------------------------------------------------------------
# Error response
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
