import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from core.accuracy.schemas import EvidenceSpan, ExtractionFailure, ExtractedClaim
from core.agents import FAST_JSON_MAX_TOKENS, _get_client, _get_model


SYSTEM_PROMPT = """You are a claim extraction engine for operational risk analysis.

Extract only atomic claims that are directly supported by the provided evidence spans.
Do not create graph nodes or graph edges.
Every claim must cite at least one evidence_span_id.
Prefer explicit claims. Mark uncertain interpretations as implied or inferred.

Return only valid JSON:
{
  "claims": [
    {
      "claim_id": "claim_<document_id>_<span_id>_<index>",
      "document_id": "<document_id>",
      "claim_type": "dependency | blocker | objective | success_criterion | date_constraint | resource_requirement | owner_assignment | risk | assumption | deliverable | scope_inclusion | scope_exclusion | governance_rule | quality_requirement",
      "subject": "specific entity or work item",
      "predicate": "short verb phrase",
      "object": "specific entity, date, condition, or result",
      "modality": "must | should | may | assumes | prohibits",
      "certainty": "explicit | implied | inferred",
      "status": "active | superseded | rejected | unknown",
      "date_start": null,
      "date_end": null,
      "owner": "",
      "evidence_span_ids": ["span_id"],
      "source_quote": "exact quote from evidence span",
      "confidence": 0.0
    }
  ]
}
"""


@dataclass
class ClaimExtractionResult:
    claims: list[ExtractedClaim]
    failures: list[ExtractionFailure]
    metrics: dict[str, int] = field(default_factory=dict)


def _failure(
    *,
    document_id: str,
    span_id: str,
    error: str,
    raw_payload: str,
) -> ExtractionFailure:
    return ExtractionFailure(
        id=f"failure_{uuid.uuid4().hex}",
        document_id=document_id,
        span_id=span_id,
        agent="claim_extractor",
        error=error,
        raw_payload=raw_payload,
        created_at=datetime.now(timezone.utc),
    )


def parse_claim_response(raw_json: str) -> list[ExtractedClaim]:
    return parse_claim_response_with_failures(
        raw_json,
        document_id="",
        span_ids=[],
    ).claims


def parse_claim_response_with_failures(
    raw_json: str,
    *,
    document_id: str,
    span_ids: list[str],
) -> ClaimExtractionResult:
    fallback_span_id = span_ids[0] if span_ids else ""
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return ClaimExtractionResult(
            claims=[],
            failures=[
                _failure(
                    document_id=document_id,
                    span_id=fallback_span_id,
                    error=f"Invalid JSON response: {exc}",
                    raw_payload=raw_json,
                )
            ],
        )

    claims: list[ExtractedClaim] = []
    failures: list[ExtractionFailure] = []
    for item in payload.get("claims", []):
        try:
            claims.append(ExtractedClaim(**item))
        except ValidationError as exc:
            item_span_ids = item.get("evidence_span_ids") if isinstance(item, dict) else None
            span_id = item_span_ids[0] if isinstance(item_span_ids, list) and item_span_ids else fallback_span_id
            failure_document_id = document_id
            if isinstance(item, dict) and not failure_document_id:
                failure_document_id = str(item.get("document_id", ""))
            failures.append(
                _failure(
                    document_id=failure_document_id,
                    span_id=span_id,
                    error=str(exc),
                    raw_payload=json.dumps(item),
                )
            )
        except Exception as exc:
            failures.append(
                _failure(
                    document_id=document_id,
                    span_id=fallback_span_id,
                    error=str(exc),
                    raw_payload=json.dumps(item),
                )
            )
    return ClaimExtractionResult(claims=claims, failures=failures)


def extract_claims(spans: list[EvidenceSpan]) -> list[ExtractedClaim]:
    return extract_claims_with_failures(spans).claims


