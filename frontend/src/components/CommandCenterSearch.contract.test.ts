import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("CommandCenterApp search/detail contract", () => {
  it("exposes node search and richer evidence sections", () => {
    const source = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");

    expect(source).toContain("node-search-input");
    expect(source).toContain("searchNodes(");
    expect(source).toContain("buildNodeDetail(");
    expect(source).toContain("buildLinkDetail(");
    expect(source).toContain("Connected Nodes");
    expect(source).toContain("Risk Score");
    expect(source).toContain("Cascade Path");
  });
});
