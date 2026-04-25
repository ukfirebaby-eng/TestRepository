from pathlib import Path
from unittest.mock import patch

import pytest

from core.evaluation import evaluate_baseline, load_evaluation_baseline
from core.orchestrator import DiamondOrchestrator
from core.vault import HybridVault


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "evaluation"
pytestmark = pytest.mark.evaluation


def _seed_post_ingestion_outputs(vault: HybridVault, document_id: str) -> None:
    vault.upsert_friction_lines(
        document_id,
        [
            {
                "source": "alpha",
                "target": "beta",
                "diamond": "Alpha depends on Beta but launch sequencing is unclear.",
                "provenance_ids": ["fixture_chunk"],
                "severity": 4,
                "probability": 3,
            }
        ],
    )
    vault.upsert_chronological_friction_lines(
        document_id,
        [
            {
                "source": "gamma",
                "target": "beta",
                "diamond": "Gamma starts after Beta but overlaps the delivery window.",
                "provenance_ids": ["fixture_chunk"],
                "severity": 3,
                "probability": 4,
            }
        ],
    )
    vault.save_narrative_report(
        document_id,
        {
            "coverage_verified": True,
            "chapters": [{"title": "Delivery Risk", "narrative": "Risk narrative."}],
        },
        model="fixture",
    )
    vault.save_executive_summary(
        document_id,
        {"summary_narrative": "Executive summary.", "generated_at": "2026-01-01T00:00:00Z"},
        model="fixture",
    )


def _seed_clean_post_ingestion_outputs(vault: HybridVault, document_id: str) -> None:
    vault.upsert_friction_lines(document_id, [])
    vault.upsert_chronological_friction_lines(document_id, [])
    vault.save_narrative_report(
        document_id,
        {
            "coverage_verified": True,
            "chapters": [{"title": "No Material Conflicts", "narrative": "No conflicts found."}],
        },
        model="fixture",
    )
    vault.save_executive_summary(
        document_id,
        {"summary_narrative": "No material conflicts found.", "generated_at": "2026-01-01T00:00:00Z"},
        model="fixture",
    )


def _seed_complex_post_ingestion_outputs(vault: HybridVault, document_id: str) -> None:
    vault.upsert_friction_lines(
        document_id,
        [
            {
                "source": "customer_portal",
                "target": "legacy_adapter",
                "diamond": (
                    "Customer Portal claims direct legacy cutover readiness while the adapter "
                    "is explicitly marked manual-only until remediation."
                ),
                "provenance_ids": ["fixture_complex_chunk"],
                "severity": 5,
                "probability": 4,
            }
        ],
    )
    vault.upsert_chronological_friction_lines(
        document_id,
        [
            {
                "source": "identity_platform",
                "target": "cutover_rehearsal",
                "diamond": "Cutover rehearsal starts before Identity Platform completion.",
                "provenance_ids": ["fixture_complex_chunk"],
                "severity": 4,
                "probability": 4,
            }
        ],
    )
    vault.save_narrative_report(
        document_id,
        {
            "coverage_verified": True,
            "chapters": [
                {
                    "title": "Contradiction, Schedule, and Hub Risk",
                    "narrative": "The fixture includes structural, temporal, and hub dependency risk.",
                }
            ],
        },
        model="fixture",
    )
    vault.save_executive_summary(
        document_id,
        {
            "summary_narrative": "Complex programme fixture exposes contradiction, schedule, and hub risk.",
            "generated_at": "2026-01-01T00:00:00Z",
        },
        model="fixture",
    )


def test_ingestion_fixture_evaluates_against_baseline(tmp_path):
    baseline_path = FIXTURE_DIR / "simple_programme_baseline.json"
    baseline = load_evaluation_baseline(baseline_path)
    document_id = baseline["document_id"]
    vault = HybridVault(tenant_id="eval_ingestion", base_dir=str(tmp_path))
    orchestrator = DiamondOrchestrator(
        tenant_id="eval_ingestion",
        document_id=document_id,
        document_name=baseline["document_path"].name,
        vault=vault,
    )
    topology = {
        "nodes": [
            {"id": "alpha", "label": "TASK", "name": "Alpha"},
            {"id": "beta", "label": "TASK", "name": "Beta"},
            {"id": "gamma", "label": "TASK", "name": "Gamma"},
        ],
        "edges": [
            {"source_id": "alpha", "target_id": "beta", "relationship": "REQUIRES"},
        ],
    }
    temporal = {
        "temporal_nodes": [
            {
                "node_id": "beta",
                "start_date": "2026-02-01",
                "end_date": "2026-02-10",
                "duration_days": 9,
                "is_milestone": False,
            },
            {
                "node_id": "gamma",
                "start_date": "2026-02-05",
                "end_date": "2026-02-15",
                "duration_days": 10,
                "is_milestone": False,
            },
        ],
        "temporal_edges": [
            {"source_id": "gamma", "target_id": "beta", "relationship": "STARTS_AFTER"},
        ],
    }

    with patch("core.orchestrator.DeconstructorAgent.extract_topology", return_value=topology), \
         patch("core.orchestrator.ChronosAgent.extract_time_data", return_value=temporal):
        orchestrator.run_ingestion_pipeline(str(baseline["document_path"]), max_workers=1)

    _seed_post_ingestion_outputs(vault, document_id)
    result = evaluate_baseline(vault, baseline_path)

    assert result["passed"] is True
    assert result["failures"] == []
    assert result["metrics"]["node_count"] == 3
    assert result["metrics"]["edge_count"] == 2


