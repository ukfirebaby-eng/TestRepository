from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.accuracy.entity_canonicalizer import build_canonical_entities_from_claims
from core.accuracy.claim_extractor import ClaimExtractionResult
from core.accuracy.schemas import DocumentManifest, EvidenceSpan, ExtractedClaim, ValidationResult
from core.evaluation import (
    collect_claim_layer_metrics,
    collect_claim_promotion_metrics,
    collect_parallel_graph_agreement,
    collect_parallel_graph_metrics,
    evaluate_claim_layer,
    evaluate_claim_layer_baseline,
    evaluate_claim_promotion,
    evaluate_claim_promotion_baseline,
    evaluate_parallel_graph_baseline,
    evaluate_parallel_graph_comparison,
    load_evaluation_baseline,
)
from core.orchestrator import DiamondOrchestrator
from core.vault import HybridVault


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "evaluation"
pytestmark = pytest.mark.evaluation


def _claim(
    *,
    claim_id: str,
    claim_type: str,
    subject: str,
    object_: str,
    span_id: str,
    validation_status: str,
    confidence: float = 0.9,
) -> ExtractedClaim:
    return ExtractedClaim(
        claim_id=claim_id,
        document_id="claim_layer_programme",
        claim_type=claim_type,
        subject=subject,
        predicate="requires" if claim_type == "dependency" else "blocks",
        object=object_,
        modality="must",
        certainty="explicit" if validation_status == "passed" else "implied",
        evidence_span_ids=[span_id],
        source_quote=f"{subject} {claim_type} {object_}.",
        confidence=confidence,
        validation_status=validation_status,
    )


def _seed_claim_layer_fixture(vault: HybridVault) -> None:
    document_id = "claim_layer_programme"
    vault.insert_document(document_id, "claim_layer_programme.md")
    vault.save_document_manifest(DocumentManifest(
        document_id=document_id,
        filename="claim_layer_programme.md",
        source_hash="sha256:fixture",
        ingested_at=datetime.now(timezone.utc),
        llm_model="fixture",
        validation_status="partial",
    ))
    vault.insert_evidence_spans([
        EvidenceSpan(
            span_id="span_1",
            document_id=document_id,
            chunk_id="chunk_1",
            page_number=1,
            text="The Cloud-Migration Programme requires security certification.",
            span_type="sentence",
            source_hash="sha256:fixture",
        ),
        EvidenceSpan(
            span_id="span_2",
            document_id=document_id,
            chunk_id="chunk_2",
            page_number=1,
            text="API Gateway blocks deployment.",
            span_type="sentence",
            source_hash="sha256:fixture",
        ),
    ])
    claims = [
        _claim(
            claim_id="claim_1",
            claim_type="dependency",
            subject="The Cloud-Migration Programme",
            object_="Security Certification",
            span_id="span_1",
            validation_status="passed",
        ),
        _claim(
            claim_id="claim_2",
            claim_type="blocker",
            subject="API Gateway",
            object_="deployment",
            span_id="span_2",
            validation_status="needs_review",
            confidence=0.7,
        ),
    ]
    vault.insert_extracted_claims(claims)
    vault.insert_validation_results([
        ValidationResult(
            claim_id="claim_1",
            document_id=document_id,
            status="passed",
            reasons=[],
            can_promote=True,
        ),
        ValidationResult(
            claim_id="claim_2",
            document_id=document_id,
            status="needs_review",
            reasons=["claim certainty is not explicit"],
            can_promote=False,
        ),
    ])
    vault.insert_canonical_entities(document_id, build_canonical_entities_from_claims(claims))


def test_collect_claim_layer_metrics_counts_accuracy_artifacts(tmp_path):
    vault = HybridVault(tenant_id="claim_eval_counts", base_dir=str(tmp_path))
    _seed_claim_layer_fixture(vault)

    metrics = collect_claim_layer_metrics(vault, "claim_layer_programme")

    assert metrics["evidence_span_count"] == 2
    assert metrics["claim_count"] == 2
    assert metrics["validated_claim_count"] == 1
    assert metrics["needs_review_claim_count"] == 1
    assert metrics["promotable_claim_count"] == 1
    assert metrics["canonical_entity_count"] == 4
    assert metrics["extraction_failure_count"] == 0


