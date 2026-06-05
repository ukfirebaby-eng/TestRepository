import { describe, expect, it } from "vitest";
import { buildGraphReviewCandidate } from "./accuracyReview";
import type { AccuracyClaim, AccuracyEvidenceSpan, AccuracyGraphAgreementEdge } from "../api/types";

const claimOnlyEdge: AccuracyGraphAgreementEdge = {
  source_id: "entity_cloud_migration",
  target_id: "entity_security_certification",
  relationship: "REQUIRES",
  canonical_source_id: "entity_cloud_migration",
  canonical_target_id: "entity_security_certification",
  source_chunk_id: "claim_layer",
  claim_id: "claim_1",
  evidence_span_ids: ["span_1"],
};

const legacyOnlyEdge: AccuracyGraphAgreementEdge = {
  source_id: "entity_legacy_launch",
  target_id: "entity_security_approval",
  relationship: "DEPENDS_ON",
  canonical_source_id: "entity_legacy_launch",
  canonical_target_id: "entity_security_approval",
  source_chunk_id: "chunk_7",
  evidence_span_ids: [],
};

const claims: AccuracyClaim[] = [
  {
    claim_id: "claim_1",
    document_id: "doc_1",
    claim_type: "dependency",
    subject: "Cloud migration",
    predicate: "requires",
    object: "Security certification",
    modality: "must",
    certainty: "explicit",
    status: "active",
    evidence_span_ids: ["span_1"],
    source_quote: "Cloud migration requires Security certification before launch.",
    confidence: 0.92,
    validation_status: "passed",
  },
];

const spans: AccuracyEvidenceSpan[] = [
  {
    span_id: "span_1",
    document_id: "doc_1",
    chunk_id: "chunk_1",
    page_number: 1,
    text: "Cloud migration requires Security certification before launch.",
    span_type: "sentence",
    source_hash: "sha256:abc",
  },
];

describe("buildGraphReviewCandidate", () => {
  it("summarizes claim-only edges with claim and evidence detail", () => {
    const candidate = buildGraphReviewCandidate(claimOnlyEdge, "claim-only", claims, spans);

    expect(candidate.label).toBe("cloud migration requires security certification");
    expect(candidate.status).toBe("Claim-backed, not in legacy graph");
    expect(candidate.evidence).toContain("Cloud migration requires Security certification before launch.");
    expect(candidate.action).toContain("Check whether the legacy extraction missed this relationship");
  });

  it("summarizes legacy-only edges as unbacked review candidates", () => {
    const candidate = buildGraphReviewCandidate(legacyOnlyEdge, "legacy-only", claims, spans);

    expect(candidate.status).toBe("Legacy graph only");
    expect(candidate.evidence).toBe("No validated claim evidence is linked to this edge yet.");
    expect(candidate.action).toContain("Find source evidence or leave it out of claim-promoted graph output");
  });
});
