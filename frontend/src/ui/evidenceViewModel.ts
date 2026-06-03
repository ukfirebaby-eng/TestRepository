type EvidenceSection = {
  title: "What this is" | "Why it matters" | "Recommended action" | "Supporting graph evidence";
  body: string;
};

type PlainEnglish = {
  heading: string;
  meaning: string;
  impact: string;
  scoreMeaning: string;
  actions: string[];
};

type RiskFinding = {
  title?: string;
  risk_type?: string;
  affected_entity?: string;
  blocked_work?: string;
  blocking_condition?: string;
  evidence_summary?: string;
  why_it_matters?: string;
  recommended_action?: string;
  confidence?: number | string;
  confidence_score?: number | string;
  confidence_level?: string;
  confidence_factors?: {
    model_confidence?: number;
    evidence_completeness?: number;
    graph_specificity?: number;
    risk_score_availability?: number;
    claim_provenance_strength?: number;
  };
  claim_ids?: string[];
  evidence_span_ids?: string[];
  claim_validation_status?: string;
  graph_agreement?: string;
  assumptions?: string[];
};

type LinkInput = {
  selectionType: "link";
  title: string;
  riskKind: string;
  riskScore?: number | string;
  severity?: number | string;
  probability?: number | string;
  sourceName: string;
  targetName: string;
  isSelfReferential?: boolean;
  finding?: RiskFinding;
  plainEnglish: PlainEnglish;
  analysis?: string;
};

type NodeConnectionInput = {
  nodeName: string;
  relationship: string;
  direction: "incoming" | "outgoing";
};

type NodeInput = {
  selectionType: "node";
  title: string;
  label?: string;
  riskKind: string;
  riskScore?: number | string;
  connections?: NodeConnectionInput[];
  fragilityInsight?: string;
};

export type EvidenceViewModel = {
  heading: string;
  subheading: string;
  badges: string[];
  sections: EvidenceSection[];
};

function hasValue(value: unknown): value is string | number {
  return value !== undefined && value !== null && String(value).trim() !== "";
}

function scoreBadges(input: { riskKind: string; riskScore?: number | string; severity?: number | string; probability?: number | string }): string[] {
  return [
    input.riskKind,
    hasValue(input.riskScore) ? `Risk score ${input.riskScore}` : "",
    hasValue(input.severity) ? `Severity ${input.severity}` : "",
    hasValue(input.probability) ? `Probability ${input.probability}` : "",
  ].filter(Boolean);
}

function confidenceBadge(finding?: RiskFinding): string {
  if (!finding || !hasValue(finding.confidence_score)) return "";
  const score = Number(finding.confidence_score);
  const scoreText = Number.isFinite(score) ? `${Math.round(score * 100)}%` : String(finding.confidence_score);
  const level = finding.confidence_level ? `${sentenceCase(finding.confidence_level)} ` : "";
  return `${level}confidence ${scoreText}`;
}

function sentenceCase(value: string): string {
  const trimmed = value.trim();
  return trimmed ? `${trimmed[0].toUpperCase()}${trimmed.slice(1)}` : trimmed;
}

function plural(count: number, singular: string, pluralValue = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : pluralValue}`;
}

function claimSupportText(finding?: RiskFinding): string {
  if (!finding) return "";
  const claimCount = finding.claim_ids?.length || 0;
  const spanCount = finding.evidence_span_ids?.length || 0;
  if (!claimCount && !spanCount) return "";
  const validation = finding.claim_validation_status?.trim().toLowerCase();
  const claimLabel = validation === "passed" || validation === "validated" ? "validated claim" : "claim";
  return `Claim support: ${plural(claimCount, claimLabel)}; ${plural(spanCount, "evidence span")}.`;
}

export function buildEvidenceViewModel(input: LinkInput | NodeInput): EvidenceViewModel {
  if (input.selectionType === "link") {
    const findingType = input.finding?.risk_type ? `${sentenceCase(input.finding.risk_type)} risk` : "";
    const findingEntity = input.finding?.affected_entity || "";
    const subheading = input.finding && findingEntity
      ? `${findingType || "Risk"} in ${findingEntity}`
      : input.isSelfReferential
      ? `Programme-level conflict in ${input.sourceName}`
      : `${input.sourceName} -> ${input.targetName}`;
    const evidenceBody = input.finding
      ? [
          input.finding.blocked_work ? `Blocked work: ${input.finding.blocked_work}.` : "",
          input.finding.blocking_condition ? `Blocking condition: ${input.finding.blocking_condition}.` : "",
          claimSupportText(input.finding),
          input.finding.assumptions?.length ? `Assumptions: ${input.finding.assumptions.join("; ")}.` : "",
        ].filter(Boolean).join(" ") || "Structured finding metadata is available for this risk."
      : input.isSelfReferential
      ? `The graph has this risk attached to ${input.sourceName} as a programme-level evidence item. Use the recommendation text to identify the real underlying milestone, approval, or blocker.`
      : `${input.sourceName} connects to ${input.targetName} through ${input.title}.`;

    return {
      heading: input.plainEnglish.heading || input.title,
      subheading,
      badges: [...scoreBadges(input), confidenceBadge(input.finding)].filter(Boolean),
      sections: [
        { title: "What this is", body: input.plainEnglish.meaning },
        { title: "Why it matters", body: `${input.plainEnglish.impact} ${input.plainEnglish.scoreMeaning}`.trim() },
        { title: "Recommended action", body: input.plainEnglish.actions.join(" ") || input.analysis || "Review and correct the highlighted dependency." },
        { title: "Supporting graph evidence", body: evidenceBody },
      ],
    };
  }

  const connections = input.connections || [];
  const connectionText = connections.length
    ? connections.map((connection) => `${connection.nodeName} (${connection.relationship})`).join("; ")
    : "No direct graph connections are currently highlighted.";

  return {
    heading: input.title,
    subheading: input.label || input.riskKind,
    badges: scoreBadges(input),
    sections: [
      { title: "What this is", body: `${input.title} is a ${input.label || input.riskKind} node in the analysed graph.` },
      { title: "Why it matters", body: input.fragilityInsight || "This node matters because it sits inside the selected dependency context." },
      { title: "Recommended action", body: "Review ownership, dependency readiness, and mitigation options for this node." },
      { title: "Supporting graph evidence", body: connectionText },
    ],
  };
}
