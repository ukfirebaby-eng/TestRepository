import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("CommandCenterApp graph loading contract", () => {
  it("lazy-loads heavyweight graph renderers behind suspense", () => {
    const source = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");

    expect(source).toContain("lazy(");
    expect(source).toContain("Suspense");
    expect(source).toContain('import("./SpatialCanvas3D")');
    expect(source).toContain('import("./AnalystMap2D")');
  });

  it("marks the active critical attention item and routes clicks through the focus helper", () => {
    const source = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");

    expect(source).toContain("focusAttentionItem");
    expect(source).toContain("isAttentionItemSelected");
    expect(source).toContain("attention-item active");
    expect(source).toContain("aria-pressed");
  });

  it("renders plain-English explanation for selected risk links", () => {
    const source = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");

    expect(source).toContain("plain-english-panel");
    expect(source).toContain("linkDetail.plainEnglish.heading");
    expect(source).toContain("linkDetail.plainEnglish.actions");
  });

  it("renders V2 ingestion telemetry and document management controls", () => {
    const source = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");

    expect(source).toContain("uploadProgress");
    expect(source).toContain("ingestion-progress-panel");
    expect(source).toContain("deleteDocument");
    expect(source).toContain("doc-delete-action");
    expect(source).toContain("clearVault");
    expect(source).toContain("Clear Vault");
  });

  it("renders export report channels in the top command ribbon", () => {
    const source = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");

    expect(source).toContain("buildReportActions");
    expect(source).toContain("exportReportActions.map");
    expect(source).toContain("command-export");
    expect(source).not.toContain("Report Channels");
    expect(source).not.toContain("report-action-list");
  });

  it("restores the V2 configuration drawer from the top command ribbon", () => {
    const source = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");

    expect(source).toContain("Configuration");
    expect(source).toContain("config-drawer");
    expect(source).toContain("loadConfig");
    expect(source).toContain("saveConfig");
    expect(source).toContain("LLM_PROVIDER");
    expect(source).toContain("OPENROUTER_API_KEY");
    expect(source).toContain("FAST_MODEL");
  });

  it("routes native operational reports through the reports workspace", () => {
    const source = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");

    expect(source).toContain("ReportWorkspace");
    expect(source).not.toContain("<OperationalReportsPanel");
  });

  it("routes native generated report flows through the reports workspace", () => {
    const source = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");

    expect(source).toContain("ReportWorkspace");
    expect(source).not.toContain("<GeneratedReportsPanel");
  });

  it("renders reports as a center workspace mode instead of right-rail panels", () => {
    const source = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");

    expect(source).toContain('type ViewMode = "spatial" | "analyst" | "reports"');
    expect(source).toContain("ReportWorkspace");
    expect(source).toContain('setViewMode("reports")');
    expect(source).toContain("Reports</button>");
    expect(source).toContain("<ReportWorkspace");
  });
});
