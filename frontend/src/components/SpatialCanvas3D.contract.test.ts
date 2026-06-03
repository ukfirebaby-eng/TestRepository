import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("SpatialCanvas3D camera controls contract", () => {
  it("uses a bounded focus animation so orbit and wheel controls are released", () => {
    const source = readFileSync(resolve(__dirname, "SpatialCanvas3D.tsx"), "utf-8");

    expect(source).toContain("advanceFocusAnimation");
    expect(source).toContain("focusKey");
  });

  it("exposes camera recovery and label-density controls", () => {
    const source = readFileSync(resolve(__dirname, "SpatialCanvas3D.tsx"), "utf-8");

    expect(source).toContain("Reset View");
    expect(source).toContain("Fit Graph");
    expect(source).toContain("Focus Selected");
    expect(source).toContain("Clear Selection");
    expect(source).toContain("Pause Motion");
    expect(source).toContain("label-density");
  });

  it("uses shared focus visibility to dim unrelated graph elements", () => {
    const source = readFileSync(resolve(__dirname, "SpatialCanvas3D.tsx"), "utf-8");

    expect(source).toContain("buildFocusVisibility");
    expect(source).toContain("focusState === \"dimmed\"");
    expect(source).toContain("onPointerMissed={props.onClearSelection}");
  });

  it("surfaces risk concentration as a 3D usefulness cue", () => {
    const source = readFileSync(resolve(__dirname, "SpatialCanvas3D.tsx"), "utf-8");

    expect(source).toContain("summarizeRiskConcentration");
    expect(source).toContain("risk-concentration-hud");
    expect(source).toContain("selected-neighbors");
  });

  it("keeps selected nodes risk-coloured and marks selection with a ring", () => {
    const source = readFileSync(resolve(__dirname, "SpatialCanvas3D.tsx"), "utf-8");

    expect(source).toContain("selectionRingColor");
    expect(source).toContain("const nodeColor = riskColor(node.riskKind)");
    expect(source).not.toContain('focusState === "selected" ? "#ffffff"');
  });
});
