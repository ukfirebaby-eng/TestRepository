import { useEffect, useState } from "react";
import { deleteGeneratedReport, getGeneratedReport, streamGeneratedReport } from "../api/client";
import { finalPayloadForKind, generatedReportConfig, type GeneratedReportKind } from "../reports/generated";

type ReportState = {
  status: "checking" | "ready" | "generating" | "error";
  payload: unknown | null;
  message: string;
};

type Props = {
  documentId: string;
  documentName?: string;
  variant?: "rail" | "workspace";
};

const reportTabs: Array<{ kind: GeneratedReportKind; label: string }> = [
  { kind: "executive", label: "Executive Summary" },
  { kind: "narrative", label: "Narrative Report" },
  { kind: "simulation", label: "Risk Simulator" },
];

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? value as Record<string, unknown> : {};
}

function asArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(asRecord) : [];
}

function text(value: unknown, fallback = "Not available."): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function numberText(value: unknown): string | null {
  if (typeof value === "number" && Number.isFinite(value)) return value.toLocaleString();
  if (typeof value === "string" && value.trim()) return value;
  return null;
}

function snippet(value: unknown, fallback = "No summary available."): string {
  const raw = text(value, fallback);
  return raw.length > 220 ? `${raw.slice(0, 217)}...` : raw;
}

function formatDecimal(value: unknown): string | null {
  if (typeof value === "number" && Number.isFinite(value)) return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
  if (typeof value === "string" && value.trim()) return value;
  return null;
}

function daysText(value: unknown): string | null {
  const numeric = typeof value === "number" && Number.isFinite(value) ? value : null;
  if (numeric === null) return numberText(value);
  return `${numeric.toLocaleString()} days`;
}

function firstPresent(...values: unknown[]): unknown {
  return values.find((value) => value !== null && value !== undefined && !(typeof value === "string" && !value.trim()));
}

function positiveNumber(value: unknown): boolean {
  if (typeof value === "number" && Number.isFinite(value)) return value > 0;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed > 0;
  }
  return false;
}

function plural(count: number, singular: string, pluralLabel = `${singular}s`) {
  return `${count.toLocaleString()} ${count === 1 ? singular : pluralLabel}`;
}

function titleCase(value: string): string {
  return value ? `${value.charAt(0).toUpperCase()}${value.slice(1).toLowerCase()}` : value;
}

function countItems(value: unknown): number {
  return Array.isArray(value) ? value.filter(Boolean).length : 0;
}

function GroundingSummary({ grounding }: { grounding: unknown }) {
  const detail = asRecord(grounding);
  if (!Object.keys(detail).length) return null;

  const rawScore = detail.confidence_score;
  const confidencePercent = typeof rawScore === "number" && Number.isFinite(rawScore)
    ? Math.round(rawScore * 100)
    : null;
  const confidenceLevel = typeof detail.confidence_level === "string" && detail.confidence_level.trim()
    ? titleCase(detail.confidence_level.trim())
    : null;
  const confidenceText = confidenceLevel || confidencePercent !== null
    ? `${confidenceLevel || "Evidence"} confidence${confidencePercent !== null ? ` ${confidencePercent}%` : ""}`
    : null;

  const validatedCount = typeof detail.validated_claim_count === "number"
    ? detail.validated_claim_count
    : detail.evidence_basis === "validated_claims"
      ? countItems(detail.claim_ids)
      : 0;
  const claimCount = typeof detail.claim_count === "number" ? detail.claim_count : countItems(detail.claim_ids);
  const evidenceSpanCount = typeof detail.evidence_span_count === "number" ? detail.evidence_span_count : countItems(detail.evidence_span_ids);
  const supportParts = [
    validatedCount > 0 ? plural(validatedCount, "validated claim") : claimCount > 0 ? plural(claimCount, "claim") : null,
    evidenceSpanCount > 0 ? plural(evidenceSpanCount, "evidence span") : null,
  ].filter(Boolean);

  if (!confidenceText && !supportParts.length) return null;

  return (
    <div className="generated-grounding">
      {confidenceText && <span>{confidenceText}</span>}
      {supportParts.length > 0 && <small>{supportParts.join(" · ")}</small>}
    </div>
  );
}

function initialState(): ReportState {
  return { status: "checking", payload: null, message: "Checking cache..." };
}

function cachedPayload(kind: GeneratedReportKind, response: { cached: boolean; report?: unknown; result?: unknown }): unknown | null {
  if (!response.cached) return null;
  return finalPayloadForKind(kind, response);
}