def test_no_conflict_ingestion_fixture_evaluates_against_baseline(tmp_path):
    baseline_path = FIXTURE_DIR / "no_conflict_programme_baseline.json"
    baseline = load_evaluation_baseline(baseline_path)
    document_id = baseline["document_id"]
    vault = HybridVault(tenant_id="eval_no_conflict", base_dir=str(tmp_path))
    orchestrator = DiamondOrchestrator(
        tenant_id="eval_no_conflict",
        document_id=document_id,
        document_name=baseline["document_path"].name,
        vault=vault,
    )
    topology = {
        "nodes": [
            {"id": "discovery", "label": "TASK", "name": "Discovery"},
            {"id": "delivery", "label": "TASK", "name": "Delivery"},
        ],
        "edges": [
            {"source_id": "discovery", "target_id": "delivery", "relationship": "PRODUCES"},
        ],
    }
    temporal = {"temporal_nodes": [], "temporal_edges": []}

    with patch("core.orchestrator.DeconstructorAgent.extract_topology", return_value=topology), \
         patch("core.orchestrator.ChronosAgent.extract_time_data", return_value=temporal):
        orchestrator.run_ingestion_pipeline(str(baseline["document_path"]), max_workers=1)

    _seed_clean_post_ingestion_outputs(vault, document_id)
    result = evaluate_baseline(vault, baseline_path)

    assert result["passed"] is True
    assert result["failures"] == []
    assert result["metrics"]["friction_count"] == 0
    assert result["metrics"]["chronological_friction_count"] == 0
    assert result["metrics"]["risk_matrix_count"] == 0


def test_complex_ingestion_fixture_evaluates_structural_temporal_and_hub_risk(tmp_path):
    baseline_path = FIXTURE_DIR / "complex_programme_baseline.json"
    baseline = load_evaluation_baseline(baseline_path)
    document_id = baseline["document_id"]
    vault = HybridVault(tenant_id="eval_complex", base_dir=str(tmp_path))
    orchestrator = DiamondOrchestrator(
        tenant_id="eval_complex",
        document_id=document_id,
        document_name=baseline["document_path"].name,
        vault=vault,
    )
    topology = {
        "nodes": [
            {"id": "identity_platform", "label": "SYSTEM", "name": "Identity Platform"},
            {"id": "customer_portal", "label": "SYSTEM", "name": "Customer Portal"},
            {"id": "billing_gateway", "label": "SYSTEM", "name": "Billing Gateway"},
            {"id": "reporting_warehouse", "label": "SYSTEM", "name": "Reporting Warehouse"},
            {"id": "legacy_adapter", "label": "SYSTEM", "name": "Legacy Adapter"},
            {"id": "cutover_rehearsal", "label": "MILESTONE", "name": "Cutover Rehearsal"},
        ],
        "edges": [
            {"source_id": "customer_portal", "target_id": "identity_platform", "relationship": "REQUIRES"},
            {"source_id": "billing_gateway", "target_id": "identity_platform", "relationship": "REQUIRES"},
            {"source_id": "reporting_warehouse", "target_id": "identity_platform", "relationship": "REQUIRES"},
            {"source_id": "legacy_adapter", "target_id": "identity_platform", "relationship": "REQUIRES"},
        ],
    }
    temporal = {
        "temporal_nodes": [
            {
                "node_id": "identity_platform",
                "start_date": "2026-05-01",
                "end_date": "2026-05-24",
                "duration_days": 23,
                "is_milestone": False,
            },
            {
                "node_id": "cutover_rehearsal",
                "start_date": "2026-05-20",
                "end_date": "2026-05-21",
                "duration_days": 1,
                "is_milestone": True,
            },
        ],
        "temporal_edges": [
            {
                "source_id": "identity_platform",
                "target_id": "cutover_rehearsal",
                "relationship": "STARTS_AFTER",
            }
        ],
    }

    with patch("core.orchestrator.DeconstructorAgent.extract_topology", return_value=topology), \
         patch("core.orchestrator.ChronosAgent.extract_time_data", return_value=temporal):
        orchestrator.run_ingestion_pipeline(str(baseline["document_path"]), max_workers=1)

    _seed_complex_post_ingestion_outputs(vault, document_id)
    result = evaluate_baseline(vault, baseline_path)

    assert result["passed"] is True
    assert result["failures"] == []
    assert result["metrics"]["friction_count"] == 1
    assert result["metrics"]["chronological_friction_count"] == 1
    assert result["metrics"]["hub_vulnerability_count"] == 2
    assert result["metrics"]["risk_matrix_count"] == 2
