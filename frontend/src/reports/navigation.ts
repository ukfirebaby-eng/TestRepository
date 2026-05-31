export type ReportAction = {
  label: string;
  description: string;
  href: string;
  kind: "operational" | "generated" | "export";
};

export function buildReportActions(documentId: string): ReportAction[] {
  return [
    {
      label: "Friction Queue",
      description: "Structural and chronological conflicts.",
      href: `/api/v1/reports/friction-queue/${documentId}`,
      kind: "operational",
    },
    {
      label: "Bottlenecks",
      description: "Fragile hubs and dependency concentration.",
      href: `/api/v1/reports/bottlenecks/${documentId}`,
      kind: "operational",
    },
    {
      label: "Schedule Collapse",
      description: "Timeline conflicts ranked by negative slack.",
      href: `/api/v1/reports/schedule-collapse/${documentId}`,
      kind: "operational",
    },
    {
      label: "Risk Matrix",
      description: "Severity and probability scoring.",
      href: `/api/v1/reports/risk-matrix/${documentId}`,
      kind: "operational",
    },
    {
      label: "Executive Summary",
      description: "Cached plain-English executive report.",
      href: `/api/v1/reports/executive-summary/${documentId}`,
      kind: "generated",
    },
    {
      label: "Narrative Report",
      description: "Cached full narrative report.",
      href: `/api/v1/reports/narrative/${documentId}`,
      kind: "generated",
    },
    {
      label: "Risk Simulator",
      description: "Cached blast-radius and forecast output.",
      href: `/api/v1/reports/risk-simulation/${documentId}`,
      kind: "generated",
    },
    {
      label: "PDF Export",
      description: "Download the narrative report as PDF.",
      href: `/api/v1/export/pdf/${documentId}`,
      kind: "export",
    },
    {
      label: "Word Export",
      description: "Download the narrative report as DOCX.",
      href: `/api/v1/export/docx/${documentId}`,
      kind: "export",
    },
  ];
}
