import { describe, expect, it } from "vitest";
import { generatedReportConfig, parseSseChunk } from "./generated";

describe("generated report helpers", () => {
  it("maps generated report kinds to existing backend endpoints", () => {
    expect(generatedReportConfig.executive.path("doc-1")).toBe("/api/v1/reports/executive-summary/doc-1");
    expect(generatedReportConfig.narrative.path("doc-1")).toBe("/api/v1/reports/narrative/doc-1");
    expect(generatedReportConfig.simulation.path("doc-1")).toBe("/api/v1/reports/risk-simulation/doc-1");
  });

  it("parses server-sent report events from streamed chunks", () => {
    expect(parseSseChunk('data: {"stage":"complete","report":{"overall_assessment":"High Risk"}}\n\n')).toEqual([
      { stage: "complete", report: { overall_assessment: "High Risk" } },
    ]);
  });

  it("parses streamed report error events", () => {
    expect(parseSseChunk('data: {"stage":"error","message":"Provider rejected max_tokens","error":"provider_error"}\n\n')).toEqual([
      { stage: "error", message: "Provider rejected max_tokens", error: "provider_error" },
    ]);
  });
});
