from core.accuracy.entity_canonicalizer import canonical_entity_id, canonical_entity_name, is_generic_entity_name
from core.accuracy.schemas import ExtractedClaim


RELATIONSHIP_BY_CLAIM_TYPE = {
    "dependency": "REQUIRES",
    "blocker": "BLOCKS",
    "deliverable": "PRODUCES",
    "scope_inclusion": "RELATES_TO",
    "scope_exclusion": "BLOCKS",
    "governance_rule": "REQUIRES",
    "quality_requirement": "REQUIRES",
}


def promote_claim_to_topology(claim: ExtractedClaim) -> dict:
    if claim.validation_status != "passed":
        return {"nodes": [], "edges": []}

    relationship = RELATIONSHIP_BY_CLAIM_TYPE.get(claim.claim_type)
    if not relationship:
        return {"nodes": [], "edges": []}

    source_id = canonical_entity_id(claim.subject)
    target_id = canonical_entity_id(claim.object)
    if source_id == target_id:
        return {"nodes": [], "edges": []}
    if is_generic_entity_name(claim.subject) or is_generic_entity_name(claim.object):
        return {"nodes": [], "edges": []}

    return {
        "nodes": [
            {"id": source_id, "label": "Concept", "name": canonical_entity_name(claim.subject)},
            {"id": target_id, "label": "Concept", "name": canonical_entity_name(claim.object)},
        ],
        "edges": [
            {
                "source_id": source_id,
                "target_id": target_id,
                "relationship": relationship,
                "claim_id": claim.claim_id,
                "evidence_span_ids": claim.evidence_span_ids,
            }
        ],
    }
