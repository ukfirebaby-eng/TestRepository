from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from core.accuracy.schemas import (
    BoundingBox,
    DocumentManifest,
    EvidenceSpan,
    ExtractedClaim,
    ValidationResult,
)


def test_evidence_span_requires_text_and_source_hash():
    span = EvidenceSpan(
        span_id="span_doc_1",
        document_id="doc_1",
        chunk_id="chunk_1",
        page_number=1,
        text="Security certification must complete before migration starts.",
        span_type="sentence",
        bbox=BoundingBox(x0=1.0, y0=2.0, x1=3.0, y1=4.0),
        source_hash="abc123",
    )

    assert span.text.startswith("Security certification")
    assert span.bbox.x1 == 3.0


def test_claim_without_evidence_is_invalid():
    with pytest.raises(ValidationError):
        ExtractedClaim(
            claim_id="claim_1",
            document_id="doc_1",
            claim_type="dependency",
            subject="Cloud migration",
            predicate="requires",
            object="Security certification",
            modality="must",
            certainty="explicit",
            evidence_span_ids=[],
            source_quote="Cloud migration requires Security certification.",
            confidence=0.91,
        )


def test_document_manifest_tracks_source_hash_and_versions():
    manifest = DocumentManifest(
        document_id="doc_1",
        filename="strategy.md",
        source_hash="sha256:abc",
        ingested_at=datetime.now(timezone.utc),
        llm_model="gpt-4o-mini",
    )

    assert manifest.parser_version == "legacy-parser-v1"
    assert manifest.schema_version == "claim-layer-v1"
    assert manifest.validation_status == "pending"


def test_validation_result_controls_promotion():
    result = ValidationResult(
        claim_id="claim_1",
        document_id="doc_1",
        status="needs_review",
        reasons=["Inferred claims require human review before promotion."],
        can_promote=False,
    )

    assert result.can_promote is False
