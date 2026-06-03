import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("V2 design system contracts", () => {
  it("defines shared primitives for buttons, panels, chips, status, and tabs", () => {
    const css = readFileSync(resolve(__dirname, "../styles.css"), "utf-8");

    expect(css).toContain(".dm-panel");
    expect(css).toContain(".dm-button");
    expect(css).toContain(".dm-button-primary");
    expect(css).toContain(".dm-button-quiet");
    expect(css).toContain(".dm-chip");
    expect(css).toContain(".dm-status");
    expect(css).toContain(".dm-tabs");
  });
});
