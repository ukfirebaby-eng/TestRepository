import type { GraphLink, GraphNode } from "../api/types";
import type { GraphSelection } from "./selection";

export type FocusVisibilityState = "normal" | "selected" | "context" | "dimmed";

export type FocusVisibility = {
  hasFocus: boolean;
  nodeState: (nodeId: string) => FocusVisibilityState;
  linkState: (linkId: string) => FocusVisibilityState;
};

function incident(link: GraphLink, nodeId: string): boolean {
  return link.source === nodeId || link.target === nodeId;
}

export function buildFocusVisibility(nodes: GraphNode[], links: GraphLink[], selection: GraphSelection): FocusVisibility {
  if (selection.type === "none") {
    return {
      hasFocus: false,
      nodeState: () => "normal",
      linkState: () => "normal",
    };
  }

  const nodeStates = new Map<string, FocusVisibilityState>(nodes.map((node) => [node.id, "dimmed"]));
  const linkStates = new Map<string, FocusVisibilityState>(links.map((link) => [link.id, "dimmed"]));

  if (selection.type === "node") {
    nodeStates.set(selection.id, "selected");
    links.forEach((link) => {
      if (!incident(link, selection.id)) return;
      linkStates.set(link.id, "context");
      nodeStates.set(link.source, link.source === selection.id ? "selected" : "context");
      nodeStates.set(link.target, link.target === selection.id ? "selected" : "context");
    });
  }

  if (selection.type === "link") {
    const selectedLink = links.find((link) => link.id === selection.id);
    if (selectedLink) {
      linkStates.set(selectedLink.id, "selected");
      nodeStates.set(selectedLink.source, "selected");
      nodeStates.set(selectedLink.target, "selected");
      links.forEach((link) => {
        const touchesEndpoint = incident(link, selectedLink.source) || incident(link, selectedLink.target);
        if (!touchesEndpoint || link.id === selectedLink.id) return;
        linkStates.set(link.id, "context");
        if (nodeStates.get(link.source) !== "selected") nodeStates.set(link.source, "context");
        if (nodeStates.get(link.target) !== "selected") nodeStates.set(link.target, "context");
      });
    }
  }

  return {
    hasFocus: true,
    nodeState: (nodeId) => nodeStates.get(nodeId) || "dimmed",
    linkState: (linkId) => linkStates.get(linkId) || "dimmed",
  };
}
