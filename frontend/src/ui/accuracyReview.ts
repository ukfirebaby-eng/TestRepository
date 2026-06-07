import type { AccuracyClaim, AccuracyEvidenceSpan, AccuracyGraphAgreementEdge } from "../api/types";

export type GraphReviewCandidateKind = "claim-only" | "legacy-only";
export type GraphReviewState = "needs_review" | "accepted" | "ignored";
export type GraphReviewFilter = "all" | GraphReviewState;
export type GraphReviewStateMap = Record<string, GraphReviewState>;

export type GraphReviewCandidate = {
  id: string;
  kind: GraphReviewCandidateKind;
  label: string;
  status: string;
  summary: string;
  evidence: string;
  action: string;
  reviewState: GraphReviewState;
};

function readableId(value: string) {
  return value.replace(/^entity_/, "").replace(/_/g, " ");
}

function edgeLabel(edge: AccuracyGraphAgreementEdge) {
  return `${readableId(edge.source_id)} ${edge.relationship.toLowerCase()} ${readableId(edge.target_id)}`;
}

function spanText(edge: AccuracyGraphAgreementEdge, spans: AccuracyEvidenceSpan[]) {
  const spanIds = new Set(edge.evidence_span_ids || []);
  return spans
    .filter((span) => spanIds.has(span.span_id))
    .map((span) => span.text)
    .filter(Boolean)
    .join(" ");
}

export function reviewCandidateKey(edge: AccuracyGraphAgreementEdge, kind: GraphReviewCandidateKind): string {
  return `${kind}:${edge.canonical_source_id || edge.source_id}:${edge.relationship}:${edge.canonical_target_id || edge.target_id}`;
}

export function filterReviewCandidates(
  candidates: GraphReviewCandidate[],
  states: GraphReviewStateMap,
  filter: GraphReviewFilter,
): GraphReviewCandidate[] {
  return candidates
    .map((candidate) => ({ ...candidate, reviewState: states[candidate.id] || candidate.reviewState }))
    .filter((candidate) => filter === "all" || candidate.reviewState === filter);
}

export function buildGraphReviewCandidate(
  edge: AccuracyGraphAgreementEdge,
  kind: GraphReviewCandidateKind,
  claims: AccuracyClaim[],
  spans: AccuracyEvidenceSpan[],
): GraphReviewCandidate {
  const claim = edge.claim_id ? claims.find((item) => item.claim_id === edge.claim_id) : undefined;
  const evidence = claim?.source_quote || spanText(edge, spans);
  const base = {
    id: reviewCandidateKey(edge, kind),
    kind,
    label: edgeLabel(edge),
    reviewState: edge.review_state || "needs_review" as const,
  };

  if (kind === "claim-only") {
    return {
      ...base,
      status: "Claim-backed, not in legacy graph",
      summary: "A validated claim produced this relationship, but the legacy graph extraction did not produce the same canonical edge.",
      evidence: evidence || "The claim is recorded, but no source quote is available in this payload.",
      action: "Check whether the legacy extraction missed this relationship, then decide whether claim promotion should keep it.",
    };
  }

  return {
    ...base,
    status: "Legacy graph only",
    summary: "The legacy graph extraction produced this relationship, but no matching validated claim currently backs it.",
    evidence: evidence || "No validated claim evidence is linked to this edge yet.",
    action: "Find source evidence or leave it out of claim-promoted graph output until it can be validated.",
  };
}