def test_evaluate_claim_layer_matches_expected_claims_by_canonical_entities(tmp_path):
    vault = HybridVault(tenant_id="claim_eval_match", base_dir=str(tmp_path))
    _seed_claim_layer_fixture(vault)

    result = evaluate_claim_layer(
        vault,
        "claim_layer_programme",
        {
            "expected_claims": [
                {"claim_type": "dependency", "subject": "cloud migration", "object": "security certification"},
                {"claim_type": "blocker", "subject": "api gateway", "object": "deployment"},
            ],
            "metrics": {"claim_match_rate": {"exact": 1.0}},
        },
    )

    assert result["passed"] is True
    assert result["metrics"]["claim_match_rate"] == 1.0
    assert result["missing_claims"] == []


def test_evaluate_claim_layer_reports_missing_expected_claims(tmp_path):
    vault = HybridVault(tenant_id="claim_eval_missing", base_dir=str(tmp_path))
    _seed_claim_layer_fixture(vault)

    result = evaluate_claim_layer(
        vault,
        "claim_layer_programme",
        {
            "expected_claims": [
                {"claim_type": "dependency", "subject": "cloud migration", "object": "security certification"},
                {"claim_type": "dependency", "subject": "payment service", "object": "API gateway"},
            ],
            "metrics": {"claim_match_rate": {"min": 1.0}},
        },
    )

    assert result["passed"] is False
    assert result["missing_claims"] == [
        {"claim_type": "dependency", "subject": "payment service", "object": "API gateway"}
    ]
    assert "claim_match_rate expected >= 1.0, got 0.5" in result["failures"]


def test_evaluate_claim_layer_baseline_uses_fixture_file(tmp_path):
    baseline_path = FIXTURE_DIR / "claim_layer_programme_baseline.json"
    baseline = load_evaluation_baseline(baseline_path)
    vault = HybridVault(tenant_id="claim_eval_baseline", base_dir=str(tmp_path))
    _seed_claim_layer_fixture(vault)

    result = evaluate_claim_layer_baseline(vault, baseline_path)

    assert baseline["document_path"] == FIXTURE_DIR / "claim_layer_programme.md"
    assert result["passed"] is True
    assert result["metrics"]["claim_match_rate"] == 1.0


def test_claim_layer_ingestion_fixture_evaluates_against_baseline(monkeypatch, tmp_path):
    baseline_path = FIXTURE_DIR / "claim_layer_programme_baseline.json"
    baseline = load_evaluation_baseline(baseline_path)
    document_id = baseline["document_id"]
    vault = HybridVault(tenant_id="claim_eval_ingestion", base_dir=str(tmp_path))

    def fake_extract_claims(spans: list[EvidenceSpan]) -> ClaimExtractionResult:
        span_by_text = {span.text: span.span_id for span in spans}
        certification_span_id = next(
            span.span_id for span in spans if "Security Certification" in span.text
        )
        gateway_span_id = next(
            span.span_id for span in spans if "API Gateway" in span.text
        )
        return ClaimExtractionResult(
            claims=[
                ExtractedClaim(
                    claim_id="claim_1",
                    document_id=document_id,
                    claim_type="dependency",
                    subject="The Cloud-Migration Programme",
                    predicate="requires",
                    object="Security Certification",
                    modality="must",
                    certainty="explicit",
                    evidence_span_ids=[certification_span_id],
                    source_quote=next(text for text in span_by_text if "Security Certification" in text),
                    confidence=0.91,
                ),
                ExtractedClaim(
                    claim_id="claim_2",
                    document_id=document_id,
                    claim_type="blocker",
                    subject="API Gateway",
                    predicate="may block",
                    object="Deployment",
                    modality="may",
                    certainty="implied",
                    evidence_span_ids=[gateway_span_id],
                    source_quote=next(text for text in span_by_text if "API Gateway" in text),
                    confidence=0.72,
                ),
            ],
            failures=[],
            metrics={
                "batches_attempted": 1,
                "batches_succeeded": 1,
                "batches_failed": 0,
                "claims_before_dedupe": 2,
                "claims_after_dedupe": 2,
            },
        )

    monkeypatch.setenv("DIAMOND_MINER_CLAIM_LAYER", "1")
    monkeypatch.setattr("core.accuracy.claim_extractor.extract_claims_with_failures", fake_extract_claims)
    monkeypatch.setattr("core.agents.DeconstructorAgent.extract_topology", lambda text: {"nodes": [], "edges": []})

    orchestrator = DiamondOrchestrator(
        tenant_id="claim_eval_ingestion",
        document_id=document_id,
        document_name=baseline["document_path"].name,
        vault=vault,
    )
    orchestrator.run_ingestion_pipeline(str(baseline["document_path"]), max_workers=1)

    result = evaluate_claim_layer_baseline(vault, baseline_path)

    assert result["passed"] is True
    assert result["metrics"]["claim_count"] == 2
    assert result["metrics"]["validated_claim_count"] == 1
    assert result["metrics"]["needs_review_claim_count"] == 1
    assert result["metrics"]["claim_match_rate"] == 1.0
    assert orchestrator.accuracy_metrics["claims_after_dedupe"] == 2


