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
});
