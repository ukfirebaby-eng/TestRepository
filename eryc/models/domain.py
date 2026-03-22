"""
Core domain models for ERYC Document Intelligence Console.

These models mirror the relational schema defined in §8 and are used
throughout the application for type-safe data passing.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SensitivityLevel(str, Enum):
    STANDARD = "standard"
    RESTRICTED = "restricted"
    CONFIDENTIAL = "confidential"


class AccessScope(str, Enum):
    WORKSPACE = "workspace"
    COLLECTION = "collection"
    PRIVATE = "private"


class IndexStatus(str, Enum):
    PENDING = "pending"
    INDEXED = "indexed"
    FAILED = "failed"


class IngestJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class QueryClass(str, Enum):
    """Query classes as defined in spec §5.2."""

    KEYWORD_EXACT = "keyword_exact"
    SEMANTIC = "semantic"
    MIXED = "mixed"
    AUTHORITATIVE_LOOKUP = "authoritative_lookup"
    CONSISTENCY_CHECK = "consistency_check"
    EVIDENCE_STATE = "evidence_state"
    TIMELINE_QUERY = "timeline_query"
    ENTITY_SUMMARY = "entity_summary"


class RetrievalMode(str, Enum):
    LEXICAL = "lexical"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class EvidenceVerdict(str, Enum):
    ENOUGH = "enough"
    NEEDS_MORE = "needs_more"
    INSUFFICIENT = "insufficient"


class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"


# ---------------------------------------------------------------------------
# Core domain entities
# ---------------------------------------------------------------------------


class User(BaseModel):
    user_id: str
    username: str
    role: UserRole = UserRole.USER
    created_at: datetime
    updated_at: datetime


class Workspace(BaseModel):
    workspace_id: str
    name: str
    domain_pack: str = "generic"
    created_at: datetime
    updated_at: datetime


class Collection(BaseModel):
    collection_id: str
    workspace_id: str
    name: str
    description: Optional[str] = None
    created_at: datetime


class Document(BaseModel):
    document_id: str
    workspace_id: str
    collection_id: Optional[str] = None
    doc_type: str
    canonical_title: str
    current_version_id: Optional[str] = None
    source_path: Optional[str] = None
    sensitivity_level: SensitivityLevel = SensitivityLevel.STANDARD
    access_scope: AccessScope = AccessScope.WORKSPACE
    created_at: datetime
    updated_at: datetime


class DocumentVersion(BaseModel):
    version_id: str
    document_id: str
    version_number: int
    content_hash: str
    parsed_at: Optional[datetime] = None
    indexed_at: Optional[datetime] = None
    index_status: IndexStatus = IndexStatus.PENDING
    created_at: datetime


class Chunk(BaseModel):
    chunk_id: str
    version_id: str
    document_id: str
    chunk_ordinal: int
    section_path: str
    token_count: int
    text: str
    text_preview: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Entity(BaseModel):
    entity_id: str
    workspace_id: str
    entity_type: str
    name: str
    canonical_name: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


# ---------------------------------------------------------------------------
# Run and citation models
# ---------------------------------------------------------------------------


class Citation(BaseModel):
    """Version-pinned citation as described in spec §10 and Appendix C."""

    citation_id: str
    run_id: str
    chunk_id: str
    document_id: str
    version_id: str
    title: str
    locator: Optional[str] = None
    source_path: Optional[str] = None
    snippet: Optional[str] = None
    ordinal: int = 0


class GroundingReport(BaseModel):
    """Grounding validation result as in Appendix C."""

    verdict: str  # "pass" | "fail"
    citation_coverage: float  # 0.0–1.0
    unsupported_claims: int


class RunDiagnostics(BaseModel):
    query_class: Optional[str] = None
    retrieval_rounds: int = 0
    retrieval_mode: Optional[str] = None
    total_candidates: int = 0
    reranker_used: bool = False
    reranker_timed_out: bool = False


class Run(BaseModel):
    run_id: str
    thread_id: str
    user_id: str
    query: str
    filters: Dict[str, Any] = Field(default_factory=dict)
    status: RunStatus = RunStatus.PENDING
    query_class: Optional[str] = None
    retrieval_mode: Optional[str] = None
    retrieval_rounds: int = 0
    answer: Optional[str] = None
    grounding: Optional[GroundingReport] = None
    diagnostics: RunDiagnostics = Field(default_factory=RunDiagnostics)
    error_message: Optional[str] = None
    citations: List[Citation] = Field(default_factory=list)
    started_at: datetime
    completed_at: Optional[datetime] = None


class IngestJob(BaseModel):
    job_id: str
    workspace_id: str
    collection_id: Optional[str] = None
    source_path: str
    doc_type: Optional[str] = None
    sensitivity_level: SensitivityLevel = SensitivityLevel.STANDARD
    status: IngestJobStatus = IngestJobStatus.QUEUED
    document_id: Optional[str] = None
    error_message: Optional[str] = None
    queued_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Retrieval models (used internally by the retrieval layer)
# ---------------------------------------------------------------------------


class CandidateChunk(BaseModel):
    """A retrieved chunk candidate with ranking metadata."""

    chunk_id: str
    document_id: str
    version_id: str
    canonical_title: str
    section_path: str
    text: str
    text_preview: str
    source_path: Optional[str] = None
    sensitivity_level: str = "standard"
    lexical_rank: Optional[int] = None
    semantic_rank: Optional[int] = None
    rrf_score: float = 0.0
    rerank_score: Optional[float] = None


class RetrievalDiagnostics(BaseModel):
    mode: RetrievalMode
    query: str
    lexical_hits: int = 0
    semantic_hits: int = 0
    fused_count: int = 0
    final_count: int = 0
    rrf_k: int = 60


# ---------------------------------------------------------------------------
# Temporal Knowledge Graph models
# ---------------------------------------------------------------------------


class NodeType(str, Enum):
    GOAL = "goal"
    PHASE = "phase"
    TASK = "task"
    RESOURCE = "resource"


class EdgeType(str, Enum):
    DEPENDS_ON = "depends_on"
    CONTRIBUTES_TO = "contributes_to"
    BLOCKS = "blocks"


class FrictionType(str, Enum):
    STRUCTURAL = "structural"   # Red — logical paradox
    TEMPORAL = "temporal"       # Yellow — timing conflict


class FrictionSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class GraphNode(BaseModel):
    node_id: str
    workspace_id: str
    node_type: NodeType
    name: str
    description: Optional[str] = None
    phase: Optional[str] = None
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class GraphEdge(BaseModel):
    edge_id: str
    workspace_id: str
    source_node_id: str
    target_node_id: str
    edge_type: EdgeType = EdgeType.DEPENDS_ON
    weight: float = 1.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class TemporalMetadata(BaseModel):
    node_id: str
    planned_start: Optional[datetime] = None
    planned_end: Optional[datetime] = None
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    duration_days: Optional[float] = None
    slack_days: Optional[float] = None
    updated_at: datetime


class FrictionItem(BaseModel):
    friction_id: str
    workspace_id: str
    friction_type: FrictionType
    severity: FrictionSeverity = FrictionSeverity.MEDIUM
    source_node_id: Optional[str] = None
    target_node_id: Optional[str] = None
    description: str
    chunk_id: Optional[str] = None
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    created_at: datetime
