import json
from pathlib import Path
from typing import Any, Dict, List


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
