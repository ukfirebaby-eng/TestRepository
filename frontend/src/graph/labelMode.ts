import type { GraphLink, GraphNode } from "../api/types";
import { nodeMatchesLens, type RiskLens } from "./lenses";
import type { GraphSelection } from "./selection";

export type LabelMode = "top-risks" | "selected-neighbors" | "none";

export function getVisibleLabelNodes(
  nodes: GraphNode[],
  links: GraphLink[],
  selection: GraphSelection,
  lens: RiskLens,
  mode: LabelMode,
): GraphNode[] {
  if (mode === "none") return [];

  const sorted = [...nodes]
    .filter((node) => nodeMatchesLens(node, lens))
    .sort((a, b) => b.riskScore - a.riskScore || a.name.localeCompare(b.name));

  if (mode === "top-risks" || selection.type === "none") return sorted.slice(0, 7);

  const selectedIds = new Set<string>();
  if (selection.type === "node") {
    selectedIds.add(selection.id);
  } else {
    const selectedLink = links.find((link) => link.id === selection.id);
    if (selectedLink) {
      selectedIds.add(selectedLink.source);
      selectedIds.add(selectedLink.target);
    }
  }

  const seedIds = new Set(selectedIds);
  links.forEach((link) => {
    if (seedIds.has(link.source)) selectedIds.add(link.target);
    if (seedIds.has(link.target)) selectedIds.add(link.source);
  });

  return sorted.filter((node) => selectedIds.has(node.id)).slice(0, 9);
}
