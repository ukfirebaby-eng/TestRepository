# Presentation Layer Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine `/app-v2` from a dense command-center prototype into a calmer, more executive-grade risk workspace where each mode has a clear primary job.

**Architecture:** Keep FastAPI APIs and backend schemas unchanged. Improve the React/Vite presentation layer by extracting mode chrome, selected-evidence rendering, report-to-graph navigation, and reusable UI styling from the current monolithic `CommandCenterApp`/`styles.css` surface. Preserve 3D Canvas, Analyst Map, Reports, ingestion, deletion, configuration, and export behavior.

**Tech Stack:** React 19, TypeScript, Vite, Three.js via `@react-three/fiber`, Sigma.js/Graphology, Vitest, Playwright, FastAPI static serving.

---

## Brainstorming Summary

### Problem Frame

The current V2 UI works, but too many surfaces compete at once: left document rail, top command bar, metric strip, lens bar, search, graph stage, permanent right evidence rail, reports workspace, and config drawer. The next pass should reduce simultaneous visual demands rather than add new capability.

### Options Considered

**Option A: Full layout rebuild.** Replace the three-column shell with a new workspace architecture. This could produce the cleanest visual result, but it risks breaking recently restored ingestion, deletion, reports, and graph focus behavior.

**Option B: Mode-aware refinement inside current shell.** Keep the current V2 shell, but make each mode show only the surfaces that support that mode. Extract selected evidence and mode chrome into smaller components and reuse existing graph state. This is the recommended path.

**Option C: Graph-first polish only.** Improve 3D labels, camera, and colors without changing layout. This is lower risk, but it does not address the main density problem.

### Recommended Direction

Use Option B. It gives the highest presentation-layer value while preserving the beta route and existing backend contracts. The implementation should be incremental and testable: first define mode hierarchy, then redesign selected evidence, then tune 3D usefulness, then wire reports-to-graph navigation, then clean up shared visual primitives.

---

## Target UX Rules

### Spatial Mode

Primary job: show where risk is concentrated.

Visible priority:
- 3D graph stage
- compact metrics
- lens controls
- selected evidence only when something is selected
- Critical Attention list as compact graph-side prompts

Avoid:
- permanent large evidence rail when nothing is selected
- visually equal weight between navigation, metrics, search, reports, and graph

### Analyst Mode

Primary job: inspect readable topology and dependency paths.

Visible priority:
- Analyst Map
- search/filter
- selected evidence
- lens controls

Avoid:
- excessive 3D/cinematic language
- labels or selected states becoming unreadable

### Reports Mode

Primary job: read and act on report content.

Visible priority:
- report content
- report item evidence links
- generated report status/actions
- clear path back to graph focus

Avoid:
- right-rail-only report details
- forcing users to manually re-find graph evidence after reading a report item

---

## Files and Responsibilities

### Create

- `frontend/src/ui/modeChrome.ts`
  - Defines mode-specific surface visibility and copy.
  - Pure TypeScript, unit tested.

- `frontend/src/ui/evidenceViewModel.ts`
  - Converts `nodeDetail`, `linkDetail`, selected node/link, and graph context into action-oriented selected-evidence sections.
  - Pure TypeScript, unit tested.

- `frontend/src/components/SelectedEvidencePanel.tsx`
  - Renders selected evidence using consistent sections: "What this is", "Why it matters", "Recommended action", "Supporting graph evidence".
  - Handles no-selection state without dominating the UI.

- `frontend/src/components/ModeToolbar.tsx`
  - Renders view switcher, export actions, configuration button, and mode-specific return-to-reports action.

- `frontend/src/components/GraphFocusBanner.tsx`
  - Shows a compact "Focused from report" context banner with "Back to Reports" and "Clear focus".

- `frontend/src/graph/riskConcentration.ts`
  - Computes top risk nodes, high-risk links, and concentration copy for 3D HUD summaries.
  - Pure TypeScript, unit tested.

- `frontend/src/ui/uiContracts.test.ts`
  - Source/contract tests for shared design primitives, mode chrome, and evidence wording.

### Modify

