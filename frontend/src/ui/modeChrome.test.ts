import { describe, expect, it } from "vitest";
import { modeChromeForView } from "./modeChrome";

describe("modeChromeForView", () => {
  it("makes spatial mode graph-first", () => {
    expect(modeChromeForView("spatial")).toMatchObject({
      rootClass: "mode-spatial",
      showMetrics: true,
      showLensBar: true,
      showSearch: false,
      evidencePlacement: "contextual",
      headline: "Cinematic spatial risk model",
    });
  });

  it("makes analyst mode inspection-first", () => {
    expect(modeChromeForView("analyst")).toMatchObject({
      rootClass: "mode-analyst",
      showMetrics: true,
      showLensBar: true,
      showSearch: true,
      evidencePlacement: "contextual",
      headline: "Analyst dependency map",
    });
  });

  it("makes reports mode report-first", () => {
    expect(modeChromeForView("reports")).toMatchObject({
      rootClass: "mode-reports",
      showMetrics: false,
      showLensBar: false,
      showSearch: false,
      evidencePlacement: "drawer",
      headline: "Reports workspace",
    });
  });
});
