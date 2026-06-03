import { describe, expect, it } from "vitest";
import { buildLinkDetail, buildNodeDetail, searchNodes } from "./details";
import { normalizeCanvasPayload } from "./normalize";

const graph = normalizeCanvasPayload({
  nodes: [
    { id: "auth", name: "Central Authentication Service", label: "system" },
    { id: "api", name: "API Gateway", label: "service" },
    { id: "portal", name: "Customer Portal", label: "application" },
  ],
  edges: [
    { source: "api", target: "auth", relationship: "validates tokens through" },
    { source: "portal", target: "api", relationship: "routes requests through" },
  ],
  friction_lines: [
    { source: "portal", target: "api", diamond: "Portal launch contradicts gateway readiness.", severity: 4, probability: 3 },
  ],
  chronological_friction_lines: [
    { source: "api", target: "auth", diamond: "Gateway starts before auth hardening completes.", severity: 5, probability: 4 },
  ],
  fragility_lines: [
    { hub_node_id: "auth", insight: "Authentication is a single point of failure.", dependency_count: 2, cascade_nodes: ["API Gateway", "Customer Portal"] },
  ],
});

describe("graph detail helpers", () => {
  it("builds node details with connections and fragility context", () => {
    const detail = buildNodeDetail(graph, "auth");

    expect(detail?.title).toBe("Central Authentication Service");
    expect(detail?.label).toBe("system");
    expect(detail?.connections).toEqual([
      { direction: "incoming", relationship: "validates tokens through", nodeName: "API Gateway", nodeId: "api" },
    ]);
    expect(detail?.fragility?.cascade_nodes).toContain("API Gateway");
  });

  it("builds risk link details with score, severity, probability, and analysis", () => {
    const link = graph.links.find((item) => item.riskKind === "timeline");
    const detail = buildLinkDetail(graph, link?.id || "");

    expect(detail?.riskKind).toBe("timeline");
    expect(detail?.riskScore).toBe(20);
    expect(detail?.severity).toBe(5);
    expect(detail?.probability).toBe(4);
    expect(detail?.sourceName).toBe("API Gateway");
    expect(detail?.targetName).toBe("Central Authentication Service");
    expect(detail?.analysis).toContain("Gateway starts before auth");
  });

  it("adds plain-English explanations for selected structural risks", () => {
    const structuralGraph = normalizeCanvasPayload({
      nodes: [
        { id: "predecessor", name: "predecessor", label: "dependency" },
        { id: "dress_rehearsal", name: "Dress rehearsal", label: "milestone" },
      ],
      edges: [],
      friction_lines: [
        {
          source: "predecessor",
          target: "dress_rehearsal",
          diamond: "Escalate the conflict to the Nexus Steering Board, move the Cloud Migration start date to after the earliest possible Security Certification (post-10 August 2026), and/or negotiate an accelerated penetration-test slot or provisional certification so the Network Infrastructure Upgrade is completed before the test and the Security Certification Body's block is lifted before migration begins.",
          severity: 4,
          probability: 4,
        },
      ],
    });
    const link = structuralGraph.links.find((item) => item.riskKind === "structural");
    const detail = buildLinkDetail(structuralGraph, link?.id || "");

    expect(detail?.plainEnglish.heading).toBe("High-risk dependency conflict");
    expect(detail?.plainEnglish.meaning).toContain("structural dependency conflict");
    expect(detail?.plainEnglish.impact).toContain("serious impact");
    expect(detail?.plainEnglish.scoreMeaning).toContain("Severity 4");
    expect(detail?.plainEnglish.scoreMeaning).toContain("Probability 4");
    expect(detail?.plainEnglish.actions).toEqual(expect.arrayContaining([
      expect.stringContaining("Escalate"),
      expect.stringContaining("Move"),
      expect.stringContaining("Do not proceed"),
    ]));
  });

  it("explains self-referential risk links as programme-level conflicts", () => {
    const selfLoopGraph = normalizeCanvasPayload({
      nodes: [
        { id: "orion_programme", name: "Orion Payments Modernisation Programme", label: "programme" },
      ],
      edges: [],
      friction_lines: [
        {
          source: "orion_programme",
          target: "orion_programme",
          diamond: "Make replicated-and-approved transaction history a hard entry criterion for testing.",
          severity: 4,
          probability: 4,
        },
      ],
    });
    const link = selfLoopGraph.links.find((item) => item.riskKind === "structural");
    const detail = buildLinkDetail(selfLoopGraph, link?.id || "");

    expect(detail?.isSelfReferential).toBe(true);
    expect(detail?.plainEnglish.meaning).toContain("programme-level structural conflict inside Orion Payments Modernisation Programme");
    expect(detail?.plainEnglish.meaning).not.toContain("from Orion Payments Modernisation Programme to Orion Payments Modernisation Programme");
    expect(detail?.plainEnglish.impact).toContain("The programme could be delayed");
  });

  it("prefers structured ingestion findings over inferred graph wording", () => {
    const findingGraph = normalizeCanvasPayload({
      nodes: [
        { id: "orion_programme", name: "Orion Payments Modernisation Programme", label: "programme" },
      ],
      edges: [],
      friction_lines: [
        {
          source: "orion_programme",
          target: "orion_programme",
          diamond: "Legacy mitigation text.",
          severity: 4,
          probability: 4,
          finding: {
            title: "Audit evidence starts before source data approval",
            risk_type: "evidence readiness",
            affected_entity: "Orion Payments Modernisation Programme",
            blocked_work: "board sign-off",
            blocking_condition: "approved transaction history",
            evidence_summary: "The plan generates audit evidence before transaction history is approved.",
            why_it_matters: "Board sign-off could be based on invalid evidence.",
            recommended_action: "Move evidence production after transaction history approval.",
            confidence: 0.91,
            assumptions: ["Transaction history approval is mandatory."],
          },
        },
      ],
    });
    const link = findingGraph.links.find((item) => item.riskKind === "structural");
    const detail = buildLinkDetail(findingGraph, link?.id || "");

    expect(detail?.plainEnglish.heading).toBe("Audit evidence starts before source data approval");
    expect(detail?.plainEnglish.meaning).toBe("The plan generates audit evidence before transaction history is approved.");
    expect(detail?.plainEnglish.impact).toBe("Board sign-off could be based on invalid evidence.");
    expect(detail?.plainEnglish.actions).toContain("Move evidence production after transaction history approval.");
    expect(detail?.plainEnglish.scoreMeaning).toContain("Confidence 91%");
  });

  it("searches nodes by name, label, and id", () => {
    expect(searchNodes(graph, "auth").map((node) => node.id)).toEqual(["auth"]);
    expect(searchNodes(graph, "application").map((node) => node.id)).toEqual(["portal"]);
    expect(searchNodes(graph, "api").map((node) => node.id)).toEqual(["api"]);
  });
});
