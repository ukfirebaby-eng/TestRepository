import { describe, expect, it } from "vitest";
import { linkMatchesLens, nodeMatchesLens } from "./lenses";
import type { GraphLink, GraphNode } from "../api/types";

const node: GraphNode = { id: "a", name: "Alpha", riskKind: "structural", riskScore: 6 };
const link: GraphLink = {
  id: "l",
  source: "a",
  target: "b",
  relationship: "risk",
  diamond: "issue",
  riskKind: "timeline",
  riskScore: 16,
};

describe("risk lenses", () => {
  it("matches overview broadly and specific lenses narrowly", () => {
    expect(nodeMatchesLens(node, "overview")).toBe(true);
    expect(nodeMatchesLens(node, "structural")).toBe(true);
    expect(nodeMatchesLens(node, "timeline")).toBe(false);
    expect(linkMatchesLens(link, "timeline")).toBe(true);
    expect(linkMatchesLens(link, "high-risk")).toBe(true);
  });
});