def batch_evidence_spans(
    spans: list[EvidenceSpan],
    *,
    max_spans: int = 15,
    max_chars: int = 12000,
) -> list[list[EvidenceSpan]]:
    batches: list[list[EvidenceSpan]] = []
    current_batch: list[EvidenceSpan] = []
    current_chars = 0

    for span in spans:
        span_chars = len(span.text)
        would_exceed_count = len(current_batch) >= max_spans
        would_exceed_chars = current_batch and current_chars + span_chars > max_chars
        if would_exceed_count or would_exceed_chars:
            batches.append(current_batch)
            current_batch = []
            current_chars = 0
        current_batch.append(span)
        current_chars += span_chars

    if current_batch:
        batches.append(current_batch)

    return batches


def _claim_dedupe_key(claim: ExtractedClaim) -> tuple[str, str, str, str, str, str]:
    return (
        claim.document_id.strip().lower(),
        claim.claim_type.strip().lower(),
        claim.subject.strip().lower(),
        claim.predicate.strip().lower(),
        claim.object.strip().lower(),
        claim.source_quote.strip().lower(),
    )


def dedupe_claims(claims: list[ExtractedClaim]) -> list[ExtractedClaim]:
    deduped: list[ExtractedClaim] = []
    seen: set[tuple[str, str, str, str, str, str]] = set()
    for claim in claims:
        key = _claim_dedupe_key(claim)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(claim)
    return deduped


def _extract_claim_batch(spans: list[EvidenceSpan]) -> ClaimExtractionResult:
    if not spans:
        return ClaimExtractionResult(claims=[], failures=[])

    span_payload: list[dict[str, Any]] = [
        {
            "span_id": span.span_id,
            "document_id": span.document_id,
            "text": span.text,
            "span_type": span.span_type,
        }
        for span in spans
    ]

    try:
        response = _get_client().chat.completions.create(
            model=_get_model("fast"),
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=FAST_JSON_MAX_TOKENS,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps({"evidence_spans": span_payload})},
            ],
        )
    except Exception as exc:
        return ClaimExtractionResult(
            claims=[],
            failures=[
                _failure(
                    document_id=spans[0].document_id,
                    span_id=spans[0].span_id,
                    error=f"Model call failed: {exc}",
                    raw_payload=json.dumps({"evidence_spans": span_payload}),
                )
            ],
        )

    return parse_claim_response_with_failures(
        response.choices[0].message.content or "",
        document_id=spans[0].document_id,
        span_ids=[span.span_id for span in spans],
    )


def extract_claims_with_failures(
    spans: list[EvidenceSpan],
    *,
    max_spans_per_batch: int = 15,
    max_chars_per_batch: int = 12000,
) -> ClaimExtractionResult:
    if not spans:
        return ClaimExtractionResult(
            claims=[],
            failures=[],
            metrics={
                "batches_attempted": 0,
                "batches_succeeded": 0,
                "batches_failed": 0,
                "claims_before_dedupe": 0,
                "claims_after_dedupe": 0,
            },
        )

    claims: list[ExtractedClaim] = []
    failures: list[ExtractionFailure] = []
    batches_attempted = 0
    batches_succeeded = 0
    batches_failed = 0

    for batch in batch_evidence_spans(
        spans,
        max_spans=max_spans_per_batch,
        max_chars=max_chars_per_batch,
    ):
        batches_attempted += 1
        result = _extract_claim_batch(batch)
        claims.extend(result.claims)
        failures.extend(result.failures)
        if result.failures and not result.claims:
            batches_failed += 1
        else:
            batches_succeeded += 1

    deduped_claims = dedupe_claims(claims)
    return ClaimExtractionResult(
        claims=deduped_claims,
        failures=failures,
        metrics={
            "batches_attempted": batches_attempted,
            "batches_succeeded": batches_succeeded,
            "batches_failed": batches_failed,
            "claims_before_dedupe": len(claims),
            "claims_after_dedupe": len(deduped_claims),
        },
    )
