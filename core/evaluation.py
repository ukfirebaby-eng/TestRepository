import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List

from core.accuracy.entity_canonicalizer import canonical_entity_id
from core.orchestrator import DiamondOrchestrator
from core.vault import HybridVault


def _get_canvas_data(vault: Any, document_id: str) -> Dict[str, Any]:
    if hasattr(vault, "get_canvas_data"):
        return vault.get_canvas_data(document_id)

    cursor = vault.conn.cursor()
    cursor.execute("""
        SELECT DISTINCT n.id, n.label, n.name FROM nodes n
        WHERE n.id IN (
            SELECT source_id FROM edges WHERE document_id = ?
            UNION
            SELECT target_id FROM edges WHERE document_id = ?
        )
    """, (document_id, document_id))
    nodes = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT source_id AS source, target_id AS target, relationship, source_chunk_id
        FROM edges WHERE document_id = ?
    """, (document_id,))
    edges = [dict(row) for row in cursor.fetchall()]

    return {"nodes": nodes, "edges": edges}


def collect_document_metrics(vault: Any, document_id: str) -> Dict[str, Any]:
    """Collect stable, non-LLM metrics for regression evaluation."""
    canvas = _get_canvas_data(vault, document_id)
    narrative = vault.get_narrative_report(document_id)
    executive = vault.get_executive_summary(document_id)

    return {
        "node_count": len(canvas.get("nodes", [])),
        "edge_count": len(canvas.get("edges", [])),
        "friction_count": len(vault.get_friction_lines(document_id)),
        "chronological_friction_count": len(vault.get_chronological_friction_lines(document_id)),
        "hub_vulnerability_count": len(vault.get_hub_vulnerabilities(document_id)),
        "risk_matrix_count": len(vault.get_risk_matrix_data(document_id)),
        "narrative_chapter_count": len(narrative.get("chapters", [])) if narrative else 0,
        "narrative_coverage_verified": bool(narrative.get("coverage_verified")) if narrative else False,
        "has_executive_summary": bool(executive),
    }


def compare_metrics(metrics: Dict[str, Any], expectations: Dict[str, Dict[str, Any]]) -> List[str]:
    """Compare collected metrics with exact/min/max expectation rules."""
    failures: List[str] = []

    for key, rules in expectations.items():
        if key not in metrics:
            failures.append(f"{key} is missing")
            continue

        actual = metrics[key]
        if "exact" in rules and actual != rules["exact"]:
            failures.append(f"{key} expected == {rules['exact']}, got {actual}")
        if "min" in rules and actual < rules["min"]:
            failures.append(f"{key} expected >= {rules['min']}, got {actual}")
        if "max" in rules and actual > rules["max"]:
            failures.append(f"{key} expected <= {rules['max']}, got {actual}")

    return failures


def evaluate_document(vault: Any, document_id: str, expectations: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Return metrics plus pass/fail status for a document baseline."""
    metrics = collect_document_metrics(vault, document_id)
    failures = compare_metrics(metrics, expectations)
    return {
        "document_id": document_id,
        "passed": not failures,
        "metrics": metrics,
        "failures": failures,
    }


def load_evaluation_baseline(path: str | Path) -> Dict[str, Any]:
    """Load an evaluation baseline and resolve its document path relative to the baseline file."""
    baseline_path = Path(path)
    data = json.loads(baseline_path.read_text(encoding="utf-8"))
    if "document_path" in data:
        data["document_path"] = (baseline_path.parent / data["document_path"]).resolve()
    return data


def evaluate_baseline(vault: Any, baseline_path: str | Path) -> Dict[str, Any]:
    """Evaluate a vault document against a JSON baseline file."""
    baseline = load_evaluation_baseline(baseline_path)
    result = evaluate_document(vault, baseline["document_id"], baseline["expectations"])
    result["baseline_path"] = str(Path(baseline_path))
    result["document_path"] = str(baseline.get("document_path", ""))
    return result


