import { describe, expect, it } from "vitest";
import { buildReportActions } from "./navigation";

describe("buildReportActions", () => {
  it("builds existing report and export routes for the active document", () => {
    const actions = buildReportActions("doc-123");

    expect(actions.map((action) => action.label)).toEqual([
      "Friction Queue",
      "Bottlenecks",
      "Schedule Collapse",
      "Risk Matrix",
      "Executive Summary",
      "Narrative Report",
      "Risk Simulator",
      "PDF Export",
      "Word Export",
    ]);
    expect(actions.map((action) => action.href)).toContain("/api/v1/reports/friction-queue/doc-123");
    expect(actions.map((action) => action.href)).toContain("/api/v1/export/docx/doc-123");
  });
});
