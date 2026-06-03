from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class BoundingBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class DocumentManifest(BaseModel):
    document_id: str
    filename: str
    mime_type: str = "application/octet-stream"
    source_hash: str
    ingested_at: datetime
    parser_version: str = "legacy-parser-v1"
    schema_version: str = "claim-layer-v1"
    embedding_model: str = "chromadb-default"
    llm_model: str = ""
    document_anchor_date: date | None = None
    validation_status: Literal["pending", "partial", "passed", "failed"] = "pending"


class EvidenceSpan(BaseModel):
    span_id: str
    document_id: str
    chunk_id: str
    page_number: int
    section_title: str = ""
    text: str
    span_type: Literal[
        "sentence",
        "paragraph",
        "table_row",
        "table_cell",
        "caption",
        "heading",
    ]
    bbox: BoundingBox | None = None
    source_hash: str

    @field_validator("text", "source_hash")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped


class ExtractedClaim(BaseModel):
    claim_id: str
    document_id: str
    claim_type: Literal[
        "dependency",
        "blocker",
        "objective",
        "success_criterion",
        "date_constraint",
        "resource_requirement",
        "owner_assignment",
        "risk",
        "assumption",
        "deliverable",
        "scope_inclusion",
        "scope_exclusion",
        "governance_rule",
        "quality_requirement",
    ]
    subject: str
    predicate: str
    object: str
    modality: Literal["must", "should", "may", "assumes", "prohibits"]
    certainty: Literal["explicit", "implied", "inferred"]
    status: Literal["active", "superseded", "rejected", "unknown"] = "active"
    date_start: date | None = None
    date_end: date | None = None
    owner: str = ""
    evidence_span_ids: list[str]
    source_quote: str
    confidence: float = Field(ge=0.0, le=1.0)
    validation_status: Literal["pending", "passed", "failed", "needs_review"] = "pending"

    @field_validator("subject", "predicate", "object", "source_quote")
    @classmethod
    def _require_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @field_validator("evidence_span_ids")
    @classmethod
    def _require_evidence(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("at least one evidence span is required")
        return cleaned


class ValidationResult(BaseModel):
    claim_id: str
    document_id: str
    status: Literal["passed", "failed", "needs_review"]
    reasons: list[str]
    can_promote: bool


class ExtractionFailure(BaseModel):
    id: str
    document_id: str
    span_id: str
    agent: str
    error: str
    raw_payload: str
    created_at: datetime


class CanonicalEntity(BaseModel):
    entity_id: str
    canonical_name: str
    entity_type: Literal[
        "initiative",
        "team",
        "system",
        "deadline",
        "resource",
        "risk",
        "objective",
        "deliverable",
    ]
    aliases: list[str] = Field(default_factory=list)
    source_span_ids: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    human_locked: bool = False


class PromotedGraphEdge(BaseModel):
    edge_id: str
    document_id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    claim_id: str
    modality: str
    certainty: str
    status: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_span_ids: list[str]
    validation_status: Literal["passed"]


class Finding(BaseModel):
    finding_id: str
    document_id: str
    finding_type: str
    severity: int = Field(ge=1, le=5)
    summary: str
    claims_involved: list[str]
    evidence_span_ids: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str
    recommended_action: str
    human_review_status: Literal["pending", "accepted", "rejected"] = "pending"