def test_collect_claim_promotion_metrics_requires_provenance(tmp_path):
    vault = HybridVault(tenant_id="claim_promotion_metrics", base_dir=str(tmp_path))
    vault.insert_document("claim_layer_programme", "claim_layer_programme.md")
    vault.insert_graph_topology(
        nodes=[
            {"id": "entity_cloud_migration", "label": "Concept", "name": "Cloud Migration"},
            {"id": "entity_security_certification", "label": "Concept", "name": "Security Certification"},
        ],
        edges=[
            {
                "source_id": "entity_cloud_migration",
                "target_id": "entity_security_certification",
                "relationship": "REQUIRES",
                "claim_id": "claim_1",
                "evidence_span_ids": ["span_1"],
            }
        ],
        source_chunk_id="claim_layer",
        document_id="claim_layer_programme",
    )

    metrics = collect_claim_promotion_metrics(vault, "claim_layer_programme")

    assert metrics == {
        "promoted_node_count": 2,
        "promoted_edge_count": 1,
        "promoted_self_edge_count": 0,
        "promoted_edges_with_claim_id": 1,
        "promoted_edges_with_evidence": 1,
    }


def test_evaluate_claim_promotion_matches_expected_canonical_edges(tmp_path):
    vault = HybridVault(tenant_id="claim_promotion_eval", base_dir=str(tmp_path))
    vault.insert_document("claim_layer_programme", "claim_layer_programme.md")
    vault.insert_graph_topology(
        nodes=[
            {"id": "entity_cloud_migration", "label": "Concept", "name": "Cloud Migration"},
            {"id": "entity_security_certification", "label": "Concept", "name": "Security Certification"},
        ],
        edges=[
            {
                "source_id": "entity_cloud_migration",
                "target_id": "entity_security_certification",
                "relationship": "REQUIRES",
                "claim_id": "claim_1",
                "evidence_span_ids": ["span_1"],
            }
        ],
        source_chunk_id="claim_layer",
        document_id="claim_layer_programme",
    )

    result = evaluate_claim_promotion(
        vault,
        "claim_layer_programme",
        {
            "expected_edges": [
                {"source": "cloud migration", "target": "security certification", "relationship": "REQUIRES"}
            ],
            "metrics": {"promoted_edge_match_rate": {"exact": 1.0}},
        },
    )

    assert result["passed"] is True
    assert result["metrics"]["promoted_edge_match_rate"] == 1.0
    assert result["missing_edges"] == []


