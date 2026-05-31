import type { BottleneckItem, FrictionQueueItem, GraphLink, GraphNode, NormalizedGraph, RiskMatrixItem, ScheduleCollapseItem } from "../api/types";

export type ReportLinkRow = FrictionQueueItem | RiskMatrixItem | ScheduleCollapseItem;

export function findReportGraphLink(graph: NormalizedGraph, row: ReportLinkRow): GraphLink | null {
  if ("source" in row && "target" in row) {
    const analysis = "analysis" in row ? row.analysis : row.diamond;
    const riskKind = row.type === "chronological" ? "timeline" : "structural";
    return graph.links.find((link) => (
      link.source === row.source
      && link.target === row.target
      && link.riskKind === riskKind
      && (!analysis || link.diamond === analysis)
    )) || null;
  }

  return graph.links.find((link) => link.riskKind === "timeline" && link.diamond === row.analysis) || null;
}

export function findReportGraphNode(graph: NormalizedGraph, row: BottleneckItem): GraphNode | null {
  return graph.nodes.find((node) => node.id === row.id) || null;
}

export function riskMatrixBuckets(rows: RiskMatrixItem[]): Map<string, RiskMatrixItem[]> {
  const buckets = new Map<string, RiskMatrixItem[]>();
  rows.forEach((row) => {
    const severity = Math.max(1, Math.min(5, Number(row.severity || 1)));
    const probability = Math.max(1, Math.min(5, Number(row.probability || 1)));
    const key = `${probability}:${severity}`;
    buckets.set(key, [...(buckets.get(key) || []), row]);
  });
  return buckets;
}
