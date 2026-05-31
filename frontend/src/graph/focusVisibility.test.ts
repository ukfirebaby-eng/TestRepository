import { describe, expect, it } from "vitest";
import type { GraphLink, GraphNode } from "../api/types";
import { buildFocusVisibility } from "./focusVisibility";

const nodes = [
  { id: "a", name: "A", riskKind: "standard", riskScore: 0 },
  { id: "b", name: "B", riskKind: "standard", riskScore: 0 },
  { id: "c", name: "C", riskKind: "standard", riskScore: 0 },
  { id: "d", name: "D", riskKind: "standard", riskScore: 0 },
] satisfies GraphNode[];

const links = [
  { id: "ab", source: "a", target: "b", relationship: "feeds", diamond: "feeds", riskKind: "standard", riskScore: 0 },
  { id: "bc", source: "b", target: "c", relationship: "depends", diamond: "depends", riskKind: "structural", riskScore: 12 },
  { id: "cd", source: "c", target: "d", relationship: "blocks", diamond: "blocks", riskKind: "timeline", riskScore: 16 },
] satisfies GraphLink[];

describe("focus visibility", () => {
  it("leaves the full graph normal when nothing is selected", () => {
    const focus = buildFocusVisibility(nodes, links, { type: "none" });

    expect(focus.nodeState("a")).toBe("normal");
    expect(focus.linkState("ab")).toBe("normal");
    expect(focus.hasFocus).toBe(false);
  });

  it("selects a node, keeps direct neighbours contextual, and dims unrelated elements", () => {
    const focus = buildFocusVisibility(nodes, links, { type: "node", id: "b" });

    expect(focus.nodeState("b")).toBe("selected");
    expect(focus.nodeState("a")).toBe("context");
    expect(focus.nodeState("c")).toBe("context");
    expect(focus.nodeState("d")).toBe("dimmed");
    expect(focus.linkState("ab")).toBe("context");
    expect(focus.linkState("bc")).toBe("context");
    expect(focus.linkState("cd")).toBe("dimmed");
  });

  it("selects a link, keeps endpoint neighbourhood visible, and dims unrelated paths", () => {
    const focus = buildFocusVisibility(nodes, links, { type: "link", id: "bc" });

    expect(focus.linkState("bc")).toBe("selected");
    expect(focus.nodeState("b")).toBe("selected");
    expect(focus.nodeState("c")).toBe("selected");
    expect(focus.nodeState("a")).toBe("context");
    expect(focus.nodeState("d")).toBe("context");
    expect(focus.linkState("ab")).toBe("context");
    expect(focus.linkState("cd")).toBe("context");
  });
});