def test_claim_promotion_ingestion_fixture_evaluates_against_baseline(monkeypatch, tmp_path):
    baseline_path = FIXTURE_DIR / "claim_layer_programme_baseline.json"
    baseline = load_evaluation_baseline(baseline_path)
    document_id = baseline["document_id"]
    vault = HybridVault(tenant_id="claim_promotion_ingestion", base_dir=str(tmp_path))

    def fake_extract_claims(spans: list[EvidenceSpan]) -> ClaimExtractionResult:
        certification_span_id = next(
            span.span_id for span in spans if "Security Certification" in span.text
        )
        gateway_span_id = next(
            span.span_id for span in spans if "API Gateway" in span.text
        )
        return ClaimExtractionResult(
            claims=[
                ExtractedClaim(
                    claim_id="claim_1",
                    document_id=document_id,
                    claim_type="dependency",
                    subject="The Cloud-Migration Programme",
                    predicate="requires",
                    object="Security Certification",
                    modality="must",
                    certainty="explicit",
                    evidence_span_ids=[certification_span_id],
                    source_quote="The Cloud-Migration Programme requires Security Certification.",
                    confidence=0.91,
                ),
                ExtractedClaim(
                    claim_id="claim_2",
                    document_id=document_id,
                    claim_type="blocker",
                    subject="API Gateway",
                    predicate="may block",
                    object="Deployment",
                    modality="may",
                    certainty="implied",
                    evidence_span_ids=[gateway_span_id],
                    source_quote="The API Gateway may block Deployment.",
                    confidence=0.72,
                ),
            ],
            failures=[],
        )

    monkeypatch.setenv("DIAMOND_MINER_CLAIM_LAYER", "1")
    monkeypatch.setenv("DIAMOND_MINER_USE_CLAIM_PROMOTION", "1")
    monkeypatch.setattr("core.accuracy.claim_extractor.extract_claims_with_failures", fake_extract_claims)
    monkeypatch.setattr("core.agents.DeconstructorAgent.extract_topology", lambda text: {"nodes": [], "edges": []})

    orchestrator = DiamondOrchestrator(
        tenant_id="claim_promotion_ingestion",
        document_id=document_id,
        document_name=baseline["document_path"].name,
        vault=vault,
    )
    orchestrator.run_ingestion_pipeline(str(baseline["document_path"]), max_workers=1)

    result = evaluate_claim_promotion_baseline(vault, baseline_path)

    assert result["passed"] is True
    assert result["metrics"]["promoted_edge_count"] == 1
    assert result["metrics"]["promoted_edges_with_claim_id"] == 1
    assert result["metrics"]["promoted_edges_with_evidence"] == 1
    assert result["missing_edges"] == []


def test_collect_parallel_graph_metrics_compares_legacy_and_claim_edges(tmp_path):
    vault = HybridVault(tenant_id="parallel_graph_metrics", base_dir=str(tmp_path))
    vault.insert_document("claim_layer_programme", "claim_layer_programme.md")
    vault.insert_graph_topology(
        nodes=[
            {"id": "cloud_migration", "label": "Concept", "name": "Cloud Migration"},
            {"id": "security_certification", "label": "Concept", "name": "Security Certification"},
        ],
        edges=[
            {
                "source_id": "cloud_migration",
                "target_id": "security_certification",
                "relationship": "REQUIRES",
            }
        ],
        source_chunk_id="legacy_chunk",
        document_id="claim_layer_programme",
    )
    vault.insert_graph_topology(
        nodes=[
            {"id": "entity_cloud_migration", "label": "Concept", "name": "Cloud Migration"},
            {"id": "entity_security_certification", "label": "Concept", "name": "Security Certification"},
        ],
        edges=[
            {
                "source_id": "entity_cloud_migration",
                "target_id": "entity_security_certification",
                "relationship": "REQUIRES",
                "claim_id": "claim_1",
                "evidence_span_ids": ["span_1"],
            }
        ],
        source_chunk_id="claim_layer",
        document_id="claim_layer_programme",
    )

    metrics = collect_parallel_graph_metrics(vault, "claim_layer_programme")

    assert metrics == {
        "legacy_edge_count": 1,
        "claim_promoted_edge_count": 1,
        "shared_canonical_edge_count": 1,
        "legacy_only_edge_count": 0,
        "claim_only_edge_count": 0,
        "claim_vs_legacy_overlap_rate": 1.0,
    }