- `frontend/src/components/CommandCenterApp.tsx`
  - Reduce layout responsibility by using `ModeToolbar`, `SelectedEvidencePanel`, and `GraphFocusBanner`.
  - Add `reportReturnMode`/`focusedFromReport` state.
  - Add `focusGraphItemFromReport` to select evidence and switch from reports to Analyst Map.
  - Add mode-specific root class names.

- `frontend/src/components/SpatialCanvas3D.tsx`
  - Add risk concentration HUD.
  - Tune default camera/label/risk-path emphasis.
  - Improve empty/no-selection captions.

- `frontend/src/components/ReportWorkspace.tsx`
  - Accept `onFocusGraphItem` instead of only raw `onSelectNode`/`onSelectLink`.
  - Keep report content primary.

- `frontend/src/components/OperationalReportsPanel.tsx`
  - Use `onFocusGraphItem` so clicking report rows focuses graph evidence and returns the user to Analyst Map.
  - Add explicit row affordance text such as "Focus evidence".

- `frontend/src/components/GeneratedReportsPanel.tsx`
  - Keep generated report flows in Reports mode.
  - Add better generated report panel hierarchy, but do not add backend dependencies.

- `frontend/src/styles.css`
  - Introduce reusable design primitives:
    - `.dm-panel`
    - `.dm-button`
    - `.dm-button-primary`
    - `.dm-button-quiet`
    - `.dm-chip`
    - `.dm-status`
    - `.dm-tabs`
  - Add mode-specific layout classes:
    - `.command-center.mode-spatial`
    - `.command-center.mode-analyst`
    - `.command-center.mode-reports`
  - Reduce visual competition through spacing, opacity, and conditional surface prominence.

- `frontend/src/components/*.contract.test.ts`
  - Update source contracts for extracted components and report-to-graph focus.

- `frontend/e2e/app-v2.spec.ts`
  - Add smoke coverage for mode switching, report-item focus, and selected evidence visibility.

---

## Task 1: Define Mode Chrome Rules

**Files:**
- Create: `frontend/src/ui/modeChrome.ts`
- Test: `frontend/src/ui/modeChrome.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/ui/modeChrome.test.ts`:

```ts
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd frontend
npm.cmd run test -- modeChrome.test.ts
```

Expected: FAIL because `frontend/src/ui/modeChrome.ts` does not exist.

- [ ] **Step 3: Implement `modeChrome.ts`**

Create `frontend/src/ui/modeChrome.ts`:

```ts
export type ViewMode = "spatial" | "analyst" | "reports";

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
};

export function modeChromeForView(viewMode: ViewMode): ModeChrome {
  return chrome[viewMode];
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
cd frontend
npm.cmd run test -- modeChrome.test.ts
```

Expected: PASS.

---

## Task 2: Extract Selected Evidence View Model

**Files:**
- Create: `frontend/src/ui/evidenceViewModel.ts`
- Test: `frontend/src/ui/evidenceViewModel.test.ts`
- Later consumer: `frontend/src/components/SelectedEvidencePanel.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/ui/evidenceViewModel.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { buildEvidenceViewModel } from "./evidenceViewModel";

describe("buildEvidenceViewModel", () => {
  it("summarizes selected risk links as an action-oriented evidence card", () => {
    const model = buildEvidenceViewModel({
      selectionType: "link",
      title: "predecessor",
      riskKind: "structural",
      riskScore: 16,
      severity: 4,
      probability: 4,
      sourceName: "Cloud Migration",
      targetName: "Dress rehearsal",
      plainEnglish: {
        heading: "Dependency conflict",
        meaning: "The plan is trying to rehearse before the required security dependency is complete.",
        impact: "This can create rework, delay, or compliance failure.",
        scoreMeaning: "Severity 4 and probability 4 make this a high-priority issue.",
        actions: ["Move migration after certification.", "Escalate to the steering board."],
      },
      analysis: "Escalate and correct the dependency chain.",
    });

    expect(model.heading).toBe("Dependency conflict");
    expect(model.badges).toContain("Risk score 16");
    expect(model.sections.map((section) => section.title)).toEqual([
      "What this is",
      "Why it matters",
      "Recommended action",
      "Supporting graph evidence",
    ]);
    expect(model.sections[2].body).toContain("Move migration after certification.");
  });

  it("summarizes selected nodes with connection evidence", () => {
    const model = buildEvidenceViewModel({
      selectionType: "node",
      title: "Central Authentication Service",
      label: "service",
      riskKind: "fragility",
      riskScore: 12,
      connections: [
        { nodeName: "API Gateway", relationship: "depends on", direction: "outgoing" },
        { nodeName: "Customer Portal", relationship: "supports", direction: "incoming" },
      ],
      fragilityInsight: "Authentication is a single point of failure.",
    });

    expect(model.heading).toBe("Central Authentication Service");
    expect(model.sections[0].body).toContain("service");
    expect(model.sections[1].body).toContain("single point of failure");
    expect(model.sections[3].body).toContain("API Gateway");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd frontend
npm.cmd run test -- evidenceViewModel.test.ts
```

