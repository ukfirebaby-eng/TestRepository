import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("SelectedEvidencePanel contract", () => {
  it("renders action-oriented evidence sections", () => {
    const source = readFileSync(resolve(__dirname, "SelectedEvidencePanel.tsx"), "utf-8");

    expect(source).toContain("What this is");
    expect(source).toContain("Why it matters");
    expect(source).toContain("Recommended action");
    expect(source).toContain("Supporting graph evidence");
    expect(source).toContain("buildEvidenceViewModel");
  });
});
