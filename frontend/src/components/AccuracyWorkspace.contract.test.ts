import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("AccuracyWorkspace contract", () => {
  it("lets graph mismatch candidates open a review detail panel", () => {
    const source = readFileSync(resolve(__dirname, "AccuracyWorkspace.tsx"), "utf-8");

    expect(source).toContain("buildGraphReviewCandidate");
    expect(source).toContain("selectedCandidate");
    expect(source).toContain("Review candidate detail");
    expect(source).toContain("setSelectedCandidate");
  });
});
