from unittest.mock import Mock

import pytest

from core.accuracy.claim_extractor import ClaimExtractionResult
from core.accuracy.pipeline_mode import PipelineMode, resolve_pipeline_mode
from core.accuracy.schemas import ExtractedClaim
from core.orchestrator import DiamondOrchestrator
from core.vault import HybridVault


def test_explicit_mode_wins_over_legacy_flags():
    env = {
        "DIAMOND_MINER_PIPELINE_MODE": "shadow",
        "DIAMOND_MINER_CLAIM_LAYER": "0",
        "DIAMOND_MINER_USE_CLAIM_PROMOTION": "1",
    }

    assert resolve_pipeline_mode(env) is PipelineMode.SHADOW


def test_legacy_flags_map_to_claims():
    env = {
        "DIAMOND_MINER_CLAIM_LAYER": "1",
        "DIAMOND_MINER_USE_CLAIM_PROMOTION": "1",
    }

    assert resolve_pipeline_mode(env) is PipelineMode.CLAIMS


def test_no_flags_preserves_legacy_default():
    assert resolve_pipeline_mode({}) is PipelineMode.LEGACY


def test_invalid_explicit_mode_raises():
    with pytest.raises(ValueError, match="invalid"):
        resolve_pipeline_mode({"DIAMOND_MINER_PIPELINE_MODE": "invalid"})


def _claim_extraction(spans):
    return ClaimExtractionResult(
        claims=[
            ExtractedClaim(
                claim_id="claim_1",
                document_id="doc_1",
                claim_type="dependency",
                subject="Cloud migration",
                predicate="requires",
                object="Security certification",
                modality="must",
                certainty="explicit",
                evidence_span_ids=[spans[0].span_id],
                source_quote=spans[0].text,
                confidence=0.9,
            )
        ],
        failures=[],
    )


def _run_ingestion(monkeypatch, tmp_path, mode):
    source = tmp_path / f"{mode}.md"
    source.write_text(
        "Cloud migration requires Security certification.",
        encoding="utf-8",
    )
    vault = HybridVault(tenant_id=mode, base_dir=str(tmp_path / "vaults"))
    legacy_extract = Mock(
        return_value={
            "nodes": [
                {"id": "legacy_source", "label": "Concept", "name": "Legacy source"},
                {"id": "legacy_target", "label": "Concept", "name": "Legacy target"},
            ],
            "edges": [
                {
                    "source_id": "legacy_source",
                    "target_id": "legacy_target",
                    "relationship": "REQUIRES",
                }
            ],
        }
    )
    monkeypatch.setenv("DIAMOND_MINER_PIPELINE_MODE", mode)
    monkeypatch.setattr(
        "core.accuracy.claim_extractor.extract_claims_with_failures",
        _claim_extraction,
    )
    monkeypatch.setattr("core.agents.DeconstructorAgent.extract_topology", legacy_extract)
    monkeypatch.setattr("core.agents.ChronosAgent.extract_time_data", lambda *args, **kwargs: {})

    orchestrator = DiamondOrchestrator(
        tenant_id=mode,
        document_id="doc_1",
        document_name=source.name,
        vault=vault,
    )
    orchestrator.run_ingestion_pipeline(str(source), max_workers=1)
    edges = [
        dict(row)
        for row in vault.conn.execute(
            "SELECT source_id, target_id, claim_id FROM edges WHERE document_id = ?",
            ("doc_1",),
        ).fetchall()
    ]
    return vault, legacy_extract, edges


def test_claims_mode_never_calls_legacy_deconstructor(monkeypatch, tmp_path):
    vault, legacy_extract, edges = _run_ingestion(monkeypatch, tmp_path, "claims")

    legacy_extract.assert_not_called()
    assert [edge["claim_id"] for edge in edges] == ["claim_1"]
    vault.conn.close()


def test_shadow_mode_runs_both_paths_with_legacy_topology_authoritative(monkeypatch, tmp_path):
    vault, legacy_extract, edges = _run_ingestion(monkeypatch, tmp_path, "shadow")

    legacy_extract.assert_called_once()
    assert {edge["claim_id"] for edge in edges} == {None, "claim_1"}
    assert any(edge["source_id"] == "legacy_source" for edge in edges)
    vault.conn.close()
