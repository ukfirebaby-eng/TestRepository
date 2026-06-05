import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("Vite build configuration", () => {
  it("splits heavy visualization vendors into explicit chunks", () => {
    const source = readFileSync(resolve(__dirname, "../vite.config.ts"), "utf-8");

    expect(source).toContain("manualChunks");
    expect(source).toContain("react-vendor");
    expect(source).toContain("three-vendor");
    expect(source).toContain("graph-vendor");
    expect(source).toContain("chunkSizeWarningLimit");
  });
});
