import json

from datetime import datetime, timezone

from core.accuracy.claim_extractor import (
    ClaimExtractionResult,
    batch_evidence_spans,
    dedupe_claims,
    extract_claims_with_failures,
    parse_claim_response,
    parse_claim_response_with_failures,
)
from core.accuracy.schemas import EvidenceSpan, ExtractionFailure, ExtractedClaim


def _span(index: int, text: str = "Cloud migration requires Security certification.") -> EvidenceSpan:
    return EvidenceSpan(
        span_id=f"span_{index}",
        document_id="doc_1",
        chunk_id=f"chunk_{index}",
        page_number=1,
        text=text,
        span_type="sentence",
        source_hash="source_hash",
    )


def _claim(claim_id: str = "claim_1") -> ExtractedClaim:
    return ExtractedClaim(
        claim_id=claim_id,
        document_id="doc_1",
        claim_type="dependency",
        subject="Cloud migration",
        predicate="requires",
        object="Security certification",
        modality="must",
        certainty="explicit",
        status="active",
        evidence_span_ids=["span_1"],
        source_quote="Cloud migration requires Security certification.",
        confidence=0.88,
    )


def test_parse_claim_response_returns_claims():
    payload = json.dumps({
        "claims": [
            {
                "claim_id": "claim_doc_1_span_1_000",
                "document_id": "doc_1",
                "claim_type": "dependency",
                "subject": "Cloud migration",
                "predicate": "requires",
                "object": "Security certification",
                "modality": "must",
                "certainty": "explicit",
                "status": "active",
                "evidence_span_ids": ["span_1"],
                "source_quote": "Cloud migration requires Security certification.",
                "confidence": 0.88,
            }
        ]
    })

    claims = parse_claim_response(payload)

    assert len(claims) == 1
    assert claims[0].subject == "Cloud migration"


def test_parse_claim_response_rejects_malformed_claims():
    payload = json.dumps({
        "claims": [
            {
                "claim_id": "claim_bad",
                "document_id": "doc_1",
                "claim_type": "dependency",
                "subject": "Cloud migration",
                "predicate": "requires",
                "object": "Security certification",
                "modality": "must",
                "certainty": "explicit",
                "evidence_span_ids": [],
                "source_quote": "Cloud migration requires Security certification.",
                "confidence": 0.88,
            }
        ]
    })

    claims = parse_claim_response(payload)

    assert claims == []


def test_parse_claim_response_with_failures_records_invalid_json():
    result = parse_claim_response_with_failures(
        "{not-json",
        document_id="doc_1",
        span_ids=["span_1"],
    )

    assert result.claims == []
    assert len(result.failures) == 1
    assert result.failures[0].document_id == "doc_1"
    assert result.failures[0].span_id == "span_1"
    assert result.failures[0].agent == "claim_extractor"
    assert "JSON" in result.failures[0].error


def test_parse_claim_response_with_failures_records_malformed_claims():
    payload = json.dumps({
        "claims": [
            {
                "claim_id": "claim_bad",
                "document_id": "doc_1",
                "claim_type": "dependency",
                "subject": "Cloud migration",
                "predicate": "requires",
                "object": "Security Certification",
                "modality": "must",
                "certainty": "explicit",
                "evidence_span_ids": [],
                "source_quote": "Cloud migration requires Security Certification.",
                "confidence": 0.88,
            }
        ]
    })

    result = parse_claim_response_with_failures(
        payload,
        document_id="doc_1",
        span_ids=["span_1"],
    )

    assert result.claims == []
    assert len(result.failures) == 1
    assert result.failures[0].span_id == "span_1"
    assert "at least one evidence span is required" in result.failures[0].error


def test_batch_evidence_spans_splits_by_count():
    batches = batch_evidence_spans([_span(index) for index in range(5)], max_spans=2, max_chars=1000)

    assert [[span.span_id for span in batch] for batch in batches] == [
        ["span_0", "span_1"],
        ["span_2", "span_3"],
        ["span_4"],
    ]


def test_batch_evidence_spans_splits_by_character_budget():
    batches = batch_evidence_spans(
        [
            _span(1, text="a" * 20),
            _span(2, text="b" * 20),
            _span(3, text="c" * 20),
        ],
        max_spans=10,
        max_chars=45,
    )

    assert [[span.span_id for span in batch] for batch in batches] == [
        ["span_1", "span_2"],
        ["span_3"],
    ]


def test_dedupe_claims_collapses_duplicate_claims():
    duplicate = _claim("claim_duplicate")

    claims = dedupe_claims([_claim("claim_1"), duplicate])

    assert [claim.claim_id for claim in claims] == ["claim_1"]


def test_extract_claims_with_failures_continues_after_failed_batch(monkeypatch):
    failure = ExtractionFailure(
        id="failure_1",
        document_id="doc_1",
        span_id="span_2",
        agent="claim_extractor",
        error="Model call failed: timeout",
        raw_payload="{}",
        created_at=datetime.now(timezone.utc),
    )

    def fake_extract_batch(spans):
        if spans[0].span_id == "span_2":
            return ClaimExtractionResult(claims=[], failures=[failure])
        return ClaimExtractionResult(claims=[_claim(f"claim_{spans[0].span_id}")], failures=[])

    monkeypatch.setattr("core.accuracy.claim_extractor._extract_claim_batch", fake_extract_batch)

    result = extract_claims_with_failures(
        [_span(1), _span(2), _span(3)],
        max_spans_per_batch=1,
        max_chars_per_batch=1000,
    )

    assert len(result.claims) == 1
    assert result.failures == [failure]
    assert result.metrics == {
        "batches_attempted": 3,
        "batches_succeeded": 2,
        "batches_failed": 1,
        "claims_before_dedupe": 2,
        "claims_after_dedupe": 1,
    }
