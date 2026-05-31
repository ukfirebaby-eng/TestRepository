import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("ReportWorkspace contract", () => {
  it("uses wide operational and generated report panels", () => {
    const source = readFileSync(resolve(__dirname, "ReportWorkspace.tsx"), "utf-8");

    expect(source).toContain("OperationalReportsPanel");
    expect(source).toContain("GeneratedReportsPanel");
    expect(source).toContain('variant="workspace"');
    expect(source).toContain("report-workspace");
  });
});
