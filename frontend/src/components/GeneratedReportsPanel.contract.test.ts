import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("GeneratedReportsPanel contract", () => {
  it("renders native generated report tabs and generation controls", () => {
    const source = readFileSync(resolve(__dirname, "GeneratedReportsPanel.tsx"), "utf-8");

    expect(source).toContain("Executive Summary");
    expect(source).toContain("Narrative Report");
    expect(source).toContain("Risk Simulator");
    expect(source).toContain("Generate");
    expect(source).toContain("Regenerate");
    expect(source).toContain("streamGeneratedReport");
  });
});
