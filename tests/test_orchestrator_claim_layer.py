import json

from datetime import datetime, timezone

from core.accuracy.claim_extractor import ClaimExtractionResult
from core.accuracy.schemas import ExtractionFailure, ExtractedClaim
from core.orchestrator import DiamondOrchestrator
from core.vault import HybridVault


def test_claim_layer_stores_manifest_spans_claims_and_validation(monkeypatch, tmp_path):
    source = tmp_path / "strategy.md"
    source.write_text("Cloud migration requires Security certification.", encoding="utf-8")
    vault = HybridVault(tenant_id="claim_layer", base_dir=str(tmp_path / "vaults"))

    def fake_extract_claims(spans):
        return ClaimExtractionResult(claims=[
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
        ], failures=[])

    monkeypatch.setenv("DIAMOND_MINER_CLAIM_LAYER", "1")
    monkeypatch.setattr("core.accuracy.claim_extractor.extract_claims_with_failures", fake_extract_claims)
    monkeypatch.setattr("core.agents.DeconstructorAgent.extract_topology", lambda text: {"nodes": [], "edges": []})

    orchestrator = DiamondOrchestrator(
        tenant_id="claim_layer",
        document_id="doc_1",
        document_name="strategy.md",
        vault=vault,
    )
    orchestrator.run_ingestion_pipeline(str(source), max_workers=1)

    assert vault.get_document_manifest("doc_1")["filename"] == "strategy.md"
    assert len(vault.list_evidence_spans("doc_1")) == 1
    assert vault.list_extracted_claims("doc_1")[0]["subject"] == "Cloud migration"
    assert vault.list_validation_results("doc_1")[0]["status"] == "passed"

    vault.conn.close()


def test_claim_promotion_flag_writes_validated_claim_to_graph(monkeypatch, tmp_path):
    source = tmp_path / "strategy.md"
    source.write_text("Cloud migration requires Security certification.", encoding="utf-8")
    vault = HybridVault(tenant_id="claim_promotion", base_dir=str(tmp_path / "vaults"))

    def fake_extract_claims(spans):
        return ClaimExtractionResult(claims=[
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
        ], failures=[])

    monkeypatch.setenv("DIAMOND_MINER_CLAIM_LAYER", "1")
    monkeypatch.setenv("DIAMOND_MINER_USE_CLAIM_PROMOTION", "1")
    monkeypatch.setattr("core.accuracy.claim_extractor.extract_claims_with_failures", fake_extract_claims)
    monkeypatch.setattr("core.agents.DeconstructorAgent.extract_topology", lambda text: {"nodes": [], "edges": []})

    orchestrator = DiamondOrchestrator(
        tenant_id="claim_promotion",
        document_id="doc_1",
        document_name="strategy.md",
        vault=vault,
    )
    orchestrator.run_ingestion_pipeline(str(source), max_workers=1)

    cursor = vault.conn.cursor()
    cursor.execute(
        """
        SELECT source_id, target_id, relationship, claim_id, evidence_span_ids
        FROM edges
        WHERE document_id = ?
        """,
        ("doc_1",),
    )
    rows = [dict(row) for row in cursor.fetchall()]

    assert len(rows) == 1
    assert rows[0]["source_id"] == "entity_cloud_migration"
    assert rows[0]["target_id"] == "entity_security_certification"
    assert rows[0]["relationship"] == "REQUIRES"
    assert rows[0]["claim_id"] == "claim_1"
    assert json.loads(rows[0]["evidence_span_ids"])[0].startswith("span_doc_1_")

    vault.conn.close()