def _list_or_empty(vault: Any, method_name: str, document_id: str) -> List[Dict[str, Any]]:
    method = getattr(vault, method_name, None)
    if not callable(method):
        return []
    return method(document_id)


def _claim_signature(claim: Dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(claim.get("claim_type", "")).strip().lower(),
        canonical_entity_id(str(claim.get("subject", ""))),
        canonical_entity_id(str(claim.get("object", ""))),
    )


def _expected_claim_signature(claim: Dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(claim.get("claim_type", "")).strip().lower(),
        canonical_entity_id(str(claim.get("subject", ""))),
        canonical_entity_id(str(claim.get("object", ""))),
    )


def collect_claim_layer_metrics(vault: Any, document_id: str) -> Dict[str, Any]:
    """Collect deterministic metrics for the evidence/claim accuracy layer."""
    evidence_spans = _list_or_empty(vault, "list_evidence_spans", document_id)
    claims = _list_or_empty(vault, "list_extracted_claims", document_id)
    validation_results = _list_or_empty(vault, "list_validation_results", document_id)
    canonical_entities = _list_or_empty(vault, "list_canonical_entities", document_id)
    extraction_failures = _list_or_empty(vault, "list_extraction_failures", document_id)
    validation_count = len(validation_results)
    validated_claim_count = sum(1 for item in validation_results if item.get("status") == "passed")
    needs_review_claim_count = sum(1 for item in validation_results if item.get("status") == "needs_review")
    failed_claim_count = sum(1 for item in validation_results if item.get("status") == "failed")
    promotable_claim_count = sum(1 for item in validation_results if item.get("can_promote"))

    return {
        "evidence_span_count": len(evidence_spans),
        "claim_count": len(claims),
        "validated_claim_count": validated_claim_count,
        "needs_review_claim_count": needs_review_claim_count,
        "failed_claim_count": failed_claim_count,
        "promotable_claim_count": promotable_claim_count,
        "canonical_entity_count": len(canonical_entities),
        "extraction_failure_count": len(extraction_failures),
        "validation_pass_rate": round(validated_claim_count / validation_count, 4) if validation_count else 0.0,
        "promotion_rate": round(promotable_claim_count / validation_count, 4) if validation_count else 0.0,
    }


def evaluate_claim_layer(
    vault: Any,
    document_id: str,
    expectations: Dict[str, Any],
) -> Dict[str, Any]:
    """Evaluate stored claim-layer artifacts against expected canonical claims."""
    claims = _list_or_empty(vault, "list_extracted_claims", document_id)
    actual_signatures = {_claim_signature(claim) for claim in claims}
    expected_claims = expectations.get("expected_claims", [])
    matched_claim_count = 0
    missing_claims = []

    for expected_claim in expected_claims:
        if _expected_claim_signature(expected_claim) in actual_signatures:
            matched_claim_count += 1
        else:
            missing_claims.append(expected_claim)

    metrics = collect_claim_layer_metrics(vault, document_id)
    metrics["expected_claim_count"] = len(expected_claims)
    metrics["matched_expected_claim_count"] = matched_claim_count
    metrics["claim_match_rate"] = round(matched_claim_count / len(expected_claims), 4) if expected_claims else 1.0
    failures = compare_metrics(metrics, expectations.get("metrics", {}))
    for missing_claim in missing_claims:
        failures.append(
            "missing expected claim: "
            f"{missing_claim.get('claim_type')} "
            f"{missing_claim.get('subject')} -> {missing_claim.get('object')}"
        )

    return {
        "document_id": document_id,
        "passed": not failures,
        "metrics": metrics,
        "failures": failures,
        "missing_claims": missing_claims,
    }


def evaluate_claim_layer_baseline(vault: Any, baseline_path: str | Path) -> Dict[str, Any]:
    """Evaluate claim-layer artifacts using a JSON fixture baseline."""
    baseline = load_evaluation_baseline(baseline_path)
    result = evaluate_claim_layer(vault, baseline["document_id"], baseline["claim_expectations"])
    result["baseline_path"] = str(Path(baseline_path))
    result["document_path"] = str(baseline.get("document_path", ""))
    return result


