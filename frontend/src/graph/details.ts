import type { GraphLink, GraphNode, NormalizedGraph, RawFragility, RawRiskFinding, RiskKind } from "../api/types";

export type NodeConnection = {
  direction: "incoming" | "outgoing";
  relationship: string;
  nodeName: string;
  nodeId: string;
};

export type NodeDetail = {
  id: string;
  title: string;
  label: string;
  riskKind: RiskKind;
  riskScore: number;
  connections: NodeConnection[];
  fragility?: RawFragility;
};

export type LinkDetail = {
  id: string;
  riskKind: RiskKind;
  riskScore: number;
  severity?: number | string;
  probability?: number | string;
  sourceName: string;
  targetName: string;
  isSelfReferential: boolean;
  finding?: RawRiskFinding;
  relationship: string;
  analysis: string;
  plainEnglish: PlainEnglishRiskExplanation;
};

export type PlainEnglishRiskExplanation = {
  heading: string;
  meaning: string;
  impact: string;
  scoreMeaning: string;
  actions: string[];
};

function nodeName(graph: NormalizedGraph, nodeId: string): string {
  return graph.nodes.find((node) => node.id === nodeId)?.name || nodeId;
}

function numeric(value: number | string | undefined): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function sentenceCase(value: string): string {
  const trimmed = value.trim();
  return trimmed ? `${trimmed[0].toUpperCase()}${trimmed.slice(1)}` : trimmed;
}

function riskHeading(link: GraphLink): string {
  const severity = numeric(link.severity);
  const probability = numeric(link.probability);
  if (link.riskScore >= 16 || ((severity || 0) >= 4 && (probability || 0) >= 4)) {
    return link.riskKind === "timeline" ? "High-risk schedule conflict" : "High-risk dependency conflict";
  }
  if (link.riskKind === "timeline") return "Schedule conflict";
  if (link.riskKind === "structural") return "Dependency conflict";
  return "Selected risk path";
}

function riskMeaning(link: GraphLink, sourceName: string, targetName: string, isSelfReferential: boolean): string {
  if (isSelfReferential) {
    if (link.riskKind === "timeline") {
      return `This means the app found a programme-level timing conflict inside ${sourceName}. The graph could not isolate two distinct milestones, so read this as an internal schedule or sequencing problem, not as ${sourceName} depending on itself.`;
    }
    if (link.riskKind === "structural") {
      return `This means the app found a programme-level structural conflict inside ${sourceName}. The graph could not isolate two distinct endpoints, so read this as an internal prerequisite, approval, capability, or blocker problem, not as ${sourceName} depending on itself.`;
    }
    return `This means the app found a programme-level risk attached to ${sourceName}. The graph could not isolate two distinct endpoints for this evidence item.`;
  }
  if (link.riskKind === "timeline") {
    return `This means the app found a timing conflict around the ${link.relationship} relationship from ${sourceName} to ${targetName}. The plan may be asking ${targetName} to start before ${sourceName} is realistically complete.`;
  }
  if (link.riskKind === "structural") {
    return `This means the app found a structural dependency conflict around the ${link.relationship} relationship from ${sourceName} to ${targetName}. The plan may depend on a prerequisite, approval, capability, or blocker that is not safely resolved.`;
  }
  return `This means the app found a risk path from ${sourceName} to ${targetName} through the ${link.relationship} relationship.`;
}

function riskImpact(link: GraphLink, targetName: string, isSelfReferential: boolean): string {
  const severity = numeric(link.severity);
  const probability = numeric(link.probability);
  const highImpact = severity !== null && severity >= 4;
  const likely = probability !== null && probability >= 4;
  if (isSelfReferential && highImpact && likely) {
    return `If left unresolved, this is likely to happen and would have a serious impact. The programme could be delayed, blocked, or forced to proceed with unresolved delivery, compliance, or operational risk.`;
  }
  if (isSelfReferential) {
    return `This should be reviewed as a programme-level dependency issue so the underlying blocker can be assigned to a specific owner, milestone, or decision.`;
  }
  if (highImpact && likely) {
    return `If left unresolved, this is likely to happen and would have a serious impact. ${targetName} could be delayed, blocked, or forced to proceed with unresolved delivery, compliance, or operational risk.`;
  }
  if (highImpact) return `If this happens, the impact is serious even if the probability is lower. ${targetName} may need a management decision before work continues.`;
  if (likely) return `This looks likely enough to track actively. ${targetName} may be affected unless the dependency is clarified or removed.`;
  return `This should be reviewed to confirm whether the dependency is real and whether ${targetName} can proceed safely.`;
}

function scoreMeaning(link: GraphLink): string {
  const severity = link.severity ?? "n/a";
  const probability = link.probability ?? "n/a";
  const confidence = numeric(link.finding?.confidence);
  const confidenceText = confidence !== null ? ` Confidence ${Math.round(confidence * 100)}%.` : "";
  return `Severity ${severity} measures impact, Probability ${probability} measures likelihood, and Risk Score ${link.riskScore} combines them for prioritisation.${confidenceText}`;
}

