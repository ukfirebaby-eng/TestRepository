import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("V2 API client document management contract", () => {
  it("exposes document deletion and vault clearing endpoints", () => {
    const source = readFileSync(resolve(__dirname, "client.ts"), "utf-8");

    expect(source).toContain("deleteDocument");
    expect(source).toContain('fetch(`/api/v1/documents/${documentId}`');
    expect(source).toContain("clearVault");
    expect(source).toContain('fetch("/api/v1/vault?confirm=true"');
  });

  it("exposes configuration read and save endpoints", () => {
    const source = readFileSync(resolve(__dirname, "client.ts"), "utf-8");

    expect(source).toContain("loadConfig");
    expect(source).toContain('fetch("/api/v1/config")');
    expect(source).toContain("saveConfig");
    expect(source).toContain('fetch("/api/v1/config", {');
    expect(source).toContain('method: "POST"');
  });

  it("types optional ingestion accuracy telemetry on job status", () => {
    const source = readFileSync(resolve(__dirname, "types.ts"), "utf-8");

    expect(source).toContain("JobAccuracyTelemetry");
    expect(source).toContain("evidence_spans: number");
    expect(source).toContain("needs_review: number");
    expect(source).toContain("accuracy?: JobAccuracyTelemetry");
  });

  it("includes the claim layer runtime flag in configuration types", () => {
    const source = readFileSync(resolve(__dirname, "types.ts"), "utf-8");

    expect(source).toContain("DIAMOND_MINER_CLAIM_LAYER");
  });

  it("exposes the read-only claim accuracy endpoint", () => {
    const clientSource = readFileSync(resolve(__dirname, "client.ts"), "utf-8");
    const typeSource = readFileSync(resolve(__dirname, "types.ts"), "utf-8");

    expect(clientSource).toContain("loadAccuracyPayload");
    expect(clientSource).toContain("`/api/v1/accuracy/${documentId}`");
    expect(typeSource).toContain("AccuracyPayload");
    expect(typeSource).toContain("AccuracyCounts");
    expect(typeSource).toContain("graph_agreement");
    expect(typeSource).toContain("claim_vs_legacy_overlap_rate");
    expect(typeSource).toContain("legacy_only_edges");
    expect(typeSource).toContain("claim_only_edges");
  });
});
