import type { GraphLink, RawFragility } from "../api/types";

export type GraphSelection =
  | { type: "none" }
  | { type: "node"; id: string }
  | { type: "link"; id: string };

export type SelectionAction =
  | { type: "select-node"; id: string }
  | { type: "select-link"; id: string }
  | { type: "clear" };

export function selectionReducer(_: GraphSelection, action: SelectionAction): GraphSelection {
  if (action.type === "select-node") return { type: "node", id: action.id };
  if (action.type === "select-link") return { type: "link", id: action.id };
  return { type: "none" };
}

function isGraphLink(item: GraphLink | RawFragility): item is GraphLink {
  return "riskKind" in item;
}

export function isAttentionItemSelected(item: GraphLink | RawFragility, selection: GraphSelection): boolean {
  if (isGraphLink(item)) return selection.type === "link" && selection.id === item.id;
  return selection.type === "node" && selection.id === item.hub_node_id;
}
