from pathlib import Path

import pytest

from core.evaluation import evaluate_baseline, load_evaluation_baseline
from core.vault import HybridVault


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "evaluation"
pytestmark = pytest.mark.evaluation


def _seed_fixture_vault(vault: HybridVault, document_id: str) -> None:
    vault.insert_document(document_id, "simple_programme.md")
    vault.insert_graph_topology(
        nodes=[
            {"id": "alpha", "label": "TASK", "name": "Alpha"},
            {"id": "beta", "label": "TASK", "name": "Beta"},
            {"id": "gamma", "label": "TASK", "name": "Gamma"},
        ],
        edges=[
            {"source_id": "alpha", "target_id": "beta", "relationship": "REQUIRES"},
            {"source_id": "gamma", "target_id": "beta", "relationship": "STARTS_AFTER"},
        ],
        source_chunk_id="chunk_fixture",
        document_id=document_id,
    )
    vault.upsert_friction_lines(
        document_id,
        [
            {
                "source": "alpha",
                "target": "beta",
                "diamond": "Alpha depends on Beta but launch sequencing is unclear.",
                "provenance_ids": ["chunk_fixture"],
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
                "provenance_ids": ["chunk_fixture"],
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


@pytest.mark.parametrize(
    ("baseline_name", "document_name"),
    [
        ("simple_programme_baseline.json", "simple_programme.md"),
        ("no_conflict_programme_baseline.json", "no_conflict_programme.md"),
        ("complex_programme_baseline.json", "complex_programme.md"),
    ],
)
def test_load_evaluation_baseline_resolves_document_path(baseline_name, document_name):
    baseline = load_evaluation_baseline(FIXTURE_DIR / baseline_name)

    assert baseline["document_path"] == FIXTURE_DIR / document_name
    assert baseline["document_path"].exists()


def test_evaluate_baseline_passes_for_seeded_fixture_vault(tmp_path):
    baseline_path = FIXTURE_DIR / "simple_programme_baseline.json"
    baseline = load_evaluation_baseline(baseline_path)
    vault = HybridVault(tenant_id="eval", base_dir=str(tmp_path))
    _seed_fixture_vault(vault, baseline["document_id"])

    result = evaluate_baseline(vault, baseline_path)

    assert result["passed"] is True
    assert result["failures"] == []
    assert result["metrics"]["node_count"] == 3