def _claim_promoted_edges(vault: Any, document_id: str) -> List[Dict[str, Any]]:
    cursor = vault.conn.cursor()
    cursor.execute(
        """
        SELECT source_id, target_id, relationship, claim_id, evidence_span_ids
        FROM edges
        WHERE document_id = ?
          AND source_chunk_id = 'claim_layer'
        ORDER BY source_id, relationship, target_id
        """,
        (document_id,),
    )
    edges = []
    for row in cursor.fetchall():
        item = dict(row)
        if item.get("evidence_span_ids"):
            try:
                item["evidence_span_ids"] = json.loads(item["evidence_span_ids"])
            except json.JSONDecodeError:
                item["evidence_span_ids"] = []
        else:
            item["evidence_span_ids"] = []
        edges.append(item)
    return edges


def _promoted_edge_signature(edge: Dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(edge.get("source_id", "")),
        str(edge.get("relationship", "")).strip().upper(),
        str(edge.get("target_id", "")),
    )


def _expected_promoted_edge_signature(edge: Dict[str, Any]) -> tuple[str, str, str]:
    return (
        canonical_entity_id(str(edge.get("source", ""))),
        str(edge.get("relationship", "")).strip().upper(),
        canonical_entity_id(str(edge.get("target", ""))),
    )


def collect_claim_promotion_metrics(vault: Any, document_id: str) -> Dict[str, Any]:
    """Collect deterministic metrics for graph edges promoted from validated claims."""
    edges = _claim_promoted_edges(vault, document_id)
    node_ids = {
        node_id
        for edge in edges
        for node_id in [edge.get("source_id"), edge.get("target_id")]
        if node_id
    }
    return {
        "promoted_node_count": len(node_ids),
        "promoted_edge_count": len(edges),
        "promoted_self_edge_count": sum(1 for edge in edges if edge.get("source_id") == edge.get("target_id")),
        "promoted_edges_with_claim_id": sum(1 for edge in edges if edge.get("claim_id")),
        "promoted_edges_with_evidence": sum(1 for edge in edges if edge.get("evidence_span_ids")),
    }


def evaluate_claim_promotion(
    vault: Any,
    document_id: str,
    expectations: Dict[str, Any],
) -> Dict[str, Any]:
    """Evaluate claim-promoted graph edges against expected canonical edges."""
    actual_signatures = {_promoted_edge_signature(edge) for edge in _claim_promoted_edges(vault, document_id)}
    expected_edges = expectations.get("expected_edges", [])
    matched_edge_count = 0
    missing_edges = []

    for expected_edge in expected_edges:
        if _expected_promoted_edge_signature(expected_edge) in actual_signatures:
            matched_edge_count += 1
        else:
            missing_edges.append(expected_edge)

    metrics = collect_claim_promotion_metrics(vault, document_id)
    metrics["expected_promoted_edge_count"] = len(expected_edges)
    metrics["matched_promoted_edge_count"] = matched_edge_count
    metrics["promoted_edge_match_rate"] = round(matched_edge_count / len(expected_edges), 4) if expected_edges else 1.0
    failures = compare_metrics(metrics, expectations.get("metrics", {}))
    for missing_edge in missing_edges:
        failures.append(
            "missing promoted edge: "
            f"{missing_edge.get('source')} "
            f"{missing_edge.get('relationship')} "
            f"{missing_edge.get('target')}"
        )

    return {
        "document_id": document_id,
        "passed": not failures,
        "metrics": metrics,
        "failures": failures,
        "missing_edges": missing_edges,
    }


def evaluate_claim_promotion_baseline(vault: Any, baseline_path: str | Path) -> Dict[str, Any]:
    """Evaluate claim-promoted graph edges using a JSON fixture baseline."""
    baseline = load_evaluation_baseline(baseline_path)
    result = evaluate_claim_promotion(vault, baseline["document_id"], baseline["promotion_expectations"])
    result["baseline_path"] = str(Path(baseline_path))
    result["document_path"] = str(baseline.get("document_path", ""))
    return result


