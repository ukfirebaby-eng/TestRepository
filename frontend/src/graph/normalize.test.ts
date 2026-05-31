import { describe, expect, it } from "vitest";
import { normalizeCanvasPayload } from "./normalize";

describe("normalizeCanvasPayload", () => {
  it("merges standard edges and risk issues into a graph model", () => {
    const graph = normalizeCanvasPayload({
      nodes: [
        { id: "a", name: "Alpha" },
        { id: "b", name: "Beta" },
      ],
      edges: [{ source: "a", target: "b", relationship: "depends on" }],
      friction_lines: [{ source: "a", target: "b", diamond: "Conflict", severity: 4, probability: 4 }],
      chronological_friction_lines: [],
      fragility_lines: [{ hub_node_id: "a", dependency_count: 3, insight: "Hub" }],
    });

    expect(graph.nodes).toHaveLength(2);
    expect(graph.links).toHaveLength(2);
    expect(graph.metrics.highRiskIssues).toBe(1);
    expect(graph.nodes.find((node) => node.id === "a")?.riskKind).toBe("high");
  });
});
