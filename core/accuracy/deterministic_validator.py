from collections.abc import Iterable

from core.accuracy.entity_canonicalizer import canonical_entity_id, is_generic_entity_name
from core.accuracy.schemas import ExtractedClaim, ValidationResult


PROMOTION_CONFIDENCE_THRESHOLD = 0.65


def validate_claim(claim: ExtractedClaim, *, known_span_ids: Iterable[str]) -> ValidationResult:
    known = set(known_span_ids)
    reasons: list[str] = []

    for span_id in claim.evidence_span_ids:
        if span_id not in known:
            reasons.append(f"Unknown evidence span: {span_id}")

    if claim.certainty != "explicit":
        reasons.append("Only explicit claims can be auto-promoted.")

    if claim.confidence < PROMOTION_CONFIDENCE_THRESHOLD:
        reasons.append("Confidence below promotion threshold.")

    if canonical_entity_id(claim.subject) == canonical_entity_id(claim.object):
        reasons.append("Claim subject and object resolve to the same entity.")

    if is_generic_entity_name(claim.subject):
        reasons.append(f"Claim subject is too generic for graph promotion: {claim.subject}.")

    if is_generic_entity_name(claim.object):
        reasons.append(f"Claim object is too generic for graph promotion: {claim.object}.")

    if claim.date_start and claim.date_end and claim.date_end < claim.date_start:
        reasons.append("Claim end date is before start date.")

    if any(reason.startswith("Unknown evidence span") for reason in reasons):
        status = "failed"
    elif reasons:
        status = "needs_review"
    else:
        status = "passed"

    return ValidationResult(
        claim_id=claim.claim_id,
        document_id=claim.document_id,
        status=status,
        reasons=reasons,
        can_promote=status == "passed",
    )