def _graph_edges(vault: Any, document_id: str) -> List[Dict[str, Any]]:
    cursor = vault.conn.cursor()
    cursor.execute(
        """
        SELECT source_id, target_id, relationship, source_chunk_id, claim_id, evidence_span_ids
        FROM edges
        WHERE document_id = ?
        ORDER BY source_id, relationship, target_id, source_chunk_id
        """,
        (document_id,),
    )
    edges = []
    for row in cursor.fetchall():
        item = dict(row)
        if item.get("evidence_span_ids"):
            try:
                item["evidence_span_ids"] = json.loads(item["evidence_span_ids"])
            except json.JSONDecodeError:
                item["evidence_span_ids"] = []
        else:
            item["evidence_span_ids"] = []
        edges.append(item)
    return edges


def _canonical_graph_node_id(node_id: str) -> str:
    raw = str(node_id or "").strip()
    if raw.startswith("entity_"):
        return raw
    return canonical_entity_id(raw.replace("_", " "))


def _canonical_graph_edge_signature(edge: Dict[str, Any]) -> tuple[str, str, str]:
    return (
        _canonical_graph_node_id(str(edge.get("source_id", ""))),
        str(edge.get("relationship", "")).strip().upper(),
        _canonical_graph_node_id(str(edge.get("target_id", ""))),
    )


def _graph_review_candidate_id(kind: str, signature: tuple[str, str, str]) -> str:
    source_id, relationship, target_id = signature
    return f"{kind}:{source_id}:{relationship}:{target_id}"


def _graph_review_state(
    decisions: Dict[str, Dict[str, Any]],
    kind: str,
    signature: tuple[str, str, str],
) -> str | None:
    decision = decisions.get(_graph_review_candidate_id(kind, signature), {})
    state = str(decision.get("state") or "").strip()
    return state or None


def _accuracy_review_decisions(vault: Any, document_id: str) -> Dict[str, Dict[str, Any]]:
    list_decisions = getattr(vault, "list_accuracy_review_decisions", None)
    if not callable(list_decisions):
        return {}
    decisions = list_decisions(document_id)
    return decisions if isinstance(decisions, dict) else {}


def _graph_edge_sample(edge: Dict[str, Any], review_state: str | None = None) -> Dict[str, Any]:
    sample = {
        "source_id": edge.get("source_id"),
        "target_id": edge.get("target_id"),
        "relationship": str(edge.get("relationship", "")).strip().upper(),
        "canonical_source_id": _canonical_graph_node_id(str(edge.get("source_id", ""))),
        "canonical_target_id": _canonical_graph_node_id(str(edge.get("target_id", ""))),
        "source_chunk_id": edge.get("source_chunk_id"),
        "claim_id": edge.get("claim_id"),
        "evidence_span_ids": edge.get("evidence_span_ids", []),
    }
    if review_state:
        sample["review_state"] = review_state
    return sample


def collect_parallel_graph_metrics(vault: Any, document_id: str) -> Dict[str, Any]:
    """Compare legacy graph edges with claim-promoted graph edges by canonical endpoint IDs."""
    edges = _graph_edges(vault, document_id)
    legacy_edges = [edge for edge in edges if edge.get("source_chunk_id") != "claim_layer"]
    claim_edges = [edge for edge in edges if edge.get("source_chunk_id") == "claim_layer"]
    legacy_signatures = {_canonical_graph_edge_signature(edge) for edge in legacy_edges}
    claim_signatures = {_canonical_graph_edge_signature(edge) for edge in claim_edges}
    shared_signatures = legacy_signatures & claim_signatures

    return {
        "legacy_edge_count": len(legacy_edges),
        "claim_promoted_edge_count": len(claim_edges),
        "shared_canonical_edge_count": len(shared_signatures),
        "legacy_only_edge_count": len(legacy_signatures - claim_signatures),
        "claim_only_edge_count": len(claim_signatures - legacy_signatures),
        "claim_vs_legacy_overlap_rate": round(len(shared_signatures) / len(claim_signatures), 4)
        if claim_signatures
        else 1.0,
    }