function recommendedActions(link: GraphLink, targetName: string, isSelfReferential: boolean): string[] {
  const analysis = (link.diamond || "").replace(/\s+/g, " ").trim();
  const actionVerb = "(?:escalate|move|reschedule|negotiate|accelerate|adjust|obtain|confirm|delay|defer|resolve)";
  const actions = analysis
    .split(new RegExp(`(?:;|\\.\\s+|,\\s+(?:and\\/or|and|or)\\s+|,\\s+(?=${actionVerb}\\b))`, "i"))
    .map((clause) => clause.replace(/^(?:alternatively|instead),?\s+/i, "").trim())
    .filter((clause) => new RegExp(`^${actionVerb}\\b`, "i").test(clause))
    .map((clause) => sentenceCase(clause))
    .filter((action) => action.length > 12);

  if (!actions.length && analysis) actions.push(sentenceCase(analysis));
  if (link.riskKind !== "standard") {
    actions.push(isSelfReferential
      ? `Do not treat ${targetName} as ready until the internal blocker described above is resolved or explicitly accepted.`
      : `Do not proceed with ${targetName} until the blocker described above is resolved or explicitly accepted.`);
  }
  return Array.from(new Set(actions)).slice(0, 4);
}

function buildPlainEnglishRiskExplanation(link: GraphLink, sourceName: string, targetName: string, isSelfReferential: boolean): PlainEnglishRiskExplanation {
  if (link.finding) {
    const actions = [
      link.finding.recommended_action,
      ...(link.finding.assumptions?.length ? [`Assumptions: ${link.finding.assumptions.join("; ")}.`] : []),
    ].filter((action): action is string => Boolean(action && action.trim()));
    return {
      heading: link.finding.title || riskHeading(link),
      meaning: link.finding.evidence_summary || riskMeaning(link, sourceName, targetName, isSelfReferential),
      impact: link.finding.why_it_matters || riskImpact(link, targetName, isSelfReferential),
      scoreMeaning: scoreMeaning(link),
      actions: actions.length ? actions : recommendedActions(link, targetName, isSelfReferential),
    };
  }
  return {
    heading: riskHeading(link),
    meaning: riskMeaning(link, sourceName, targetName, isSelfReferential),
    impact: riskImpact(link, targetName, isSelfReferential),
    scoreMeaning: scoreMeaning(link),
    actions: recommendedActions(link, targetName, isSelfReferential),
  };
}

export function buildNodeDetail(graph: NormalizedGraph, nodeId: string): NodeDetail | null {
  const node = graph.nodes.find((item) => item.id === nodeId);
  if (!node) return null;

  const connections = graph.links
    .filter((link) => link.riskKind === "standard" && (link.source === nodeId || link.target === nodeId))
    .map<NodeConnection>((link) => {
      const outgoing = link.source === nodeId;
      const otherId = outgoing ? link.target : link.source;
      return {
        direction: outgoing ? "outgoing" : "incoming",
        relationship: link.relationship,
        nodeId: otherId,
        nodeName: nodeName(graph, otherId),
      };
    })
    .sort((a, b) => a.nodeName.localeCompare(b.nodeName));

  return {
    id: node.id,
    title: node.name,
    label: node.label || "node",
    riskKind: node.riskKind,
    riskScore: node.riskScore,
    connections,
    fragility: graph.topRisks.find((item): item is RawFragility => !("riskKind" in item) && item.hub_node_id === nodeId),
  };
}

export function buildLinkDetail(graph: NormalizedGraph, linkId: string): LinkDetail | null {
  const link = graph.links.find((item) => item.id === linkId);
  if (!link) return null;
  const sourceName = nodeName(graph, link.source);
  const targetName = nodeName(graph, link.target);
  const isSelfReferential = link.source === link.target || sourceName === targetName;
  return {
    id: link.id,
    riskKind: link.riskKind,
    riskScore: link.riskScore,
    severity: link.severity,
    probability: link.probability,
    sourceName,
    targetName,
    isSelfReferential,
    finding: link.finding,
    relationship: link.relationship,
    analysis: link.diamond || link.relationship,
    plainEnglish: buildPlainEnglishRiskExplanation(link, sourceName, targetName, isSelfReferential),
  };
}

export function searchNodes(graph: NormalizedGraph, query: string, limit = 8): GraphNode[] {
  const term = query.trim().toLowerCase();
  if (term.length < 2) return [];
  return graph.nodes
    .filter((node) => `${node.id} ${node.name} ${node.label || ""} ${node.riskKind}`.toLowerCase().includes(term))
    .sort((a, b) => b.riskScore - a.riskScore || a.name.localeCompare(b.name))
    .slice(0, limit);
}
