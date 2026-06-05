from pathlib import Path

import pytest

from core.evaluation import evaluate_claim_accuracy_gate, evaluate_claim_accuracy_gate_baseline


pytestmark = pytest.mark.evaluation

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "evaluation"


def _passing_metrics():
    return {
        "schema_valid_rate": 0.98,
        "evidence_linkage_rate": 0.94,
        "dependency_recall": 0.88,
        "false_positive_contradiction_rate": 0.05,
        "graph_promoted_without_evidence": 0,
        "accepted_without_validation": 0,
        "promoted_edges_without_claim_id": 0,
    }


def test_claim_accuracy_gate_passes_when_all_thresholds_are_met():
    result = evaluate_claim_accuracy_gate(_passing_metrics())

    assert result == {
        "passed": True,
        "metrics": _passing_metrics(),
        "thresholds": {
            "schema_valid_rate": {"min": 0.95},
            "evidence_linkage_rate": {"min": 0.90},
            "dependency_recall": {"min": 0.85},
            "false_positive_contradiction_rate": {"max": 0.10},
            "graph_promoted_without_evidence": {"max": 0},
            "accepted_without_validation": {"max": 0},
            "promoted_edges_without_claim_id": {"max": 0},
        },
        "failures": [],
    }


def test_claim_accuracy_gate_reports_threshold_failures_and_missing_metrics():
    metrics = {
        "schema_valid_rate": 0.91,
        "evidence_linkage_rate": 0.89,
        "dependency_recall": 0.84,
        "false_positive_contradiction_rate": 0.12,
        "graph_promoted_without_evidence": 1,
        "accepted_without_validation": 0,
    }

    result = evaluate_claim_accuracy_gate(metrics)

    assert result["passed"] is False
    assert result["failures"] == [
        "schema_valid_rate expected >= 0.95, got 0.91",
        "evidence_linkage_rate expected >= 0.9, got 0.89",
        "dependency_recall expected >= 0.85, got 0.84",
        "false_positive_contradiction_rate expected <= 0.1, got 0.12",
        "graph_promoted_without_evidence expected <= 0, got 1",
        "promoted_edges_without_claim_id is missing",
    ]


def test_claim_accuracy_gate_baseline_uses_fixture_metrics():
    baseline_path = FIXTURE_DIR / "claim_layer_programme_baseline.json"

    result = evaluate_claim_accuracy_gate_baseline(baseline_path)

    assert result["document_id"] == "claim_layer_programme"
    assert result["passed"] is True
    assert result["baseline_path"] == str(baseline_path)
    assert result["document_path"] == str((FIXTURE_DIR / "claim_layer_programme.md").resolve())
    assert result["metrics"]["dependency_recall"] == 1.0
    assert result["failures"] == []


def test_claim_accuracy_gate_baseline_reports_missing_gate_metrics(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        '{"document_id": "missing_gate", "document_path": "missing_gate.md"}',
        encoding="utf-8",
    )

    result = evaluate_claim_accuracy_gate_baseline(baseline_path)

    assert result["document_id"] == "missing_gate"
    assert result["passed"] is False
    assert result["metrics"] == {}
    assert result["failures"] == ["accuracy_gate.metrics is missing"]
