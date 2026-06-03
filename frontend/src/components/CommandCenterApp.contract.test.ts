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

  it("delegates selected evidence rendering to SelectedEvidencePanel", () => {
    const source = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");

    expect(source).toContain("SelectedEvidencePanel");
    expect(source).not.toContain("plain-english-panel");
  });

  it("uses mode chrome and ModeToolbar for mode-specific hierarchy", () => {
    const source = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");

    expect(source).toContain("modeChromeForView");
    expect(source).toContain("ModeToolbar");
    expect(source).toContain("chrome.showMetrics");
    expect(source).toContain("chrome.showLensBar");
    expect(source).toContain("chrome.showSearch");
  });

  it("switches from reports to graph focus when report evidence is selected", () => {
    const source = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");

    expect(source).toContain("focusGraphItemFromReport");
    expect(source).toContain('setViewMode("analyst")');
    expect(source).toContain("focusedFromReport");
    expect(source).toContain("GraphFocusBanner");
  });

  it("renders V2 ingestion telemetry and document management controls", () => {
    const source = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");

    expect(source).toContain("uploadProgress");
    expect(source).toContain("ingestion-progress-panel");
    expect(source).toContain("ingestion-accuracy-grid");
    expect(source).toContain("Evidence spans");
    expect(source).toContain("Batches");
    expect(source).toContain("claims_after_dedupe");
    expect(source).toContain("Needs review");
    expect(source).toContain("deleteDocument");
    expect(source).toContain("doc-delete-action");
    expect(source).toContain("clearVault");
    expect(source).toContain("Clear Vault");
  });

  it("renders export report channels in the top command ribbon", () => {
    const appSource = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");
    const toolbarSource = readFileSync(resolve(__dirname, "ModeToolbar.tsx"), "utf-8");

    expect(appSource).toContain("buildReportActions");
    expect(toolbarSource).toContain("exportReportActions.map");
    expect(toolbarSource).toContain("command-export");
    expect(appSource).not.toContain("Report Channels");
    expect(appSource).not.toContain("report-action-list");
  });

  it("restores the V2 configuration drawer from the top command ribbon", () => {
    const appSource = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");
    const toolbarSource = readFileSync(resolve(__dirname, "ModeToolbar.tsx"), "utf-8");

    expect(toolbarSource).toContain("Configuration");
    expect(toolbarSource).toContain("config-icon-action");
    expect(toolbarSource).toContain('aria-label="Configuration"');
    expect(appSource).toContain("config-drawer");
    expect(appSource).toContain("loadConfig");
    expect(appSource).toContain("saveConfig");
    expect(appSource).toContain("LLM_PROVIDER");
    expect(appSource).toContain("OPENROUTER_API_KEY");
    expect(appSource).toContain("FAST_MODEL");
    expect(appSource).toContain("DIAMOND_MINER_CLAIM_LAYER");
    expect(appSource).toContain("Claim layer");
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

  it("routes claim-layer inspection through the accuracy workspace", () => {
    const appSource = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");
    const toolbarSource = readFileSync(resolve(__dirname, "ModeToolbar.tsx"), "utf-8");

    expect(toolbarSource).toContain("Accuracy");
    expect(appSource).toContain("AccuracyWorkspace");
    expect(toolbarSource).toContain('onViewModeChange("accuracy")');
    expect(appSource).toContain("<AccuracyWorkspace");
    const accuracySource = readFileSync(resolve(__dirname, "AccuracyWorkspace.tsx"), "utf-8");
    expect(accuracySource).toContain("Claim Quality Report");
    expect(accuracySource).toContain("Graph agreement");
    expect(accuracySource).toContain("Claim vs legacy overlap");
    expect(accuracySource).toContain("Graph review candidates");
    expect(accuracySource).toContain("legacy_only_edges");
    expect(accuracySource).toContain("claim_only_edges");
    expect(accuracySource).toContain("payload.quality.graph_agreement");
    expect(accuracySource).toContain("payload.quality");
    expect(accuracySource).toContain("Extraction coverage");
    expect(accuracySource).toContain("Promotion readiness");
    expect(accuracySource).toContain("Canonical Entities");
    expect(accuracySource).toContain("payload.canonical_entities");
    expect(accuracySource).toContain("Extraction Failures");
    expect(accuracySource).toContain("payload.extraction_failures");
  });

  it("renders reports as a center workspace mode instead of right-rail panels", () => {
    const source = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");

    expect(source).toContain("ViewMode");
    expect(source).toContain("ReportWorkspace");
    expect(source).toContain('setViewMode("reports")');
    expect(source).toContain("ModeToolbar");
    expect(source).toContain("<ReportWorkspace");
  });
});
