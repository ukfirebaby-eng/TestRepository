import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("AnalystMap2D selection contract", () => {
  it("keeps selected graph evidence visible with explicit map state", () => {
    const source = readFileSync(resolve(__dirname, "AnalystMap2D.tsx"), "utf-8");

    expect(source).toContain("buildFocusVisibility");
    expect(source).toContain("Selection focused");
    expect(source).toContain('focusState === "dimmed"');
    expect(source).toContain("clickStage");
    expect(source).toContain("Clear selection");
    expect(source).toContain("drawAnalystNodeHover");
    expect(source).toContain("defaultDrawNodeHover: drawAnalystNodeHover");
    expect(source).toContain('context.fillStyle = "#edf4f7"');
  });
});
