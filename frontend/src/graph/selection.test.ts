import { describe, expect, it } from "vitest";
import { isAttentionItemSelected, selectionReducer } from "./selection";

describe("selectionReducer", () => {
  it("tracks selected graph nodes and links", () => {
    expect(selectionReducer({ type: "none" }, { type: "select-node", id: "n1" })).toEqual({ type: "node", id: "n1" });
    expect(selectionReducer({ type: "node", id: "n1" }, { type: "select-link", id: "l1" })).toEqual({ type: "link", id: "l1" });
    expect(selectionReducer({ type: "link", id: "l1" }, { type: "clear" })).toEqual({ type: "none" });
  });

  it("matches critical attention risks to the active graph selection", () => {
    expect(isAttentionItemSelected({ id: "risk-1", source: "a", target: "b", relationship: "blocks", diamond: "Conflict", riskKind: "structural", riskScore: 8 }, { type: "link", id: "risk-1" })).toBe(true);
    expect(isAttentionItemSelected({ hub_node_id: "hub-1", insight: "Fragile hub" }, { type: "node", id: "hub-1" })).toBe(true);
    expect(isAttentionItemSelected({ hub_node_id: "hub-1", insight: "Fragile hub" }, { type: "link", id: "risk-1" })).toBe(false);
  });
});
