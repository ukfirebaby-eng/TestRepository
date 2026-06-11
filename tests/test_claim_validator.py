from core.accuracy.deterministic_validator import validate_claim
from core.accuracy.schemas import ExtractedClaim


def _claim(**overrides):
    data = {
        "claim_id": "claim_1",
        "document_id": "doc_1",
        "claim_type": "dependency",
        "subject": "Cloud migration",
        "predicate": "requires",
        "object": "Security certification",
        "modality": "must",
        "certainty": "explicit",
        "evidence_span_ids": ["span_1"],
        "source_quote": "Cloud migration requires Security certification.",
        "confidence": 0.9,
    }
    data.update(overrides)
    return ExtractedClaim(**data)


def test_explicit_claim_with_evidence_can_promote():
    result = validate_claim(_claim(), known_span_ids={"span_1"})

    assert result.status == "passed"
    assert result.can_promote is True
    assert result.reasons == []


def test_unknown_evidence_span_fails():
    result = validate_claim(_claim(), known_span_ids=set())

    assert result.status == "failed"
    assert result.can_promote is False
    assert "Unknown evidence span: span_1" in result.reasons


def test_inferred_claim_needs_review():
    result = validate_claim(_claim(certainty="inferred"), known_span_ids={"span_1"})

    assert result.status == "needs_review"
    assert result.can_promote is False
    assert "Only explicit claims can be auto-promoted." in result.reasons


def test_low_confidence_claim_needs_review():
    result = validate_claim(_claim(confidence=0.41), known_span_ids={"span_1"})

    assert result.status == "needs_review"
    assert result.can_promote is False
    assert "Confidence below promotion threshold." in result.reasons


def test_canonical_self_reference_claim_needs_review():
    result = validate_claim(
        _claim(
            subject="Orion Payments Modernisation Programme",
            object="Orion Payments Modernisation",
            source_quote="The Orion Payments Modernisation Programme depends on the programme being ready.",
        ),
        known_span_ids={"span_1"},
    )

    assert result.status == "needs_review"
    assert result.can_promote is False
    assert "Claim subject and object resolve to the same entity." in result.reasons


def test_generic_endpoint_claim_needs_review():
    result = validate_claim(
        _claim(
            subject="The programme",
            object="approval",
            source_quote="The programme requires approval.",
        ),
        known_span_ids={"span_1"},
    )

    assert result.status == "needs_review"
    assert result.can_promote is False
    assert "Claim subject is too generic for graph promotion: The programme." in result.reasons
    assert "Claim object is too generic for graph promotion: approval." in result.reasons


def test_specific_governance_endpoint_can_promote():
    result = validate_claim(
        _claim(
            subject="Cloud migration",
            object="Security Steering Board approval",
            source_quote="Cloud migration requires Security Steering Board approval.",
        ),
        known_span_ids={"span_1"},
    )

    assert result.status == "passed"
    assert result.can_promote is True