Expected: FAIL because `evidenceViewModel.ts` does not exist.

- [ ] **Step 3: Implement `evidenceViewModel.ts`**

Create `frontend/src/ui/evidenceViewModel.ts`:

```ts
type EvidenceSection = {
  title: "What this is" | "Why it matters" | "Recommended action" | "Supporting graph evidence";
  body: string;
};

type PlainEnglish = {
  heading: string;
  meaning: string;
  impact: string;
  scoreMeaning: string;
  actions: string[];
};

type LinkInput = {
  selectionType: "link";
  title: string;
  riskKind: string;
  riskScore?: number | string;
  severity?: number | string;
  probability?: number | string;
  sourceName: string;
  targetName: string;
  plainEnglish: PlainEnglish;
  analysis?: string;
};

type NodeConnectionInput = {
  nodeName: string;
  relationship: string;
  direction: "incoming" | "outgoing";
};

type NodeInput = {
  selectionType: "node";
  title: string;
  label?: string;
  riskKind: string;
  riskScore?: number | string;
  connections?: NodeConnectionInput[];
  fragilityInsight?: string;
};

export type EvidenceViewModel = {
  heading: string;
  subheading: string;
  badges: string[];
  sections: EvidenceSection[];
};

function hasValue(value: unknown): value is string | number {
  return value !== undefined && value !== null && String(value).trim() !== "";
}

function scoreBadges(input: { riskKind: string; riskScore?: number | string; severity?: number | string; probability?: number | string }): string[] {
  return [
    input.riskKind,
    hasValue(input.riskScore) ? `Risk score ${input.riskScore}` : "",
    hasValue(input.severity) ? `Severity ${input.severity}` : "",
    hasValue(input.probability) ? `Probability ${input.probability}` : "",
  ].filter(Boolean);
}

export function buildEvidenceViewModel(input: LinkInput | NodeInput): EvidenceViewModel {
  if (input.selectionType === "link") {
    return {
      heading: input.plainEnglish.heading || input.title,
      subheading: `${input.sourceName} -> ${input.targetName}`,
      badges: scoreBadges(input),
      sections: [
        { title: "What this is", body: input.plainEnglish.meaning },
        { title: "Why it matters", body: `${input.plainEnglish.impact} ${input.plainEnglish.scoreMeaning}`.trim() },
        { title: "Recommended action", body: input.plainEnglish.actions.join(" ") || input.analysis || "Review and correct the highlighted dependency." },
        { title: "Supporting graph evidence", body: `${input.sourceName} connects to ${input.targetName} through ${input.title}.` },
      ],
    };
  }

  const connections = input.connections || [];
  const connectionText = connections.length
    ? connections.map((connection) => `${connection.nodeName} (${connection.relationship})`).join("; ")
    : "No direct graph connections are currently highlighted.";

  return {
    heading: input.title,
    subheading: input.label || input.riskKind,
    badges: scoreBadges(input),
    sections: [
      { title: "What this is", body: `${input.title} is a ${input.label || input.riskKind} node in the analysed graph.` },
      { title: "Why it matters", body: input.fragilityInsight || "This node matters because it sits inside the selected dependency context." },
      { title: "Recommended action", body: "Review ownership, dependency readiness, and mitigation options for this node." },
      { title: "Supporting graph evidence", body: connectionText },
    ],
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
cd frontend
npm.cmd run test -- evidenceViewModel.test.ts
```

