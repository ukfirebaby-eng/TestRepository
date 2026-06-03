export type ViewMode = "spatial" | "analyst" | "reports" | "accuracy";

export type EvidencePlacement = "contextual" | "drawer";

export type ModeChrome = {
  rootClass: string;
  headline: string;
  showMetrics: boolean;
  showLensBar: boolean;
  showSearch: boolean;
  evidencePlacement: EvidencePlacement;
};

const chrome: Record<ViewMode, ModeChrome> = {
  spatial: {
    rootClass: "mode-spatial",
    headline: "Cinematic spatial risk model",
    showMetrics: true,
    showLensBar: true,
    showSearch: false,
    evidencePlacement: "contextual",
  },
  analyst: {
    rootClass: "mode-analyst",
    headline: "Analyst dependency map",
    showMetrics: true,
    showLensBar: true,
    showSearch: true,
    evidencePlacement: "contextual",
  },
  reports: {
    rootClass: "mode-reports",
    headline: "Reports workspace",
    showMetrics: false,
    showLensBar: false,
    showSearch: false,
    evidencePlacement: "drawer",
  },
  accuracy: {
    rootClass: "mode-accuracy",
    headline: "Claim accuracy workspace",
    showMetrics: false,
    showLensBar: false,
    showSearch: false,
    evidencePlacement: "drawer",
  },
};

export function modeChromeForView(viewMode: ViewMode): ModeChrome {
  return chrome[viewMode];
}