def test_claim_layer_persists_extraction_failures(monkeypatch, tmp_path):
    source = tmp_path / "strategy.md"
    source.write_text("Cloud migration requires Security certification.", encoding="utf-8")
    vault = HybridVault(tenant_id="claim_failures", base_dir=str(tmp_path / "vaults"))

    def fake_extract_claims(spans):
        return ClaimExtractionResult(
            claims=[],
            failures=[
                ExtractionFailure(
                    id="failure_1",
                    document_id="doc_1",
                    span_id=spans[0].span_id,
                    agent="claim_extractor",
                    error="Invalid JSON response",
                    raw_payload="{not-json",
                    created_at=datetime.now(timezone.utc),
                )
            ],
        )

    monkeypatch.setenv("DIAMOND_MINER_CLAIM_LAYER", "1")
    monkeypatch.setattr("core.accuracy.claim_extractor.extract_claims_with_failures", fake_extract_claims)
    monkeypatch.setattr("core.agents.DeconstructorAgent.extract_topology", lambda text: {"nodes": [], "edges": []})

    orchestrator = DiamondOrchestrator(
        tenant_id="claim_failures",
        document_id="doc_1",
        document_name="strategy.md",
        vault=vault,
    )
    orchestrator.run_ingestion_pipeline(str(source), max_workers=1)

    failures = vault.list_extraction_failures("doc_1")
    assert failures[0]["id"] == "failure_1"
    assert orchestrator.accuracy_metrics["extraction_failures"] == 1

    vault.conn.close()


def test_claim_layer_includes_batch_metrics_in_accuracy_telemetry(monkeypatch, tmp_path):
    source = tmp_path / "strategy.md"
    source.write_text("Cloud migration requires Security certification.", encoding="utf-8")
    vault = HybridVault(tenant_id="claim_batch_metrics", base_dir=str(tmp_path / "vaults"))

    def fake_extract_claims(spans):
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
            metrics={
                "batches_attempted": 2,
                "batches_succeeded": 2,
                "batches_failed": 0,
                "claims_before_dedupe": 2,
                "claims_after_dedupe": 1,
            },
        )

    monkeypatch.setenv("DIAMOND_MINER_CLAIM_LAYER", "1")
    monkeypatch.setattr("core.accuracy.claim_extractor.extract_claims_with_failures", fake_extract_claims)
    monkeypatch.setattr("core.agents.DeconstructorAgent.extract_topology", lambda text: {"nodes": [], "edges": []})

    orchestrator = DiamondOrchestrator(
        tenant_id="claim_batch_metrics",
        document_id="doc_1",
        document_name="strategy.md",
        vault=vault,
    )
    orchestrator.run_ingestion_pipeline(str(source), max_workers=1)

    assert orchestrator.accuracy_metrics["batches_attempted"] == 2
    assert orchestrator.accuracy_metrics["batches_succeeded"] == 2
    assert orchestrator.accuracy_metrics["claims_before_dedupe"] == 2
    assert orchestrator.accuracy_metrics["claims_after_dedupe"] == 1

    vault.conn.close()


def test_claim_layer_persists_canonical_entities(monkeypatch, tmp_path):
    source = tmp_path / "strategy.md"
    source.write_text("The Cloud-Migration Programme requires Security Certification.", encoding="utf-8")
    vault = HybridVault(tenant_id="claim_canonical_entities", base_dir=str(tmp_path / "vaults"))

    def fake_extract_claims(spans):
        return ClaimExtractionResult(claims=[
            ExtractedClaim(
                claim_id="claim_1",
                document_id="doc_1",
                claim_type="dependency",
                subject="The Cloud-Migration Programme",
                predicate="requires",
                object="Security Certification",
                modality="must",
                certainty="explicit",
                evidence_span_ids=[spans[0].span_id],
                source_quote=spans[0].text,
                confidence=0.9,
            )
        ], failures=[])

    monkeypatch.setenv("DIAMOND_MINER_CLAIM_LAYER", "1")
    monkeypatch.setattr("core.accuracy.claim_extractor.extract_claims_with_failures", fake_extract_claims)
    monkeypatch.setattr("core.agents.DeconstructorAgent.extract_topology", lambda text: {"nodes": [], "edges": []})

    orchestrator = DiamondOrchestrator(
        tenant_id="claim_canonical_entities",
        document_id="doc_1",
        document_name="strategy.md",
        vault=vault,
    )
    orchestrator.run_ingestion_pipeline(str(source), max_workers=1)

    entities = vault.list_canonical_entities("doc_1")
    assert entities[0]["entity_id"] == "entity_cloud_migration"
    assert entities[0]["canonical_name"] == "Cloud Migration"
    assert entities[0]["aliases"] == ["The Cloud-Migration Programme"]
    assert orchestrator.accuracy_metrics["canonical_entities"] == 2

    vault.conn.close()
