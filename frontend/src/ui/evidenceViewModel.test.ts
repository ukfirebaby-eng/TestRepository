import { describe, expect, it } from "vitest";
import { buildEvidenceViewModel } from "./evidenceViewModel";

describe("buildEvidenceViewModel", () => {
  it("summarizes selected risk links as an action-oriented evidence card", () => {
    const model = buildEvidenceViewModel({
      selectionType: "link",
      title: "predecessor",
      riskKind: "structural",
      riskScore: 16,
      severity: 4,
      probability: 4,
      sourceName: "Cloud Migration",
      targetName: "Dress rehearsal",
      plainEnglish: {
        heading: "Dependency conflict",
        meaning: "The plan is trying to rehearse before the required security dependency is complete.",
        impact: "This can create rework, delay, or compliance failure.",
        scoreMeaning: "Severity 4 and probability 4 make this a high-priority issue.",
        actions: ["Move migration after certification.", "Escalate to the steering board."],
      },
      analysis: "Escalate and correct the dependency chain.",
    });

    expect(model.heading).toBe("Dependency conflict");
    expect(model.badges).toContain("Risk score 16");
    expect(model.sections.map((section) => section.title)).toEqual([
      "What this is",
      "Why it matters",
      "Recommended action",
      "Supporting graph evidence",
    ]);
    expect(model.sections[2].body).toContain("Move migration after certification.");
  });

  it("summarizes self-referential risk links without a duplicate from-to path", () => {
    const model = buildEvidenceViewModel({
      selectionType: "link",
      title: "structural friction",
      riskKind: "structural",
      riskScore: 16,
      severity: 4,
      probability: 4,
      sourceName: "Orion Payments Modernisation Programme",
      targetName: "Orion Payments Modernisation Programme",
      isSelfReferential: true,
      plainEnglish: {
        heading: "High-risk dependency conflict",
        meaning: "This is a programme-level structural conflict inside Orion Payments Modernisation Programme.",
        impact: "The programme could be delayed.",
        scoreMeaning: "Severity 4 and probability 4 make this a high-priority issue.",
        actions: ["Make the testing evidence a hard entry criterion."],
      },
      analysis: "Correct the internal dependency sequence.",
    });

    expect(model.subheading).toBe("Programme-level conflict in Orion Payments Modernisation Programme");
    expect(model.subheading).not.toContain("->");
    expect(model.sections[3].body).toContain("The graph has this risk attached to Orion Payments Modernisation Programme as a programme-level evidence item");
  });

  it("uses structured finding fields for supporting evidence when available", () => {
    const model = buildEvidenceViewModel({
      selectionType: "link",
      title: "structural friction",
      riskKind: "structural",
      riskScore: 16,
      severity: 4,
      probability: 4,
      sourceName: "programme",
      targetName: "programme",
      isSelfReferential: true,
      finding: {
        title: "Audit evidence starts before source data approval",
        risk_type: "evidence readiness",
        affected_entity: "Orion Payments Modernisation Programme",
        blocked_work: "board sign-off",
        blocking_condition: "approved transaction history",
        evidence_summary: "Evidence is produced too early.",
        why_it_matters: "Sign-off could rely on invalid evidence.",
        recommended_action: "Move evidence production.",
        confidence: 0.91,
        confidence_score: 0.91,
        confidence_level: "high",
        assumptions: [],
      },
      plainEnglish: {
        heading: "Audit evidence starts before source data approval",
        meaning: "Evidence is produced too early.",
        impact: "Sign-off could rely on invalid evidence.",
        scoreMeaning: "Confidence 91%.",
        actions: ["Move evidence production."],
      },
    });

    expect(model.subheading).toBe("Evidence readiness risk in Orion Payments Modernisation Programme");
    expect(model.badges).toContain("High confidence 91%");
    expect(model.sections[3].body).toContain("Blocked work: board sign-off.");
    expect(model.sections[3].body).toContain("Blocking condition: approved transaction history.");
  });

  it("describes claim provenance in selected risk evidence", () => {
    const model = buildEvidenceViewModel({
      selectionType: "link",
      title: "structural friction",
      riskKind: "structural",
      riskScore: 16,
      severity: 4,
      probability: 4,
      sourceName: "programme",
      targetName: "programme",
      isSelfReferential: true,
      finding: {
        title: "Audit evidence starts before source data approval",
        risk_type: "evidence readiness",
        affected_entity: "Orion Payments Modernisation Programme",
        blocked_work: "board sign-off",
        blocking_condition: "approved transaction history",
        evidence_summary: "Evidence is produced too early.",
        why_it_matters: "Sign-off could rely on invalid evidence.",
        recommended_action: "Move evidence production.",
        confidence_score: 0.96,
        confidence_level: "high",
        claim_ids: ["claim_1"],
        evidence_span_ids: ["span_1", "span_2"],
        claim_validation_status: "passed",
      },
      plainEnglish: {
        heading: "Audit evidence starts before source data approval",
        meaning: "Evidence is produced too early.",
        impact: "Sign-off could rely on invalid evidence.",
        scoreMeaning: "Confidence 96%.",
        actions: ["Move evidence production."],
      },
    });

    expect(model.badges).toContain("High confidence 96%");
    expect(model.badges).toContain("Validated claim-backed");
    expect(model.sections[3].body).toContain("Claim support: 1 validated claim; 2 evidence spans.");
  });

  it("marks legacy-only graph risks for review", () => {
    const model = buildEvidenceViewModel({
      selectionType: "link",
      title: "structural friction",
      riskKind: "structural",
      riskScore: 12,
      severity: 3,
      probability: 4,
      sourceName: "Legacy migration",
      targetName: "Security approval",
      finding: {
        title: "Legacy graph-only dependency",
        risk_type: "dependency",
        affected_entity: "Legacy migration",
        blocked_work: "launch",
        blocking_condition: "security approval",
        evidence_summary: "The edge exists in the legacy graph but has no matching validated claim.",
        why_it_matters: "It needs review before being treated as a confirmed blocker.",
        recommended_action: "Review source evidence.",
        confidence_score: 0.62,
        confidence_level: "medium",
        graph_agreement: "legacy_only",
      },
      plainEnglish: {
        heading: "Legacy graph-only dependency",
        meaning: "This risk came from the legacy graph extraction path.",
        impact: "It may still be valid, but it has weaker provenance.",
        scoreMeaning: "Medium confidence.",
        actions: ["Review source evidence."],
      },
    });

    expect(model.badges).toContain("Legacy-only graph risk");
    expect(model.sections[3].body).toContain("Graph agreement: legacy-only, not yet claim-backed.");
  });

  it("summarizes selected nodes with connection evidence", () => {
    const model = buildEvidenceViewModel({
      selectionType: "node",
      title: "Central Authentication Service",
      label: "service",
      riskKind: "fragility",
      riskScore: 12,
      connections: [
        { nodeName: "API Gateway", relationship: "depends on", direction: "outgoing" },
        { nodeName: "Customer Portal", relationship: "supports", direction: "incoming" },
      ],
      fragilityInsight: "Authentication is a single point of failure.",
    });

    expect(model.heading).toBe("Central Authentication Service");
    expect(model.sections[0].body).toContain("service");
    expect(model.sections[1].body).toContain("single point of failure");
    expect(model.sections[3].body).toContain("API Gateway");
  });
});
