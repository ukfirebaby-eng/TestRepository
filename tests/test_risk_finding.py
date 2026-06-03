from core.risk_finding import build_risk_finding


def test_builds_structured_finding_from_model_output():
    result = {
        "confidence": 0.91,
        "severity": 4,
        "probability": 4,
        "analysis": "Make approved transaction history a hard entry criterion.",
        "finding": {
            "title": "Audit evidence starts before source data approval",
            "risk_type": "evidence readiness",
            "affected_entity": "Orion Payments Modernisation Programme",
            "blocked_work": "board sign-off",
            "blocking_condition": "approved transaction history",
            "evidence_summary": "The plan generates audit evidence before transaction history is approved.",
            "why_it_matters": "Board sign-off could be based on invalid evidence.",
            "recommended_action": "Move evidence production after transaction history approval.",
            "assumptions": ["The transaction history approval is mandatory."],
        },
    }

    finding = build_risk_finding(
        result,
        risk_type="structural",
        source_name="Orion Payments Modernisation Programme",
        target_name="Orion Payments Modernisation Programme",
        relationship="structural friction",
        blocked_work="board sign-off",
        blocking_condition="approved transaction history",
    )

    assert finding["title"] == "Audit evidence starts before source data approval"
    assert finding["affected_entity"] == "Orion Payments Modernisation Programme"
    assert finding["recommended_action"] == "Move evidence production after transaction history approval."
    assert finding["confidence"] == 0.91
    assert finding["confidence_score"] == 0.91
    assert finding["confidence_level"] == "high"
    assert finding["confidence_factors"] == {
        "model_confidence": 0.91,
        "evidence_completeness": 1.0,
        "graph_specificity": 0.7,
        "risk_score_availability": 1.0,
    }
    assert finding["assumptions"] == ["The transaction history approval is mandatory."]


def test_builds_finding_with_validated_claim_provenance():
    result = {
        "confidence": 0.91,
        "severity": 4,
        "probability": 4,
        "analysis": "Move evidence production after transaction history approval.",
        "finding": {
            "title": "Audit evidence starts before source data approval",
            "risk_type": "evidence readiness",
            "affected_entity": "Orion Payments Modernisation Programme",
            "blocked_work": "board sign-off",
            "blocking_condition": "approved transaction history",
            "evidence_summary": "The plan generates audit evidence before transaction history is approved.",
            "why_it_matters": "Board sign-off could be based on invalid evidence.",
            "recommended_action": "Move evidence production after transaction history approval.",
            "claim_ids": ["claim_1"],
            "evidence_span_ids": ["span_1", "span_2"],
            "claim_validation_status": "passed",
        },
    }

    finding = build_risk_finding(
        result,
        risk_type="structural",
        source_name="Orion Payments Modernisation Programme",
        target_name="Orion Payments Modernisation Programme",
        relationship="structural friction",
        blocked_work="board sign-off",
        blocking_condition="approved transaction history",
    )

    assert finding["claim_ids"] == ["claim_1"]
    assert finding["evidence_span_ids"] == ["span_1", "span_2"]
    assert finding["claim_validation_status"] == "passed"
    assert finding["confidence_score"] == 0.96
    assert finding["confidence_factors"]["claim_provenance_strength"] == 1.0


def test_builds_fallback_finding_when_model_returns_legacy_shape():
    result = {
        "confidence": 0.75,
        "analysis": "Delay dress rehearsal until certification is complete.",
    }

    finding = build_risk_finding(
        result,
        risk_type="timeline",
        source_name="Security Certification",
        target_name="Dress rehearsal",
        relationship="chronological friction",
        blocked_work="Dress rehearsal",
        blocking_condition="Security Certification",
    )

    assert finding["title"] == "Timeline risk affecting Dress rehearsal"
    assert finding["risk_type"] == "timeline"
    assert finding["blocked_work"] == "Dress rehearsal"
    assert finding["blocking_condition"] == "Security Certification"
    assert finding["evidence_summary"] == "Delay dress rehearsal until certification is complete."
    assert finding["confidence"] == 0.75
    assert finding["confidence_score"] == 0.81
    assert finding["confidence_level"] == "medium"
