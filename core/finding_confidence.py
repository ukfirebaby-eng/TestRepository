from typing import Any, Dict, List, Optional


def _number(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed == parsed else default


def _has_text(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _list_values(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if _has_text(value):
        return [str(value).strip()]
    return []


def _level(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.65:
        return "medium"
    return "low"


def _claim_provenance_strength(
    *,
    claim_ids: Any,
    evidence_span_ids: Any,
    claim_validation_status: str = "",
    graph_agreement: str = "",
) -> Optional[float]:
    claims = _list_values(claim_ids)
    spans = _list_values(evidence_span_ids)
    validation = claim_validation_status.strip().lower()
    agreement = graph_agreement.strip().lower()

    if claims and validation in {"passed", "validated"}:
        return 1.0
    if claims and spans:
        return 0.85
    if claims:
        return 0.75
    if spans:
        return 0.7
    if agreement == "legacy_only":
        return 0.45
    return None


def score_finding_confidence(
    *,
    model_confidence: Any,
    severity: Any = None,
    probability: Any = None,
    source_name: str = "",
    target_name: str = "",
    evidence_summary: str = "",
    blocked_work: str = "",
    blocking_condition: str = "",
    claim_ids: Any = None,
    evidence_span_ids: Any = None,
    claim_validation_status: str = "",
    graph_agreement: str = "",
) -> Dict[str, Any]:
    """Scores trust in a finding using deterministic signals available at ingestion time."""
    model = max(0.0, min(_number(model_confidence), 1.0))
    evidence_fields = [_has_text(evidence_summary), _has_text(blocked_work), _has_text(blocking_condition)]
    evidence_completeness = round(sum(evidence_fields) / len(evidence_fields), 4)
    graph_specificity = 0.7 if source_name and target_name and source_name == target_name else 1.0
    risk_score_availability = 1.0 if _number(severity) > 0 and _number(probability) > 0 else 0.6
    base_score = (
        (model * 0.5)
        + (evidence_completeness * 0.2)
        + (graph_specificity * 0.15)
        + (risk_score_availability * 0.15)
    )
    claim_provenance_strength = _claim_provenance_strength(
        claim_ids=claim_ids,
        evidence_span_ids=evidence_span_ids,
        claim_validation_status=claim_validation_status,
        graph_agreement=graph_agreement,
    )
    provenance_adjustment = 0.0
    if claim_provenance_strength == 1.0:
        provenance_adjustment = 0.05
    elif claim_provenance_strength is not None and claim_provenance_strength >= 0.85:
        provenance_adjustment = 0.03
    elif claim_provenance_strength is not None and claim_provenance_strength >= 0.7:
        provenance_adjustment = 0.01
    elif claim_provenance_strength is not None and claim_provenance_strength <= 0.45:
        provenance_adjustment = -0.04

    score = round(max(0.0, min(base_score + provenance_adjustment, 1.0)), 2)
    factors = {
        "model_confidence": round(model, 4),
        "evidence_completeness": evidence_completeness,
        "graph_specificity": graph_specificity,
        "risk_score_availability": risk_score_availability,
    }
    if claim_provenance_strength is not None:
        factors["claim_provenance_strength"] = claim_provenance_strength

    return {
        "confidence_score": score,
        "confidence_level": _level(score),
        "confidence_factors": factors,
    }