Expected: PASS.

---

## Task 3: Extract Selected Evidence Panel

**Files:**
- Create: `frontend/src/components/SelectedEvidencePanel.tsx`
- Modify: `frontend/src/components/CommandCenterApp.tsx`
- Test: `frontend/src/components/CommandCenterApp.contract.test.ts`
- Test: `frontend/src/components/SelectedEvidencePanel.contract.test.ts`

- [ ] **Step 1: Write the failing contract test**

Create `frontend/src/components/SelectedEvidencePanel.contract.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("SelectedEvidencePanel contract", () => {
  it("renders action-oriented evidence sections", () => {
    const source = readFileSync(resolve(__dirname, "SelectedEvidencePanel.tsx"), "utf-8");

    expect(source).toContain("What this is");
    expect(source).toContain("Why it matters");
    expect(source).toContain("Recommended action");
    expect(source).toContain("Supporting graph evidence");
    expect(source).toContain("buildEvidenceViewModel");
  });
});
```

Update `frontend/src/components/CommandCenterApp.contract.test.ts` with:

```ts
it("delegates selected evidence rendering to SelectedEvidencePanel", () => {
  const source = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");

  expect(source).toContain("SelectedEvidencePanel");
  expect(source).not.toContain("plain-english-panel");
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd frontend
npm.cmd run test -- SelectedEvidencePanel.contract.test.ts CommandCenterApp.contract.test.ts
```

Expected: FAIL because `SelectedEvidencePanel.tsx` does not exist and `CommandCenterApp` still renders evidence inline.

- [ ] **Step 3: Create `SelectedEvidencePanel.tsx`**

Implement a component that accepts:

```ts
type Props = {
  selectedNode: GraphNode | null;
  selectedLink: GraphLink | null;
  nodeDetail: ReturnType<typeof buildNodeDetail> | null;
  linkDetail: ReturnType<typeof buildLinkDetail> | null;
  graph: NormalizedGraph | null;
  onSelectNode: (node: GraphNode) => void;
  onClearSelection: () => void;
  placement: "contextual" | "drawer";
};
```

Rendering rules:
- If no selection, render a compact empty state: "Select a node or risk path to inspect evidence."
- If link selected, use `buildEvidenceViewModel` with `linkDetail.plainEnglish`, `sourceName`, `targetName`, scores, and `analysis`.
- If node selected, use `buildEvidenceViewModel` with label, risk kind, score, connections, and fragility insight.
- Render badges first, then the four evidence sections.
- Keep connected-node buttons, but place them under "Supporting graph evidence".
- Include a "Clear selection" button.

- [ ] **Step 4: Replace inline evidence in `CommandCenterApp.tsx`**

Replace the first `panel-section` inside `.insight-panel` with:

```tsx
<SelectedEvidencePanel
  selectedNode={selectedNode}
  selectedLink={selectedLink}
  nodeDetail={nodeDetail}
  linkDetail={linkDetail}
  graph={graph}
  onSelectNode={selectNode}
  onClearSelection={clearSelection}
  placement={chrome.evidencePlacement}
/>
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd frontend
npm.cmd run test -- evidenceViewModel.test.ts SelectedEvidencePanel.contract.test.ts CommandCenterApp.contract.test.ts
```

Expected: PASS.

---

## Task 4: Add Mode Toolbar and Mode-Aware Layout

**Files:**
- Create: `frontend/src/components/ModeToolbar.tsx`
- Modify: `frontend/src/components/CommandCenterApp.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/components/CommandCenterApp.contract.test.ts`

- [ ] **Step 1: Write the failing contract test**

Add to `CommandCenterApp.contract.test.ts`:

```ts
it("uses mode chrome and ModeToolbar for mode-specific hierarchy", () => {
  const source = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");

  expect(source).toContain("modeChromeForView");
  expect(source).toContain("ModeToolbar");
  expect(source).toContain("chrome.showMetrics");
  expect(source).toContain("chrome.showLensBar");
  expect(source).toContain("chrome.showSearch");
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd frontend
npm.cmd run test -- CommandCenterApp.contract.test.ts
```

Expected: FAIL because mode chrome is not used.

- [ ] **Step 3: Create `ModeToolbar.tsx`**

Props:

```ts
import type { ViewMode } from "../ui/modeChrome";
import type { ReportAction } from "../reports/navigation";

type Props = {
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  exportReportActions: ReportAction[];
  onOpenConfiguration: () => void;
  focusedFromReport: boolean;
  onBackToReports: () => void;
};
```

Rendering:
- Buttons for `3D Canvas`, `Analyst Map`, `Reports`.
- `Configuration` button.
- Export links.
- If `focusedFromReport`, show quiet `Back to Reports` button.

- [ ] **Step 4: Use mode chrome in `CommandCenterApp.tsx`**

Changes:
- Import `modeChromeForView`.
- Replace local `ViewMode` type with imported `ViewMode`.
- Add:

```ts
const chrome = modeChromeForView(viewMode);
```

- Change root:

```tsx
<main className={`command-center ${chrome.rootClass}`}>
```

- Use `chrome.headline` in the top command eyebrow.
- Wrap metrics/search/lens rendering with `chrome.showMetrics`, `chrome.showSearch`, and `chrome.showLensBar`.
- Replace inline `<nav className="command-actions">` with `ModeToolbar`.

- [ ] **Step 5: Add CSS mode hierarchy**

Modify `frontend/src/styles.css`:

```css
.command-center.mode-spatial .insight-panel .panel-section:first-child:not(:has(.evidence-selected)) {
  opacity: 0.78;
}

.command-center.mode-analyst .node-search-panel {
  border-color: rgba(115, 198, 232, 0.32);
}

.command-center.mode-reports {
  grid-template-columns: 280px minmax(0, 1fr);
}

.command-center.mode-reports .insight-panel {
  display: none;
}

.mode-return-action {
  border-color: rgba(245, 201, 95, 0.42);
  color: #fff0bc;
}
```

If `:has()` support is considered too risky, replace the first rule with an explicit class set by `SelectedEvidencePanel`.

- [ ] **Step 6: Run focused tests**

Run:

```bash
cd frontend
npm.cmd run test -- modeChrome.test.ts CommandCenterApp.contract.test.ts
npm.cmd run typecheck
```

Expected: PASS.

---

## Task 5: Implement Reports-to-Graph Focus Workflow

**Files:**
- Modify: `frontend/src/components/CommandCenterApp.tsx`
- Modify: `frontend/src/components/ReportWorkspace.tsx`
- Modify: `frontend/src/components/OperationalReportsPanel.tsx`
- Create: `frontend/src/components/GraphFocusBanner.tsx`
- Test: `frontend/src/components/ReportWorkspace.contract.test.ts`
- Test: `frontend/src/reports/operational.test.ts`

- [ ] **Step 1: Write the failing contract test**

Update `frontend/src/components/ReportWorkspace.contract.test.ts`:

```ts
it("supports report-to-graph focus navigation", () => {
  const source = readFileSync(resolve(__dirname, "ReportWorkspace.tsx"), "utf-8");

  expect(source).toContain("onFocusGraphItem");
  expect(source).toContain("OperationalReportsPanel");
});
```

Update `CommandCenterApp.contract.test.ts`:

```ts
it("switches from reports to graph focus when report evidence is selected", () => {
  const source = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");

  expect(source).toContain("focusGraphItemFromReport");
  expect(source).toContain('setViewMode("analyst")');
  expect(source).toContain("focusedFromReport");
  expect(source).toContain("GraphFocusBanner");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd frontend
npm.cmd run test -- ReportWorkspace.contract.test.ts CommandCenterApp.contract.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Add `GraphFocusBanner.tsx`**

Props:

```ts
type Props = {
  visible: boolean;
  label: string;
  onBackToReports: () => void;
  onClearFocus: () => void;
};
```

Render a compact banner above the stage when `visible` is true:
- label text: "Focused from report: {label}"
- `Back to Reports`
- `Clear focus`

- [ ] **Step 4: Wire graph focus in `CommandCenterApp.tsx`**

Add state:

```ts
const [focusedFromReport, setFocusedFromReport] = useState<{ label: string } | null>(null);
```

Add:

```ts
function focusGraphItemFromReport(item: GraphNode | GraphLink) {
  if ("relationship" in item) {
    selectLink(item);
    setFocusedFromReport({ label: item.relationship });
  } else {
    selectNode(item);
    setFocusedFromReport({ label: item.name });
  }
  setViewMode("analyst");
}
```

Add:

```ts
function backToReports() {
  setViewMode("reports");
}
```

Update `clearSelection()` to also clear `focusedFromReport`.

- [ ] **Step 5: Update report components**

In `ReportWorkspace.tsx`, change props to:

```ts
onFocusGraphItem: (item: GraphNode | GraphLink) => void;
```

Pass it to `OperationalReportsPanel`.

In `OperationalReportsPanel.tsx`, replace direct `onSelectNode`/`onSelectLink` calls with `onFocusGraphItem`.

- [ ] **Step 6: Add visible affordance text**

Inside report rows add:

```tsx
<em>Focus evidence</em>
```

Style:

```css
.report-row em {
  color: #73c6e8;
  font-style: normal;
  font-size: 0.66rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
cd frontend
npm.cmd run test -- ReportWorkspace.contract.test.ts CommandCenterApp.contract.test.ts operational.test.ts
npm.cmd run typecheck
```

Expected: PASS.

---

## Task 6: Improve 3D Risk Concentration Usefulness

**Files:**
- Create: `frontend/src/graph/riskConcentration.ts`
- Test: `frontend/src/graph/riskConcentration.test.ts`
- Modify: `frontend/src/components/SpatialCanvas3D.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/graph/riskConcentration.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { summarizeRiskConcentration } from "./riskConcentration";
import type { GraphLink, GraphNode } from "../api/types";

const nodes: GraphNode[] = [
  { id: "a", name: "Authentication", riskKind: "fragility", riskScore: 16 },
  { id: "b", name: "Portal", riskKind: "standard", riskScore: 2 },
  { id: "c", name: "Migration", riskKind: "high", riskScore: 18 },
];

const links: GraphLink[] = [
  { id: "l1", source: "a", target: "b", relationship: "blocks", diamond: "Risk", riskKind: "high", riskScore: 16 },
  { id: "l2", source: "b", target: "c", relationship: "depends", diamond: "Risk", riskKind: "structural", riskScore: 12 },
];

describe("summarizeRiskConcentration", () => {
  it("identifies concentration around high-risk nodes and links", () => {
    const summary = summarizeRiskConcentration(nodes, links);

    expect(summary.primaryNode?.name).toBe("Migration");
    expect(summary.highRiskLinkCount).toBe(2);
    expect(summary.caption).toContain("2 high-risk paths");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend
npm.cmd run test -- riskConcentration.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement `riskConcentration.ts`**

Create:

```ts
import type { GraphLink, GraphNode } from "../api/types";

export type RiskConcentrationSummary = {
  primaryNode: GraphNode | null;
  highRiskLinkCount: number;
  caption: string;
};

export function summarizeRiskConcentration(nodes: GraphNode[], links: GraphLink[]): RiskConcentrationSummary {
  const primaryNode = [...nodes].sort((a, b) => b.riskScore - a.riskScore)[0] || null;
  const highRiskLinkCount = links.filter((link) => link.riskScore >= 12 || link.riskKind === "high").length;
  const caption = primaryNode
    ? `${highRiskLinkCount.toLocaleString()} high-risk paths concentrate around ${primaryNode.name}.`
    : "No risk concentration available.";

  return { primaryNode, highRiskLinkCount, caption };
}
```

- [ ] **Step 4: Use summary in `SpatialCanvas3D.tsx`**

Add:

```ts
const riskSummary = useMemo(() => summarizeRiskConcentration(props.nodes, props.links), [props.nodes, props.links]);
```

Render near the graph stage:

```tsx
<div className="risk-concentration-hud">
  <span>Risk concentration</span>
  <strong>{riskSummary.primaryNode?.name || "No dominant node"}</strong>
  <p>{riskSummary.caption}</p>
</div>
```

- [ ] **Step 5: Tune 3D encoding**

Changes in `SpatialCanvas3D.tsx`:
- Reduce standard link opacity in `linkOpacity` from `0.22` to `0.14`.
- Increase selected/context link opacity slightly.
- Make default `labelMode` `"selected-neighbors"` when a selection exists, otherwise `"top-risks"`.
- Reduce grid visual weight in `Atmosphere` by changing grid colors to lower contrast.

- [ ] **Step 6: Style 3D HUD**

Add:

```css
.risk-concentration-hud {
  position: absolute;
  left: 16px;
  bottom: 54px;
  max-width: 320px;
  border: 1px solid rgba(245, 201, 95, 0.22);
  border-radius: 8px;
  padding: 10px 12px;
  background: rgba(7, 10, 14, 0.72);
  backdrop-filter: blur(12px);
}

.risk-concentration-hud span {
  color: #f5c95f;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 0.58rem;
  font-weight: 800;
}

.risk-concentration-hud strong {
  display: block;
  margin-top: 4px;
  color: #edf4f7;
}

.risk-concentration-hud p {
  margin: 5px 0 0;
  color: #c3d0d8;
  font-size: 0.74rem;
  line-height: 1.35;
}
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
cd frontend
npm.cmd run test -- riskConcentration.test.ts SpatialCanvas3D.contract.test.ts
npm.cmd run typecheck
```

Expected: PASS.

---

## Task 7: Design-System Cleanup

**Files:**
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/ui/uiContracts.test.ts`
- Modify components opportunistically:
  - `ModeToolbar.tsx`
  - `SelectedEvidencePanel.tsx`
  - `ReportWorkspace.tsx`
  - `OperationalReportsPanel.tsx`
  - `GeneratedReportsPanel.tsx`

- [ ] **Step 1: Write source contract test**

Create `frontend/src/ui/uiContracts.test.ts`:

```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend
npm.cmd run test -- uiContracts.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Add CSS primitives**

Add to `frontend/src/styles.css` near common controls:

```css
.dm-panel {
  border: 1px solid rgba(155, 174, 188, 0.16);
  background: rgba(255, 255, 255, 0.03);
  border-radius: 8px;
}

.dm-button {
  border: 1px solid rgba(155, 174, 188, 0.2);
  color: #edf4f7;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 6px;
  padding: 8px 11px;
  text-decoration: none;
}

.dm-button-primary {
  border-color: rgba(115, 198, 232, 0.64);
  background: rgba(115, 198, 232, 0.14);
}

.dm-button-quiet {
  color: #91a2af;
  background: rgba(255, 255, 255, 0.02);
}

.dm-chip {
  display: inline-flex;
  align-items: center;
  border: 1px solid rgba(155, 174, 188, 0.18);
  border-radius: 999px;
  color: #f5c95f;
  background: rgba(245, 201, 95, 0.08);
  padding: 4px 8px;
  font-size: 0.68rem;
}

.dm-status {
  border: 1px solid rgba(155, 174, 188, 0.12);
  border-radius: 6px;
  padding: 8px 9px;
  background: rgba(5, 7, 10, 0.4);
}

.dm-tabs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
}
```

- [ ] **Step 4: Apply primitives incrementally**

Apply classes without deleting existing specific classes:
- `ModeToolbar` buttons use `dm-button`.
- Selected evidence badges use `dm-chip`.
- Report panels use `dm-panel`.
- Report tabs add `dm-tabs`.

Do not rewrite the full CSS file in one pass.

- [ ] **Step 5: Run tests**

Run:

```bash
cd frontend
npm.cmd run test -- uiContracts.test.ts CommandCenterApp.contract.test.ts ReportWorkspace.contract.test.ts
npm.cmd run typecheck
```

Expected: PASS.

---

## Task 8: Browser/E2E Acceptance Coverage

**Files:**
- Modify: `frontend/e2e/app-v2.spec.ts`
- Build output: generated by `npm.cmd run build`, not manually edited.

- [ ] **Step 1: Add Playwright checks**

Add tests that verify:
- `/app-v2` shows `3D Canvas`, `Analyst Map`, `Reports`, `Configuration`.
- switching to `Reports` hides graph-only lens/search surfaces.
- clicking a report row with mocked operational data switches to Analyst Map and shows selected evidence.
- opening and closing `Configuration` does not change current view mode.

- [ ] **Step 2: Run e2e locally**

Run:

```bash
cd frontend
npm.cmd run e2e
```

Expected:
- PASS if WebGL browser teardown is stable.
- If the known WebGL teardown flake appears, rerun the failing test once and record the isolated result.

---

## Task 9: Verification and Commit Strategy

**Focused checks after each task:**

```bash
cd frontend
npm.cmd run test -- <changed-test-file>
npm.cmd run typecheck
```

**Full frontend checks before commit:**

```bash
cd frontend
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
```

**Backend/static checks before commit:**

```bash
python -m pytest -q tests/test_app_v2_static.py tests/test_frontend_v2_contract.py
```

**Optional browser checks:**

```bash
cd frontend
npm.cmd run e2e
```

**Commit slices:**

1. `refactor: add mode-aware command center chrome`
2. `feat: redesign selected evidence panel`
3. `feat: connect reports to graph focus`
4. `feat: improve 3d risk concentration cues`
5. `style: consolidate v2 design primitives`

---

## Parallel-Agent Strategy For Coding

Use subagents only after implementation starts. Suggested split:

### Worker A: Mode Chrome And Toolbar

Owns:
- `frontend/src/ui/modeChrome.ts`
- `frontend/src/components/ModeToolbar.tsx`
- related CommandCenterApp wiring

Does not edit:
- `SpatialCanvas3D.tsx`
- report components

### Worker B: Selected Evidence

Owns:
- `frontend/src/ui/evidenceViewModel.ts`
- `frontend/src/components/SelectedEvidencePanel.tsx`
- selected-evidence styling

Does not edit:
- report navigation
- 3D rendering

### Worker C: 3D Usefulness

Owns:
- `frontend/src/graph/riskConcentration.ts`
- `frontend/src/components/SpatialCanvas3D.tsx`
- 3D HUD styling

Does not edit:
- report components
- config/ingestion/deletion flows

### Main Agent: Integration

Owns:
- `CommandCenterApp.tsx` integration conflicts
- `ReportWorkspace.tsx`
- `OperationalReportsPanel.tsx`
- final verification and build

---

## Risk Controls

- Do not touch backend API schemas.
- Do not change ingestion, deletion, vault clear, configuration persistence, report generation, or export endpoints.
- Do not replace Three.js or Sigma.js in this pass.
- Do not manually edit `static/app-v2`; run `npm.cmd run build`.
- Keep the legacy root UI at `/` working.
- Avoid broad CSS rewrites; add primitives and migrate active components incrementally.

---

## Self-Review

Spec coverage:
- Information hierarchy: Task 1 and Task 4.
- Selected evidence redesign: Task 2 and Task 3.
- 3D canvas usefulness: Task 6.
- Reports-to-graph integration: Task 5.
- Design-system cleanup: Task 7.
- Verification: Task 8 and Task 9.

Placeholder scan:
- No task uses "TBD", "TODO", or open-ended implementation placeholders.
- Each task includes concrete files, tests, commands, and expected results.

Type consistency:
- `ViewMode` is defined once in `modeChrome.ts` and imported by components.
- `GraphNode | GraphLink` focus handoff is used consistently for report-to-graph navigation.
- Evidence model separates link and node inputs with a discriminated `selectionType`.
