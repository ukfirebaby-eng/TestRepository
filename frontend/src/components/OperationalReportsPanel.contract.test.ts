import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("OperationalReportsPanel contract", () => {
  it("renders native report tabs and graph focus actions", () => {
    const source = readFileSync(resolve(__dirname, "OperationalReportsPanel.tsx"), "utf-8");

    expect(source).toContain("Friction Queue");
    expect(source).toContain("Bottlenecks");
    expect(source).toContain("Schedule Collapse");
    expect(source).toContain("Risk Matrix");
    expect(source).toContain("onFocusGraphItem");
    expect(source).toContain("Focus evidence");
  });
});