def test_collect_parallel_graph_agreement_includes_mismatch_samples(tmp_path):
    vault = HybridVault(tenant_id="parallel_graph_mismatches", base_dir=str(tmp_path))
    vault.insert_document("claim_layer_programme", "claim_layer_programme.md")
    vault.insert_graph_topology(
        nodes=[
            {"id": "cloud_migration", "label": "Concept", "name": "Cloud Migration"},
            {"id": "security_certification", "label": "Concept", "name": "Security Certification"},
            {"id": "data_migration", "label": "Concept", "name": "Data Migration"},
            {"id": "cutover_plan", "label": "Concept", "name": "Cutover Plan"},
        ],
        edges=[
            {
                "source_id": "cloud_migration",
                "target_id": "security_certification",
                "relationship": "REQUIRES",
            },
            {
                "source_id": "data_migration",
                "target_id": "cutover_plan",
                "relationship": "REQUIRES",
            },
        ],
        source_chunk_id="legacy_chunk",
        document_id="claim_layer_programme",
    )
    vault.insert_graph_topology(
        nodes=[
            {"id": "entity_cloud_migration", "label": "Concept", "name": "Cloud Migration"},
            {"id": "entity_security_certification", "label": "Concept", "name": "Security Certification"},
            {"id": "entity_api_gateway", "label": "Concept", "name": "API Gateway"},
            {"id": "entity_deployment", "label": "Concept", "name": "Deployment"},
        ],
        edges=[
            {
                "source_id": "entity_cloud_migration",
                "target_id": "entity_security_certification",
                "relationship": "REQUIRES",
                "claim_id": "claim_1",
                "evidence_span_ids": ["span_1"],
            },
            {
                "source_id": "entity_api_gateway",
                "target_id": "entity_deployment",
                "relationship": "BLOCKS",
                "claim_id": "claim_2",
                "evidence_span_ids": ["span_2"],
            },
        ],
        source_chunk_id="claim_layer",
        document_id="claim_layer_programme",
    )

    agreement = collect_parallel_graph_agreement(vault, "claim_layer_programme")

    assert agreement["legacy_edge_count"] == 2
    assert agreement["claim_promoted_edge_count"] == 2
    assert agreement["shared_canonical_edge_count"] == 1
    assert agreement["legacy_only_edge_count"] == 1
    assert agreement["claim_only_edge_count"] == 1
    assert agreement["claim_vs_legacy_overlap_rate"] == 0.5
    assert agreement["legacy_only_edges"] == [
        {
            "source_id": "data_migration",
            "target_id": "cutover_plan",
            "relationship": "REQUIRES",
            "canonical_source_id": "entity_data_migration",
            "canonical_target_id": "entity_cutover_plan",
            "source_chunk_id": "legacy_chunk",
            "claim_id": None,
            "evidence_span_ids": [],
        }
    ]
    assert agreement["claim_only_edges"] == [
        {
            "source_id": "entity_api_gateway",
            "target_id": "entity_deployment",
            "relationship": "BLOCKS",
            "canonical_source_id": "entity_api_gateway",
            "canonical_target_id": "entity_deployment",
            "source_chunk_id": "claim_layer",
            "claim_id": "claim_2",
            "evidence_span_ids": ["span_2"],
        }
    ]