export function GeneratedReportsPanel({ documentId, documentName, variant = "rail" }: Props) {
  const [activeKind, setActiveKind] = useState<GeneratedReportKind>("executive");
  const [states, setStates] = useState<Record<GeneratedReportKind, ReportState>>({
    executive: initialState(),
    narrative: initialState(),
    simulation: initialState(),
  });

  const activeState = states[activeKind];

  useEffect(() => {
    let cancelled = false;
    setStates((current) => ({
      ...current,
      [activeKind]: { status: "checking", payload: null, message: "Checking cache..." },
    }));

    getGeneratedReport(activeKind, documentId)
      .then((response) => {
        if (cancelled) return;
        setStates((current) => ({
          ...current,
          [activeKind]: {
            status: "ready",
            payload: cachedPayload(activeKind, response),
            message: response.cached ? "Cached report loaded." : "No cached report yet.",
          },
        }));
      })
      .catch(() => {
        if (cancelled) return;
        setStates((current) => ({
          ...current,
          [activeKind]: { status: "error", payload: null, message: "Generated report unavailable." },
        }));
      });

    return () => {
      cancelled = true;
    };
  }, [activeKind, documentId]);

  async function generateReport(regenerate = false) {
    setStates((current) => ({
      ...current,
      [activeKind]: { ...current[activeKind], status: "generating", message: regenerate ? "Clearing cached report..." : "Starting report generation..." },
    }));

    try {
      if (regenerate) {
        await deleteGeneratedReport(activeKind, documentId);
      }
      const finalPayload = await streamGeneratedReport(activeKind, documentId, (event) => {
        setStates((current) => ({
          ...current,
          [activeKind]: {
            ...current[activeKind],
            status: "generating",
            message: event.message || event.stage || "Generating report...",
          },
        }));
      });
      setStates((current) => ({
        ...current,
        [activeKind]: {
          status: "ready",
          payload: finalPayload,
          message: finalPayload ? "Report ready." : "Generation completed without report content.",
        },
      }));
    } catch (error) {
      const message = error instanceof Error && error.message ? error.message : "Generation failed.";
      setStates((current) => ({
        ...current,
        [activeKind]: { ...current[activeKind], status: "error", message },
      }));
    }
  }

  return (
    <div className={`generated-report-panel ${variant}`}>
      <div className="report-tabs">
        {reportTabs.map(({ kind, label }) => (
          <button key={kind} className={activeKind === kind ? "active" : ""} onClick={() => setActiveKind(kind)}>
            {label}
          </button>
        ))}
      </div>

      <div className="generated-report-actions">
        <span>{activeState.message}</span>
        <button disabled={activeState.status === "generating"} onClick={() => generateReport(false)}>Generate</button>
        <button disabled={activeState.status === "generating"} onClick={() => generateReport(true)}>Regenerate</button>
      </div>

      <div className={`generated-status ${activeState.status}`}>
        <strong>{generatedReportConfig[activeKind].label}</strong>
        <small>{documentName || documentId}</small>
      </div>

      {activeState.status === "checking" && <div className="report-empty">Checking generated report cache...</div>}
      {activeState.status === "error" && <div className="report-empty error">Generated report flow unavailable.</div>}
      {activeState.status !== "checking" && activeState.status !== "error" && !activeState.payload && (
        <div className="generated-empty">No cached {generatedReportConfig[activeKind].label.toLowerCase()} yet.</div>
      )}
      {activeState.payload !== null && (
        <div className="generated-report-body">
          {activeKind === "executive" && <ExecutiveReport payload={activeState.payload} />}
          {activeKind === "narrative" && <NarrativeReport payload={activeState.payload} />}
          {activeKind === "simulation" && <SimulationReport payload={activeState.payload} />}
        </div>
      )}
    </div>
  );
}

export function ExecutiveReport({ payload }: { payload: unknown }) {
  const report = asRecord(payload);
  const issues = asArray(report.issues).slice(0, 5);
  return (
    <>
      <div className="generated-card">
        <span>Assessment</span>
        <strong>{text(report.overall_assessment, "Assessment pending")}</strong>
        <p>{snippet(report.summary_narrative || report.executive_summary)}</p>
      </div>
      {report.business_impact && <p className="generated-note">{text(report.business_impact)}</p>}
      <div className="generated-issue-list">
        {issues.map((issue, index) => (
          <div key={`${text(issue.title, "Issue")}-${index}`} className="generated-issue">
            <span>{text(issue.severity, "Unscored")}</span>
            <strong>{text(issue.title, "Untitled issue")}</strong>
            <small>{snippet(issue.plain_english || issue.solution)}</small>
            <GroundingSummary grounding={issue.grounding || issue} />
          </div>
        ))}
      </div>
      {report.coverage_warning && <p className="generated-warning">{text(report.coverage_warning)}</p>}
    </>
  );
}

export function NarrativeReport({ payload }: { payload: unknown }) {
  const report = asRecord(payload);
  const chapters = asArray(report.chapters).slice(0, 6);
  return (
    <>
      <div className="generated-card">
        <span>Assessment</span>
        <strong>{text(report.overall_assessment, "Narrative ready")}</strong>
        <p>{snippet(report.summary_narrative || report.executive_summary || report.narrative)}</p>
      </div>
      <div className="generated-issue-list">
        {chapters.map((chapter, index) => (
          <div key={`${text(chapter.title, "Chapter")}-${index}`} className="generated-issue">
            <span>Chapter {index + 1}</span>
            <strong>{text(chapter.title, "Untitled chapter")}</strong>
            <small>{snippet(chapter.narrative)}</small>
            <GroundingSummary grounding={chapter.grounding_summary || chapter} />
          </div>
        ))}
      </div>
      {report.coverage_warning && <p className="generated-warning">{text(report.coverage_warning)}</p>}
    </>
  );
}

