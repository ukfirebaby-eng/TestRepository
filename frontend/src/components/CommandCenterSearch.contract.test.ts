import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("CommandCenterApp search/detail contract", () => {
  it("exposes node search and richer evidence sections", () => {
    const appSource = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");
    const evidenceSource = readFileSync(resolve(__dirname, "SelectedEvidencePanel.tsx"), "utf-8");
    const evidenceModelSource = readFileSync(resolve(__dirname, "../ui/evidenceViewModel.ts"), "utf-8");

    expect(appSource).toContain("node-search-input");
    expect(appSource).toContain("searchNodes(");
    expect(appSource).toContain("buildNodeDetail(");
    expect(appSource).toContain("buildLinkDetail(");
    expect(evidenceSource).toContain("Supporting graph evidence");
    expect(evidenceModelSource).toContain("Risk score");
    expect(evidenceSource).toContain("Cascade Path");
  });
});