def test_evaluate_parallel_graph_comparison_uses_fixture_expectations(tmp_path):
    baseline_path = FIXTURE_DIR / "claim_layer_programme_baseline.json"
    baseline = load_evaluation_baseline(baseline_path)
    vault = HybridVault(tenant_id="parallel_graph_baseline", base_dir=str(tmp_path))
    vault.insert_document("claim_layer_programme", "claim_layer_programme.md")
    vault.insert_graph_topology(
        nodes=[
            {"id": "cloud_migration", "label": "Concept", "name": "Cloud Migration"},
            {"id": "security_certification", "label": "Concept", "name": "Security Certification"},
        ],
        edges=[
            {
                "source_id": "cloud_migration",
                "target_id": "security_certification",
                "relationship": "REQUIRES",
            },
        ],
        source_chunk_id="legacy_chunk",
        document_id="claim_layer_programme",
    )
    vault.insert_graph_topology(
        nodes=[
            {"id": "entity_cloud_migration", "label": "Concept", "name": "Cloud Migration"},
            {"id": "entity_security_certification", "label": "Concept", "name": "Security Certification"},
        ],
        edges=[
            {
                "source_id": "entity_cloud_migration",
                "target_id": "entity_security_certification",
                "relationship": "REQUIRES",
                "claim_id": "claim_1",
                "evidence_span_ids": ["span_1"],
            }
        ],
        source_chunk_id="claim_layer",
        document_id="claim_layer_programme",
    )

    direct_result = evaluate_parallel_graph_comparison(
        vault,
        "claim_layer_programme",
        baseline["parallel_expectations"],
    )
    baseline_result = evaluate_parallel_graph_baseline(vault, baseline_path)

    assert direct_result["passed"] is True
    assert baseline_result["passed"] is True
    assert baseline_result["metrics"]["shared_canonical_edge_count"] == 1


def test_parallel_graph_ingestion_fixture_compares_legacy_and_claim_promotion(monkeypatch, tmp_path):
    baseline_path = FIXTURE_DIR / "claim_layer_programme_baseline.json"
    baseline = load_evaluation_baseline(baseline_path)
    document_id = baseline["document_id"]
    vault = HybridVault(tenant_id="parallel_graph_ingestion", base_dir=str(tmp_path))

    def fake_extract_claims(spans: list[EvidenceSpan]) -> ClaimExtractionResult:
        certification_span_id = next(
            span.span_id for span in spans if "Security Certification" in span.text
        )
        gateway_span_id = next(
            span.span_id for span in spans if "API Gateway" in span.text
        )
        return ClaimExtractionResult(
            claims=[
                ExtractedClaim(
                    claim_id="claim_1",
                    document_id=document_id,
                    claim_type="dependency",
                    subject="The Cloud-Migration Programme",
                    predicate="requires",
                    object="Security Certification",
                    modality="must",
                    certainty="explicit",
                    evidence_span_ids=[certification_span_id],
                    source_quote="The Cloud-Migration Programme requires Security Certification.",
                    confidence=0.91,
                ),
                ExtractedClaim(
                    claim_id="claim_2",
                    document_id=document_id,
                    claim_type="blocker",
                    subject="API Gateway",
                    predicate="may block",
                    object="Deployment",
                    modality="may",
                    certainty="implied",
                    evidence_span_ids=[gateway_span_id],
                    source_quote="The API Gateway may block Deployment.",
                    confidence=0.72,
                ),
            ],
            failures=[],
        )

    legacy_topology = {
        "nodes": [
            {"id": "cloud_migration", "label": "Concept", "name": "Cloud Migration"},
            {"id": "security_certification", "label": "Concept", "name": "Security Certification"},
        ],
        "edges": [
            {
                "source_id": "cloud_migration",
                "target_id": "security_certification",
                "relationship": "REQUIRES",
            }
        ],
    }

    monkeypatch.setenv("DIAMOND_MINER_CLAIM_LAYER", "1")
    monkeypatch.setenv("DIAMOND_MINER_USE_CLAIM_PROMOTION", "1")
    monkeypatch.setattr("core.accuracy.claim_extractor.extract_claims_with_failures", fake_extract_claims)
    monkeypatch.setattr("core.agents.DeconstructorAgent.extract_topology", lambda text: legacy_topology)
    monkeypatch.setattr("core.agents.ChronosAgent.extract_time_data", lambda text, nodes: {"temporal_edges": []})

    orchestrator = DiamondOrchestrator(
        tenant_id="parallel_graph_ingestion",
        document_id=document_id,
        document_name=baseline["document_path"].name,
        vault=vault,
    )
    orchestrator.run_ingestion_pipeline(str(baseline["document_path"]), max_workers=1)

    result = evaluate_parallel_graph_baseline(vault, baseline_path)

    assert result["passed"] is True
    assert result["metrics"]["claim_vs_legacy_overlap_rate"] == 1.0
