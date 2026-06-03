import { describe, expect, it } from "vitest";
import type { GraphLink, GraphNode } from "../api/types";
import { summarizeRiskConcentration } from "./riskConcentration";

const nodes: GraphNode[] = [
  { id: "a", name: "Authentication", riskKind: "fragility", riskScore: 16 },
  { id: "b", name: "Portal", riskKind: "standard", riskScore: 2 },
  { id: "c", name: "Migration", riskKind: "high", riskScore: 18 },
];

const links: GraphLink[] = [
  { id: "l1", source: "a", target: "b", relationship: "blocks", diamond: "Risk", riskKind: "high", riskScore: 16 },
  { id: "l2", source: "b", target: "c", relationship: "depends", diamond: "Risk", riskKind: "structural", riskScore: 12 },
];

describe("summarizeRiskConcentration", () => {
  it("identifies concentration around high-risk nodes and links", () => {
    const summary = summarizeRiskConcentration(nodes, links);

    expect(summary.primaryNode?.name).toBe("Migration");
    expect(summary.highRiskLinkCount).toBe(2);
    expect(summary.caption).toContain("2 high-risk paths");
  });
});