export function SimulationReport({ payload }: { payload: unknown }) {
  const report = asRecord(payload);
  return (
    <div className="simulation-grid">
      <BlastRadiusCard payload={report.blast_radius} />
      <BlackSwanCard payload={report.black_swan} />
      <MonteCarloCard payload={report.monte_carlo} />
    </div>
  );
}

function BlastRadiusCard({ payload }: { payload: unknown }) {
  const detail = asRecord(payload);
  const nodes = asArray(detail.nodes);
  const topNode = nodes[0] || {};
  const score = formatDecimal(detail.svi || detail.svi_score || detail.risk_score);
  const blastRadius = numberText(topNode.blast_radius_count);
  const cascadeDepth = numberText(topNode.cascade_depth);
  const topName = text(topNode.name || topNode.id, "No dominant cascade node");
  const summary = nodes.length
    ? `${topName} affects ${blastRadius || "unknown"} downstream nodes across depth ${cascadeDepth || "unknown"}.`
    : text(detail.summary || detail.analysis, "No blast-radius cascade nodes found.");
  return (
    <div className="generated-card">
      <span>Blast Radius</span>
      <strong>{score ? `SVI ${score}` : "SVI unavailable"}</strong>
      <p>{summary}</p>
      {nodes.length > 0 && (
        <div className="simulation-detail-list">
          {nodes.slice(0, 3).map((node, index) => (
            <div key={`${text(node.id || node.name, "node")}-${index}`}>
              <strong>{text(node.name || node.id, "Unnamed node")}</strong>
              <small>
                {numberText(node.dependency_count) ? `${numberText(node.dependency_count)} dependencies` : "Dependency count unavailable"}
                {numberText(node.svi_contribution) ? ` · SVI contribution ${numberText(node.svi_contribution)}` : ""}
              </small>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function BlackSwanCard({ payload }: { payload: unknown }) {
  const detail = asRecord(payload);
  const scenarios = asArray(detail.scenarios);
  const firstScenario = scenarios[0] || {};
  const scenarioCount = scenarios.length;
  const trigger = text(firstScenario.trigger_node, "trigger not specified");
  const cascadePath = Array.isArray(firstScenario.cascade_path) ? firstScenario.cascade_path : [];
  const summary = scenarioCount
    ? `${text(firstScenario.title, "Untitled scenario")} starts at ${trigger} and spans ${plural(cascadePath.length, "step")}.`
    : text(detail.summary || detail.analysis, "No black-swan scenarios available.");
  return (
    <div className="generated-card">
      <span>Black Swan</span>
      <strong>{scenarioCount ? plural(scenarioCount, "scenario") : "No scenarios"}</strong>
      <p>{summary}</p>
      {scenarios.length > 0 && (
        <div className="simulation-detail-list">
          {scenarios.slice(0, 3).map((scenario, index) => {
            const path = Array.isArray(scenario.cascade_path) ? scenario.cascade_path : [];
            return (
              <div key={`${text(scenario.title, "scenario")}-${index}`}>
                <strong>{text(scenario.title, "Untitled scenario")}</strong>
                <small>{text(scenario.trigger_node, "Trigger unavailable")} · {plural(path.length, "cascade step")}</small>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function MonteCarloCard({ payload }: { payload: unknown }) {
  const detail = asRecord(payload);
  const atRiskNodes = asArray(detail.at_risk_nodes).filter((node) => positiveNumber(node.mean_delay_days));
  const p50 = daysText(firstPresent(detail.p50_delay_days, detail.p50));
  const p80 = daysText(firstPresent(detail.p80_delay_days, detail.p80));
  const p95 = daysText(firstPresent(detail.p95_delay_days, detail.p95, detail.p90_delay_days, detail.p90));
  const available = detail.available !== false && Boolean(p50 || p80 || p95);
  const forecastSummary = `P50 ${p50 || "n/a"} - P80 ${p80 || "n/a"} - P95 ${p95 || "n/a"}.`;
  return (
    <div className="generated-card">
      <span>Monte Carlo</span>
      <strong>{available ? `P95 ${p95 || "n/a"}` : "Forecast unavailable"}</strong>
      <p>
        {available
          ? `${forecastSummary} ${atRiskNodes.length > 0 ? `${plural(atRiskNodes.length, "node")} flagged as delay-sensitive.` : "No delay-sensitive nodes identified."}`
          : text(detail.reason || detail.message, "Insufficient temporal data for Monte Carlo forecasting.")}
      </p>
      {available && atRiskNodes.length > 0 && (
        <div className="simulation-detail-list">
          {atRiskNodes.slice(0, 3).map((node, index) => (
            <div key={`${text(node.id || node.name, "risk-node")}-${index}`}>
              <strong>{text(node.name || node.id, "Unnamed node")}</strong>
              <small>{daysText(node.mean_delay_days) || "Mean delay unavailable"}</small>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
