import type { GraphLink, GraphNode, RiskKind } from "../api/types";

export type RiskLens = "overview" | "structural" | "fragility" | "timeline" | "high-risk";

export function nodeMatchesLens(node: GraphNode, lens: RiskLens): boolean {
  if (lens === "overview") return true;
  if (lens === "high-risk") return node.riskKind === "high";
  return node.riskKind === (lens as RiskKind);
}

export function linkMatchesLens(link: GraphLink, lens: RiskLens): boolean {
  if (lens === "overview") return true;
  if (lens === "high-risk") return link.riskScore >= 12 || Number(link.severity || 0) >= 4;
  return link.riskKind === (lens as RiskKind);
}

export function riskColor(riskKind: RiskKind): string {
  if (riskKind === "high") return "#ff5a68";
  if (riskKind === "structural") return "#e36b5d";
  if (riskKind === "timeline") return "#e7a84a";
  if (riskKind === "fragility") return "#f0c85a";
  return "#79c7e8";
}
