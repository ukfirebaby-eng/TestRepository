import { useEffect, useMemo, useState } from "react";
import type { BottleneckItem, FrictionQueueItem, GraphLink, GraphNode, NormalizedGraph, OperationalReports, RiskMatrixItem, ScheduleCollapseItem } from "../api/types";
import { loadOperationalReports } from "../api/client";
import { findReportGraphLink, findReportGraphNode, riskMatrixBuckets } from "../reports/operational";

type ReportTab = "friction" | "bottlenecks" | "schedule" | "matrix";

type Props = {
  documentId: string;
  graph: NormalizedGraph;
  onFocusGraphItem: (item: GraphNode | GraphLink) => void;
  variant?: "rail" | "workspace";
};

const tabs: Array<{ id: ReportTab; label: string }> = [
  { id: "friction", label: "Friction Queue" },
  { id: "bottlenecks", label: "Bottlenecks" },
  { id: "schedule", label: "Schedule Collapse" },
  { id: "matrix", label: "Risk Matrix" },
];

function snippet(text?: string, fallback = "No analysis available.", limit = 180) {
  if (!text) return fallback;
  return text.length > limit ? `${text.slice(0, limit - 3)}...` : text;
}

export function OperationalReportsPanel({ documentId, graph, onFocusGraphItem, variant = "rail" }: Props) {
  const [activeTab, setActiveTab] = useState<ReportTab>("friction");
  const [reports, setReports] = useState<OperationalReports | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const snippetLimit = variant === "workspace" ? 320 : 180;

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    loadOperationalReports(documentId)
      .then((data) => {
        if (cancelled) return;
        setReports(data);
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [documentId]);

  const matrixBuckets = useMemo(() => riskMatrixBuckets(reports?.riskMatrix || []), [reports]);

  function selectReportLink(row: FrictionQueueItem | ScheduleCollapseItem | RiskMatrixItem) {
    const link = findReportGraphLink(graph, row);
    if (link) onFocusGraphItem(link);
  }

  function selectBottleneck(row: BottleneckItem) {
    const node = findReportGraphNode(graph, row);
    if (node) onFocusGraphItem(node);
  }

  return (
    <div className={`operational-report-panel ${variant}`}>
      <div className="dm-tabs report-tabs">
        {tabs.map((tab) => (
          <button key={tab.id} className={activeTab === tab.id ? "active" : ""} onClick={() => setActiveTab(tab.id)}>
            {tab.label}
          </button>
        ))}
      </div>

      {status === "loading" && <div className="report-empty">Loading operational reports...</div>}
      {status === "error" && <div className="report-empty error">Operational reports unavailable.</div>}

      {status === "ready" && reports && activeTab === "friction" && (
        <div className="report-row-list">
          {reports.frictionQueue.length ? reports.frictionQueue.map((item, index) => (
            <button key={`${item.type}-${item.source}-${item.target}-${index}`} className="report-row" onClick={() => selectReportLink(item)}>
              <span>{item.type}</span>
              <strong>{item.source} {"->"} {item.target}</strong>
              <small>{snippet(item.diamond, "No analysis available.", snippetLimit)}</small>
              <em>Focus evidence</em>
            </button>
          )) : <div className="report-empty">No friction items detected.</div>}
        </div>
      )}

      {status === "ready" && reports && activeTab === "bottlenecks" && (
        <div className="report-row-list">
          {reports.bottlenecks.length ? reports.bottlenecks.map((item) => (
            <button key={item.id} className="report-row" onClick={() => selectBottleneck(item)}>
              <span>{item.label || "hub"}</span>
              <strong>{item.name}</strong>
              <small>{Number(item.dependency_count || 0).toLocaleString()} inbound dependencies</small>
              <em>Focus evidence</em>
            </button>
          )) : <div className="report-empty">No bottlenecks detected.</div>}
        </div>
      )}

      {status === "ready" && reports && activeTab === "schedule" && (
        <div className="report-row-list">
          {reports.scheduleCollapse.length ? reports.scheduleCollapse.map((item, index) => (
            <button key={`${item.predecessor_name}-${item.successor_name}-${index}`} className="report-row" onClick={() => selectReportLink(item)}>
              <span>{Number(item.days_at_risk || 0).toLocaleString()} days at risk</span>
              <strong>{item.predecessor_name} {"->"} {item.successor_name}</strong>
              <small>{item.pred_end_date} {"->"} {item.succ_start_date}</small>
              <em>Focus evidence</em>
            </button>
          )) : <div className="report-empty">No schedule collapse detected.</div>}
        </div>
      )}

      {status === "ready" && reports && activeTab === "matrix" && (
        <div className="risk-matrix-panel">
          {Array.from({ length: 5 }, (_, probabilityIndex) => 5 - probabilityIndex).map((probability) => (
            Array.from({ length: 5 }, (_, severityIndex) => severityIndex + 1).map((severity) => {
              const rows = matrixBuckets.get(`${probability}:${severity}`) || [];
              return (
                <button
                  key={`${probability}:${severity}`}
                  className={rows.length ? "matrix-cell active" : "matrix-cell"}
                  disabled={!rows.length}
                  onClick={() => rows[0] && selectReportLink(rows[0])}
                  title={`Probability ${probability}, severity ${severity}`}
                >
                  {rows.length || ""}
                </button>
              );
            })
          ))}
        </div>
      )}
    </div>
  );
}
