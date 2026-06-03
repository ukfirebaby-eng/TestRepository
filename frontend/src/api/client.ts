import type { AccuracyPayload, AppConfig, BottleneckItem, CanvasPayload, ClearVaultResult, ConfigUpdate, ConfigUpdateResult, DeleteDocumentResult, DocumentSummary, FrictionQueueItem, JobStatus, OperationalReports, RiskMatrixItem, ScheduleCollapseItem, UploadResult } from "./types";
import { finalPayloadForKind, generatedReportConfig, parseSseChunk, type GeneratedReportEvent, type GeneratedReportKind } from "../reports/generated";

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function listDocuments(): Promise<DocumentSummary[]> {
  const data = await readJson<{ documents: DocumentSummary[] }>(await fetch("/api/v1/documents"));
  return data.documents ?? [];
}

export async function loadCanvas(documentId: string): Promise<CanvasPayload> {
  return readJson<CanvasPayload>(await fetch(`/api/v1/canvas/${documentId}`));
}

export async function uploadDocument(file: File): Promise<UploadResult> {
  const formData = new FormData();
  formData.append("file", file);
  return readJson<UploadResult>(await fetch("/api/v1/ingest", { method: "POST", body: formData }));
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  return readJson<JobStatus>(await fetch(`/api/v1/status/${jobId}`));
}

export async function deleteDocument(documentId: string): Promise<DeleteDocumentResult> {
  return readJson<DeleteDocumentResult>(await fetch(`/api/v1/documents/${documentId}`, { method: "DELETE" }));
}

export async function clearVault(): Promise<ClearVaultResult> {
  return readJson<ClearVaultResult>(await fetch("/api/v1/vault?confirm=true", { method: "DELETE" }));
}

export async function loadConfig(): Promise<AppConfig> {
  return readJson<AppConfig>(await fetch("/api/v1/config"));
}

export async function saveConfig(config: ConfigUpdate): Promise<ConfigUpdateResult> {
  return readJson<ConfigUpdateResult>(await fetch("/api/v1/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  }));
}

export async function loadOperationalReports(documentId: string): Promise<OperationalReports> {
  const [frictionQueue, bottlenecks, scheduleCollapse, riskMatrix] = await Promise.all([
    readJson<{ friction_queue: FrictionQueueItem[] }>(await fetch(`/api/v1/reports/friction-queue/${documentId}`)),
    readJson<{ bottlenecks: BottleneckItem[] }>(await fetch(`/api/v1/reports/bottlenecks/${documentId}`)),
    readJson<{ schedule_collapse: ScheduleCollapseItem[] }>(await fetch(`/api/v1/reports/schedule-collapse/${documentId}`)),
    readJson<{ risk_matrix: RiskMatrixItem[] }>(await fetch(`/api/v1/reports/risk-matrix/${documentId}`)),
  ]);

  return {
    frictionQueue: frictionQueue.friction_queue ?? [],
    bottlenecks: bottlenecks.bottlenecks ?? [],
    scheduleCollapse: scheduleCollapse.schedule_collapse ?? [],
    riskMatrix: riskMatrix.risk_matrix ?? [],
  };
}

export async function loadAccuracyPayload(documentId: string): Promise<AccuracyPayload> {
  return readJson<AccuracyPayload>(await fetch(`/api/v1/accuracy/${documentId}`));
}

export async function getGeneratedReport(kind: GeneratedReportKind, documentId: string): Promise<{ cached: boolean; report?: unknown; result?: unknown }> {
  return readJson<{ cached: boolean; report?: unknown; result?: unknown }>(await fetch(generatedReportConfig[kind].path(documentId)));
}

export async function deleteGeneratedReport(kind: GeneratedReportKind, documentId: string): Promise<void> {
  const response = await fetch(generatedReportConfig[kind].path(documentId), { method: "DELETE" });
  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`);
  }
}

export async function streamGeneratedReport(
  kind: GeneratedReportKind,
  documentId: string,
  onEvent: (event: GeneratedReportEvent) => void,
): Promise<unknown | null> {
  const response = await fetch(generatedReportConfig[kind].path(documentId), { method: "POST" });
  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`);
  }
  if (!response.body) {
    throw new Error("Report stream unavailable.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let finalPayload: unknown | null = null;
  let streamError: string | null = null;
  let buffer = "";

  function handleEvents(events: GeneratedReportEvent[]) {
    events.forEach((event) => {
      onEvent(event);
      if (event.stage === "error" || event.error) {
        streamError = event.message || "Report generation failed.";
      }
      if (event.stage === "complete") {
        const payload = finalPayloadForKind(kind, event);
        if (payload !== undefined) finalPayload = payload;
      }
    });
  }

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() ?? "";
    frames.forEach((frame) => handleEvents(parseSseChunk(frame)));
  }

  buffer += decoder.decode();
  handleEvents(parseSseChunk(buffer));

  if (streamError) {
    throw new Error(streamError);
  }

  return finalPayload;
}
