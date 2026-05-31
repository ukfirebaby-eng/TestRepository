import { describe, expect, it } from "vitest";
import type { NormalizedGraph } from "../api/types";
import { findReportGraphLink, findReportGraphNode, riskMatrixBuckets } from "./operational";

const graph: NormalizedGraph = {
  nodes: [
    { id: "a", name: "Alpha", riskKind: "high", riskScore: 16 },
    { id: "b", name: "Beta", riskKind: "timeline", riskScore: 8 },
  ],
  links: [
    { id: "timeline-1", source: "a", target: "b", relationship: "chronological friction", diamond: "Overlap", riskKind: "timeline", riskScore: 16 },
  ],
  metrics: { nodes: 2, edges: 1, structuralConflicts: 0, timelineConflicts: 1, fragilityPoints: 0, highRiskIssues: 1 },
  topRisks: [],
};

describe("operational report helpers", () => {
  it("matches report rows to graph links and nodes", () => {
    expect(findReportGraphLink(graph, { source: "a", target: "b", analysis: "Overlap", type: "chronological" })?.id).toBe("timeline-1");
    expect(findReportGraphNode(graph, { id: "a", name: "Alpha", dependency_count: 4 })?.id).toBe("a");
  });

  it("groups risk matrix rows by probability and severity", () => {
    const buckets = riskMatrixBuckets([
      { type: "structural", source: "a", target: "b", analysis: "One", severity: 4, probability: 5 },
      { type: "chronological", source: "b", target: "a", analysis: "Two", severity: 4, probability: 5 },
    ]);

    expect(buckets.get("5:4")).toHaveLength(2);
  });
});
