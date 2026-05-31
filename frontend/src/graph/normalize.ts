import type { CanvasPayload, GraphLink, GraphNode, NormalizedGraph, RawFragility, RawIssue, RiskKind } from "../api/types";

export function issueScore(issue: Pick<RawIssue, "severity" | "probability">): number {
  const severity = Number(issue.severity || 0);
  const probability = Number(issue.probability || 0);
  return severity * probability || severity || probability || 0;
}

function linkId(source: string, target: string, text: string, riskKind: RiskKind, index: number): string {
  return `${riskKind}:${index}:${source}:${target}:${text}`.replace(/[^A-Za-z0-9:_-]/g, "_");
}

function toRiskLink(issue: RawIssue, index: number, riskKind: "structural" | "timeline"): GraphLink {
  return {
    id: linkId(issue.source, issue.target, issue.diamond || "", riskKind, index),
    source: issue.source,
    target: issue.target,
    relationship: riskKind === "timeline" ? "chronological friction" : "structural friction",
    diamond: issue.diamond || "",
    severity: issue.severity,
    probability: issue.probability,
    riskKind,
    riskScore: issueScore(issue),
  };
}

export function normalizeCanvasPayload(payload: CanvasPayload): NormalizedGraph {
  const rawNodes = payload.nodes ?? [];
  const rawEdges = payload.edges ?? [];
  const structural = payload.friction_lines ?? [];
  const timeline = payload.chronological_friction_lines ?? [];
  const fragility = payload.fragility_lines ?? [];
  const nodeIds = new Set(rawNodes.map((node) => node.id));

  const structuralLinks = structural.map((issue, index) => toRiskLink(issue, index, "structural"));
  const timelineLinks = timeline.map((issue, index) => toRiskLink(issue, index, "timeline"));
  const highRiskNodeIds = new Set<string>();
  const highRiskIssues = [...structuralLinks, ...timelineLinks].filter((link) => link.riskScore >= 12 || Number(link.severity || 0) >= 4);
  highRiskIssues.forEach((link) => {
    highRiskNodeIds.add(link.source);
    highRiskNodeIds.add(link.target);
  });
  const structuralNodeIds = new Set(structural.flatMap((issue) => [issue.source, issue.target]));
  const timelineNodeIds = new Set(timeline.flatMap((issue) => [issue.source, issue.target]));
  const fragilityNodeIds = new Set(fragility.map((item) => item.hub_node_id));

  const nodes: GraphNode[] = rawNodes.map((node) => {
    let riskKind: RiskKind = "standard";
    if (highRiskNodeIds.has(node.id)) riskKind = "high";
    else if (fragilityNodeIds.has(node.id)) riskKind = "fragility";
    else if (timelineNodeIds.has(node.id)) riskKind = "timeline";
    else if (structuralNodeIds.has(node.id)) riskKind = "structural";
    return {
      ...node,
      name: node.name || node.id,
      riskKind,
      riskScore: riskKind === "high" ? 16 : riskKind === "fragility" ? 10 : riskKind === "timeline" ? 8 : riskKind === "structural" ? 6 : 0,
    };
  });

  const standardLinks: GraphLink[] = rawEdges
    .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
    .map((edge, index) => ({
      id: linkId(edge.source, edge.target, edge.relationship || "", "standard", index),
      source: edge.source,
      target: edge.target,
      relationship: edge.relationship || "related",
      diamond: "",
      riskKind: "standard",
      riskScore: 0,
    }));

  const riskLinks = [...structuralLinks, ...timelineLinks].filter((link) => nodeIds.has(link.source) && nodeIds.has(link.target));
  const topRisks: Array<GraphLink | RawFragility> = [...riskLinks, ...fragility].sort((a, b) => {
    const scoreA = "riskScore" in a ? a.riskScore : Number(a.dependency_count || 0);
    const scoreB = "riskScore" in b ? b.riskScore : Number(b.dependency_count || 0);
    return scoreB - scoreA;
  });

  return {
    nodes,
    links: [...standardLinks, ...riskLinks],
    metrics: {
      nodes: nodes.length,
      edges: rawEdges.length,
      structuralConflicts: structural.length,
      timelineConflicts: timeline.length,
      fragilityPoints: fragility.length,
      highRiskIssues: highRiskIssues.length,
    },
    topRisks,
  };
}
