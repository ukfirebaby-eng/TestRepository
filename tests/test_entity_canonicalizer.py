from core.accuracy.entity_canonicalizer import (
    build_canonical_entities_from_claims,
    canonical_entity_id,
    canonical_entity_name,
)
from core.accuracy.schemas import ExtractedClaim


def test_canonical_entity_id_collapses_case_punctuation_and_articles():
    assert canonical_entity_id("The Cloud-Migration Programme") == "entity_cloud_migration"
    assert canonical_entity_id("cloud migration") == "entity_cloud_migration"


def test_canonical_entity_name_keeps_readable_business_label():
    assert canonical_entity_name("the cloud-migration programme") == "Cloud Migration"


def test_canonical_entity_id_preserves_meaningful_system_suffixes():
    assert canonical_entity_id("Payment Processing Module") == "entity_payment_processing_module"


def test_canonical_entity_name_preserves_acronyms():
    assert canonical_entity_name("The API Gateway Programme") == "API Gateway"


def test_build_canonical_entities_groups_claim_aliases_and_source_spans():
    claims = [
        ExtractedClaim(
            claim_id="claim_1",
            document_id="doc_1",
            claim_type="dependency",
            subject="The Cloud-Migration Programme",
            predicate="requires",
            object="API Gateway",
            modality="must",
            certainty="explicit",
            evidence_span_ids=["span_1"],
            source_quote="The Cloud-Migration Programme requires API Gateway readiness.",
            confidence=0.9,
            validation_status="passed",
        ),
        ExtractedClaim(
            claim_id="claim_2",
            document_id="doc_1",
            claim_type="blocker",
            subject="cloud migration",
            predicate="is blocked by",
            object="API gateway service",
            modality="must",
            certainty="explicit",
            evidence_span_ids=["span_2"],
            source_quote="Cloud migration is blocked by the API gateway service.",
            confidence=0.8,
            validation_status="passed",
        ),
    ]

    entities = build_canonical_entities_from_claims(claims)

    cloud = next(entity for entity in entities if entity.entity_id == "entity_cloud_migration")
    assert cloud.canonical_name == "Cloud Migration"
    assert cloud.entity_type == "initiative"
    assert cloud.aliases == ["The Cloud-Migration Programme", "cloud migration"]
    assert cloud.source_span_ids == ["span_1", "span_2"]
    assert cloud.confidence == 0.9

    api_gateway = next(entity for entity in entities if entity.entity_id == "entity_api_gateway")
    assert api_gateway.entity_type == "system"
    assert api_gateway.aliases == ["API Gateway"]