def collect_parallel_graph_agreement(vault: Any, document_id: str) -> Dict[str, Any]:
    """Return graph agreement metrics plus representative mismatch samples for review."""
    edges = _graph_edges(vault, document_id)
    legacy_edges = [edge for edge in edges if edge.get("source_chunk_id") != "claim_layer"]
    claim_edges = [edge for edge in edges if edge.get("source_chunk_id") == "claim_layer"]
    legacy_by_signature = {
        _canonical_graph_edge_signature(edge): edge
        for edge in legacy_edges
    }
    claim_by_signature = {
        _canonical_graph_edge_signature(edge): edge
        for edge in claim_edges
    }
    legacy_signatures = set(legacy_by_signature)
    claim_signatures = set(claim_by_signature)
    shared_signatures = legacy_signatures & claim_signatures
    legacy_only_signatures = sorted(legacy_signatures - claim_signatures)
    claim_only_signatures = sorted(claim_signatures - legacy_signatures)
    decisions = _accuracy_review_decisions(vault, document_id)
    legacy_review_states = {
        signature: _graph_review_state(decisions, "legacy-only", signature)
        for signature in legacy_only_signatures
    }
    claim_review_states = {
        signature: _graph_review_state(decisions, "claim-only", signature)
        for signature in claim_only_signatures
    }
    accepted_claim_only_count = sum(
        1 for state in claim_review_states.values() if state == "accepted"
    )
    ignored_claim_only_count = sum(
        1 for state in claim_review_states.values() if state == "ignored"
    )
    accepted_legacy_only_count = sum(
        1 for state in legacy_review_states.values() if state == "accepted"
    )
    ignored_legacy_only_count = sum(
        1 for state in legacy_review_states.values() if state == "ignored"
    )
    active_claim_only_count = sum(
        1 for state in claim_review_states.values() if state not in {"accepted", "ignored"}
    )
    active_legacy_only_count = sum(
        1 for state in legacy_review_states.values() if state not in {"accepted", "ignored"}
    )

    return {
        "legacy_edge_count": len(legacy_edges),
        "claim_promoted_edge_count": len(claim_edges),
        "shared_canonical_edge_count": len(shared_signatures),
        "legacy_only_edge_count": len(legacy_only_signatures),
        "claim_only_edge_count": len(claim_only_signatures),
        "accepted_claim_only_edge_count": accepted_claim_only_count,
        "ignored_claim_only_edge_count": ignored_claim_only_count,
        "accepted_legacy_only_edge_count": accepted_legacy_only_count,
        "ignored_legacy_only_edge_count": ignored_legacy_only_count,
        "active_claim_only_edge_count": active_claim_only_count,
        "active_legacy_only_edge_count": active_legacy_only_count,
        "human_promoted_edge_count": accepted_claim_only_count,
        "claim_vs_legacy_overlap_rate": round(len(shared_signatures) / len(claim_signatures), 4)
        if claim_signatures
        else 1.0,
        "legacy_only_edges": [
            _graph_edge_sample(
                legacy_by_signature[signature],
                legacy_review_states.get(signature),
            )
            for signature in legacy_only_signatures[:10]
        ],
        "claim_only_edges": [
            _graph_edge_sample(
                claim_by_signature[signature],
                claim_review_states.get(signature),
            )
            for signature in claim_only_signatures[:10]
        ],
    }


def evaluate_parallel_graph_comparison(
    vault: Any,
    document_id: str,
    expectations: Dict[str, Any],
) -> Dict[str, Any]:
    """Evaluate legacy-vs-claim graph overlap without changing ingestion defaults."""
    metrics = collect_parallel_graph_metrics(vault, document_id)
    failures = compare_metrics(metrics, expectations.get("metrics", {}))

    return {
        "document_id": document_id,
        "passed": not failures,
        "metrics": metrics,
        "failures": failures,
    }


