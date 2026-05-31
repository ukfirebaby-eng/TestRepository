export type GeneratedReportKind = "executive" | "narrative" | "simulation";

export type GeneratedReportEvent = {
  stage?: string;
  message?: string;
  report?: unknown;
  result?: unknown;
};

export const generatedReportConfig: Record<GeneratedReportKind, { label: string; path: (documentId: string) => string }> = {
  executive: {
    label: "Executive Summary",
    path: (documentId) => `/api/v1/reports/executive-summary/${documentId}`,
  },
  narrative: {
    label: "Narrative Report",
    path: (documentId) => `/api/v1/reports/narrative/${documentId}`,
  },
  simulation: {
    label: "Risk Simulator",
    path: (documentId) => `/api/v1/reports/risk-simulation/${documentId}`,
  },
};

export function parseSseChunk(chunk: string): GeneratedReportEvent[] {
  return chunk
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trim())
    .flatMap((payload) => {
      try {
        return [JSON.parse(payload) as GeneratedReportEvent];
      } catch {
        return [];
      }
    });
}

export function finalPayloadForKind(kind: GeneratedReportKind, event: GeneratedReportEvent): unknown {
  return kind === "simulation" ? event.result : event.report;
}
