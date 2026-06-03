import type { GraphLink, GraphNode } from "../api/types";

export type RiskConcentrationSummary = {
  primaryNode: GraphNode | null;
  highRiskLinkCount: number;
  caption: string;
};

export function summarizeRiskConcentration(nodes: GraphNode[], links: GraphLink[]): RiskConcentrationSummary {
  const primaryNode = [...nodes].sort((a, b) => b.riskScore - a.riskScore)[0] || null;
  const highRiskLinkCount = links.filter((link) => link.riskScore >= 12 || link.riskKind === "high").length;
  const caption = primaryNode
    ? `${highRiskLinkCount.toLocaleString()} high-risk paths concentrate around ${primaryNode.name}.`
    : "No risk concentration available.";

  return { primaryNode, highRiskLinkCount, caption };
}
