from typing import Any, Dict, List

from core.finding_confidence import score_finding_confidence


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    if _text(value):
        return [_text(value)]
    return []


def build_risk_finding(
    result: Dict[str, Any],
    *,
    risk_type: str,
    source_name: str,
    target_name: str,
    relationship: str,
    blocked_work: str = "",
    blocking_condition: str = "",
) -> Dict[str, Any]:
    """Builds a stable, user-facing finding from model output plus graph context."""
    raw = result.get("finding") if isinstance(result.get("finding"), dict) else {}
    analysis = _text(result.get("analysis"))
    confidence = result.get("confidence", raw.get("confidence", 0.0))
    affected_entity = _text(raw.get("affected_entity")) or (source_name if source_name == target_name else target_name)
    blocked = _text(raw.get("blocked_work")) or _text(blocked_work) or affected_entity
    blocker = _text(raw.get("blocking_condition")) or _text(blocking_condition) or source_name
    normalised_type = _text(raw.get("risk_type")) or risk_type
    claim_ids = _list(raw.get("claim_ids") or raw.get("claim_id"))
    evidence_span_ids = _list(raw.get("evidence_span_ids") or raw.get("evidence_span_id"))
    claim_validation_status = _text(raw.get("claim_validation_status") or raw.get("validation_status"))
    graph_agreement = _text(raw.get("graph_agreement"))

    title = _text(raw.get("title"))
    if not title:
        title = f"{normalised_type.capitalize()} risk affecting {affected_entity}"

    evidence_summary = _text(raw.get("evidence_summary")) or analysis
    why_it_matters = _text(raw.get("why_it_matters")) or (
        f"{affected_entity} may be delayed, blocked, or approved on unsafe assumptions."
    )
    recommended_action = _text(raw.get("recommended_action")) or analysis

    confidence_payload = score_finding_confidence(
        model_confidence=confidence,
        severity=result.get("severity"),
        probability=result.get("probability"),
        source_name=source_name,
        target_name=target_name,
        evidence_summary=evidence_summary,
        blocked_work=blocked,
        blocking_condition=blocker,
        claim_ids=claim_ids,
        evidence_span_ids=evidence_span_ids,
        claim_validation_status=claim_validation_status,
        graph_agreement=graph_agreement,
    )

    finding = {
        "title": title,
        "risk_type": normalised_type,
        "affected_entity": affected_entity,
        "blocked_work": blocked,
        "blocking_condition": blocker,
        "relationship": relationship,
        "evidence_summary": evidence_summary,
        "why_it_matters": why_it_matters,
        "recommended_action": recommended_action,
        "confidence": confidence,
        **confidence_payload,
        "assumptions": _list(raw.get("assumptions")),
    }
    if claim_ids:
        finding["claim_ids"] = claim_ids
    if evidence_span_ids:
        finding["evidence_span_ids"] = evidence_span_ids
    if claim_validation_status:
        finding["claim_validation_status"] = claim_validation_status
    if graph_agreement:
        finding["graph_agreement"] = graph_agreement
    return finding