def evaluate_parallel_graph_baseline(vault: Any, baseline_path: str | Path) -> Dict[str, Any]:
    """Evaluate parallel legacy-vs-claim graph metrics using a JSON fixture baseline."""
    baseline = load_evaluation_baseline(baseline_path)
    result = evaluate_parallel_graph_comparison(
        vault,
        baseline["document_id"],
        baseline["parallel_expectations"],
    )
    result["baseline_path"] = str(Path(baseline_path))
    result["document_path"] = str(baseline.get("document_path", ""))
    return result


CLAIM_ACCURACY_GATE_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "schema_valid_rate": {"min": 0.95},
    "evidence_linkage_rate": {"min": 0.90},
    "dependency_recall": {"min": 0.85},
    "false_positive_contradiction_rate": {"max": 0.10},
    "graph_promoted_without_evidence": {"max": 0},
    "accepted_without_validation": {"max": 0},
    "promoted_edges_without_claim_id": {"max": 0},
}


def evaluate_claim_accuracy_gate(
    metrics: Dict[str, Any],
    thresholds: Dict[str, Dict[str, float]] | None = None,
) -> Dict[str, Any]:
    """Evaluate whether claim promotion is ready to replace direct graph extraction."""
    gate_thresholds = thresholds or CLAIM_ACCURACY_GATE_THRESHOLDS
    failures = compare_metrics(metrics, gate_thresholds)
    return {
        "passed": not failures,
        "metrics": metrics,
        "thresholds": gate_thresholds,
        "failures": failures,
    }


def evaluate_claim_accuracy_gate_baseline(baseline_path: str | Path) -> Dict[str, Any]:
    """Evaluate claim-layer replacement readiness using a JSON fixture baseline."""
    baseline = load_evaluation_baseline(baseline_path)
    gate = baseline.get("accuracy_gate")
    metrics = gate.get("metrics") if isinstance(gate, dict) else None
    thresholds = gate.get("thresholds") if isinstance(gate, dict) else None

    if not isinstance(metrics, dict):
        result = {
            "document_id": baseline.get("document_id", ""),
            "passed": False,
            "metrics": {},
            "thresholds": thresholds or CLAIM_ACCURACY_GATE_THRESHOLDS,
            "failures": ["accuracy_gate.metrics is missing"],
        }
    else:
        result = evaluate_claim_accuracy_gate(
            metrics,
            thresholds if isinstance(thresholds, dict) else None,
        )
        result["document_id"] = baseline.get("document_id", "")

    result["baseline_path"] = str(Path(baseline_path))
    result["document_path"] = str(baseline.get("document_path", ""))
    return result


def live_evaluation_enabled() -> bool:
    """Return True only when live model-backed evaluation is explicitly enabled."""
    return os.environ.get("DIAMOND_MINER_LIVE_EVALUATION", "").strip().lower() in {"1", "true", "yes", "on"}


def evaluate_live_ingestion_fixture(
    baseline_path: str | Path,
    base_dir: str | Path,
    tenant_id: str | None = None,
    max_workers: int = 3,
) -> Dict[str, Any]:
    """
    Run a baseline through the real ingestion and analysis agents.

    This is intentionally separate from deterministic fixture tests because it can
    call live LLM providers and will vary with model/provider behaviour.
    """
    baseline = load_evaluation_baseline(baseline_path)
    live_tenant = tenant_id or f"live_eval_{uuid.uuid4().hex[:8]}"
    vault = HybridVault(tenant_id=live_tenant, base_dir=str(base_dir))
    orchestrator = DiamondOrchestrator(
        tenant_id=live_tenant,
        document_id=baseline["document_id"],
        document_name=baseline["document_path"].name,
        vault=vault,
    )

    orchestrator.run_ingestion_pipeline(str(baseline["document_path"]), max_workers=max_workers)
    orchestrator.interrogate_friction()
    orchestrator.interrogate_fragility()
    orchestrator.interrogate_time_friction()
    return evaluate_baseline(vault, baseline_path)
