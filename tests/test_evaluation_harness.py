from unittest.mock import MagicMock

import pytest

from core.evaluation import collect_document_metrics, compare_metrics, evaluate_document


pytestmark = pytest.mark.evaluation


def _vault():
    vault = MagicMock()
    vault.get_canvas_data.return_value = {
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [{"source": "a", "target": "b"}],
    }
    vault.get_friction_lines.return_value = [{"severity": 4}, {"severity": 2}]
    vault.get_chronological_friction_lines.return_value = [{"severity": 3}]
    vault.get_hub_vulnerabilities.return_value = [{"id": "a"}]
    vault.get_risk_matrix_data.return_value = [{"severity": 4, "probability": 4}]
    vault.get_narrative_report.return_value = {"coverage_verified": True, "chapters": [{}, {}]}
    vault.get_executive_summary.return_value = {"summary_narrative": "Summary"}
    return vault


def test_collect_document_metrics_counts_core_outputs():
    metrics = collect_document_metrics(_vault(), "doc_1")

    assert metrics == {
        "node_count": 2,
        "edge_count": 1,
        "friction_count": 2,
        "chronological_friction_count": 1,
        "hub_vulnerability_count": 1,
        "risk_matrix_count": 1,
        "narrative_chapter_count": 2,
        "narrative_coverage_verified": True,
        "has_executive_summary": True,
    }


def test_compare_metrics_accepts_exact_min_and_max_expectations():
    failures = compare_metrics(
        {"node_count": 5, "edge_count": 4, "friction_count": 2},
        {
            "node_count": {"min": 4},
            "edge_count": {"max": 4},
            "friction_count": {"exact": 2},
        },
    )

    assert failures == []


def test_compare_metrics_reports_failed_expectations():
    failures = compare_metrics(
        {"node_count": 2, "edge_count": 5, "friction_count": 1},
        {
            "node_count": {"min": 3},
            "edge_count": {"max": 4},
            "friction_count": {"exact": 2},
            "missing_metric": {"exact": 1},
        },
    )

    assert failures == [
        "node_count expected >= 3, got 2",
        "edge_count expected <= 4, got 5",
        "friction_count expected == 2, got 1",
        "missing_metric is missing",
    ]


def test_evaluate_document_returns_passed_false_with_failures():
    result = evaluate_document(_vault(), "doc_1", {"node_count": {"exact": 3}})

    assert result["passed"] is False
    assert result["failures"] == ["node_count expected == 3, got 2"]
    assert result["metrics"]["node_count"] == 2
