import { describe, expect, it } from "vitest";
import type { GraphLink, GraphNode } from "../api/types";
import { getVisibleLabelNodes } from "./labelMode";

const nodes: GraphNode[] = [
  { id: "a", name: "Alpha", riskKind: "high", riskScore: 16 },
  { id: "b", name: "Beta", riskKind: "timeline", riskScore: 8 },
  { id: "c", name: "Gamma", riskKind: "standard", riskScore: 0 },
];

const links: GraphLink[] = [
  { id: "ab", source: "a", target: "b", relationship: "depends", diamond: "", riskKind: "standard", riskScore: 0 },
  { id: "bc", source: "b", target: "c", relationship: "depends", diamond: "", riskKind: "standard", riskScore: 0 },
];

describe("getVisibleLabelNodes", () => {
  it("shows top risk labels by default", () => {
    expect(getVisibleLabelNodes(nodes, links, { type: "none" }, "overview", "top-risks").map((node) => node.id)).toEqual(["a", "b", "c"]);
  });

  it("can restrict labels to selected node and immediate neighbours", () => {
    expect(getVisibleLabelNodes(nodes, links, { type: "node", id: "b" }, "overview", "selected-neighbors").map((node) => node.id)).toEqual(["a", "b", "c"]);
    expect(getVisibleLabelNodes(nodes, links, { type: "node", id: "a" }, "overview", "selected-neighbors").map((node) => node.id)).toEqual(["a", "b"]);
  });

  it("can hide labels entirely", () => {
    expect(getVisibleLabelNodes(nodes, links, { type: "node", id: "b" }, "overview", "none")).toEqual([]);
  });
});
