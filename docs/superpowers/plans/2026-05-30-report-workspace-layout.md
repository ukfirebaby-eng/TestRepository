# Report Workspace Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move operational and generated reports out of the slim right rail and into a wide first-class `Reports` workspace view in V2.

**Architecture:** Add a new `reports` view mode to `CommandCenterApp`, render a dedicated `ReportWorkspace` in the center stage, and reuse existing report panels with a `variant` prop for rail/workspace styling. The backend APIs and report schemas remain unchanged.

**Tech Stack:** React, TypeScript, Vite, CSS, Vitest contract tests, Playwright e2e tests, FastAPI static serving.

---

## File Structure

- Modify `frontend/src/components/CommandCenterApp.tsx`: add `reports` view mode, command button, center-stage report rendering, and remove report panels from the right rail.
- Create `frontend/src/components/ReportWorkspace.tsx`: wide report workspace wrapper.
- Modify `frontend/src/components/OperationalReportsPanel.tsx`: add `variant?: "rail" | "workspace"` and workspace-friendly classes/snippet length.
- Modify `frontend/src/components/GeneratedReportsPanel.tsx`: add `variant?: "rail" | "workspace"` and workspace-friendly classes.
- Modify `frontend/src/styles.css`: add report workspace layout and variant styling.
- Modify `frontend/src/components/CommandCenterApp.contract.test.ts`: contract for new view mode and right rail boundaries.
- Add `frontend/src/components/ReportWorkspace.contract.test.ts`: source contract for workspace composition.
- Modify `frontend/e2e/app-v2.spec.ts`: browser coverage for `Reports` workspace.

## Task 1: Add Failing Contracts For Reports Workspace

**Files:**
- Modify: `frontend/src/components/CommandCenterApp.contract.test.ts`
- Create: `frontend/src/components/ReportWorkspace.contract.test.ts`

- [ ] **Step 1: Update `CommandCenterApp.contract.test.ts`**

Add this test:

```ts
it("renders reports as a center workspace mode instead of right-rail panels", () => {
  const source = readFileSync(resolve(__dirname, "CommandCenterApp.tsx"), "utf-8");

  expect(source).toContain('type ViewMode = "spatial" | "analyst" | "reports"');
  expect(source).toContain("ReportWorkspace");
  expect(source).toContain('setViewMode("reports")');
  expect(source).toContain("Reports</button>");
  expect(source).toContain('<ReportWorkspace');
});
```

- [ ] **Step 2: Add `ReportWorkspace.contract.test.ts`**

Create:

```ts
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("ReportWorkspace contract", () => {
  it("uses wide operational and generated report panels", () => {
    const source = readFileSync(resolve(__dirname, "ReportWorkspace.tsx"), "utf-8");

    expect(source).toContain("OperationalReportsPanel");
    expect(source).toContain("GeneratedReportsPanel");
    expect(source).toContain('variant="workspace"');
    expect(source).toContain("report-workspace");
  });
});
```

- [ ] **Step 3: Run tests and verify red**

Run:

```powershell
cd frontend
npm.cmd run test -- src/components/CommandCenterApp.contract.test.ts src/components/ReportWorkspace.contract.test.ts
```

Expected: fails because `ReportWorkspace.tsx` does not exist and `CommandCenterApp` has no `reports` mode.

## Task 2: Create Report Workspace Component

**Files:**
- Create: `frontend/src/components/ReportWorkspace.tsx`

- [ ] **Step 1: Implement `ReportWorkspace.tsx`**

Create:

```tsx
import type { GraphLink, GraphNode, NormalizedGraph } from "../api/types";
import { GeneratedReportsPanel } from "./GeneratedReportsPanel";
import { OperationalReportsPanel } from "./OperationalReportsPanel";

type Props = {
  documentId: string;
  documentName: string;
  graph: NormalizedGraph;
  onSelectNode: (node: GraphNode) => void;
  onSelectLink: (link: GraphLink) => void;
};

export function ReportWorkspace({ documentId, documentName, graph, onSelectNode, onSelectLink }: Props) {
  return (
    <section className="report-workspace" aria-label="Reports workspace">
      <header className="report-workspace-header">
        <div>
          <p className="eyebrow">Reports workspace</p>
          <h2>{documentName}</h2>
        </div>
        <span>{graph.metrics.nodes.toLocaleString()} nodes analysed</span>
      </header>
      <div className="report-workspace-grid">
        <section className="report-workspace-panel operational">
          <p className="eyebrow">Operational Reports</p>
          <OperationalReportsPanel
            documentId={documentId}
            graph={graph}
            onSelectNode={onSelectNode}
            onSelectLink={onSelectLink}
            variant="workspace"
          />
        </section>
        <section className="report-workspace-panel generated">
          <p className="eyebrow">Generated Intelligence</p>
          <GeneratedReportsPanel documentId={documentId} documentName={documentName} variant="workspace" />
        </section>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Run contract tests**

Run:

```powershell
cd frontend
npm.cmd run test -- src/components/ReportWorkspace.contract.test.ts
```

Expected: may still fail until report panels support `variant`.

## Task 3: Add Report Panel Variants

**Files:**
- Modify: `frontend/src/components/OperationalReportsPanel.tsx`
- Modify: `frontend/src/components/GeneratedReportsPanel.tsx`

- [ ] **Step 1: Update `OperationalReportsPanel` props**

Change props to:

```ts
type Props = {
  documentId: string;
  graph: NormalizedGraph;
  onSelectNode: (node: GraphNode) => void;
  onSelectLink: (link: GraphLink) => void;
  variant?: "rail" | "workspace";
};
```

Change the function signature and class:

```tsx
export function OperationalReportsPanel({ documentId, graph, onSelectNode, onSelectLink, variant = "rail" }: Props) {
```

```tsx
<div className={`operational-report-panel ${variant}`}>
```

Change snippet use in report rows to:

```ts
const snippetLimit = variant === "workspace" ? 320 : 180;
```

Then call:

```tsx
<small>{snippet(item.diamond, "No analysis available.", snippetLimit)}</small>
```

Update `snippet` signature:

```ts
function snippet(text?: string, fallback = "No analysis available.", limit = 180) {
  if (!text) return fallback;
  return text.length > limit ? `${text.slice(0, limit - 3)}...` : text;
}
```

- [ ] **Step 2: Update `GeneratedReportsPanel` props**

Change props to:

```ts
type Props = {
  documentId: string;
  documentName?: string;
  variant?: "rail" | "workspace";
};
```

Change function signature and root class:

```tsx
export function GeneratedReportsPanel({ documentId, documentName, variant = "rail" }: Props) {
```

```tsx
<div className={`generated-report-panel ${variant}`}>
```

- [ ] **Step 3: Run TypeScript**

Run:

```powershell
cd frontend
npm.cmd run typecheck
```

Expected: passes.

## Task 4: Wire Reports Mode Into App Shell

**Files:**
- Modify: `frontend/src/components/CommandCenterApp.tsx`

- [ ] **Step 1: Import `ReportWorkspace`**

Add:

```ts
import { ReportWorkspace } from "./ReportWorkspace";
```

- [ ] **Step 2: Extend `ViewMode`**

Change:

```ts
type ViewMode = "spatial" | "analyst";
```

To:

```ts
type ViewMode = "spatial" | "analyst" | "reports";
```

- [ ] **Step 3: Add command button**

Add after `Analyst Map`:

```tsx
<button onClick={() => setViewMode("reports")} className={viewMode === "reports" ? "active" : ""}>Reports</button>
```

- [ ] **Step 4: Render report workspace in center stage**

Add in `stage-shell` after Analyst Map:

```tsx
{loadState === "ready" && graph && activeDocument && viewMode === "reports" && (
  <ReportWorkspace
    documentId={activeDocument.id}
    documentName={activeDocument.name}
    graph={graph}
    onSelectNode={selectNode}
    onSelectLink={selectLink}
  />
)}
```

- [ ] **Step 5: Remove report panels from right rail**

Delete the right-rail `panel-section` blocks that render:

```tsx
<OperationalReportsPanel ... />
```

And:

```tsx
<GeneratedReportsPanel ... />
```

Keep `Report Channels`.

- [ ] **Step 6: Run contracts**

Run:

```powershell
cd frontend
npm.cmd run test -- src/components/CommandCenterApp.contract.test.ts src/components/ReportWorkspace.contract.test.ts
```

Expected: passes.

## Task 5: Add Workspace Styling

**Files:**
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Add report workspace layout CSS**

Add:

```css
.report-workspace {
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 12px;
  padding: 16px;
  overflow: hidden;
  background: linear-gradient(145deg, rgba(7, 10, 14, 0.82), rgba(10, 15, 20, 0.9));
}
.report-workspace-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  border: 1px solid rgba(155, 174, 188, 0.16);
  border-radius: 8px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.035);
}
.report-workspace-header h2 {
  margin: 4px 0 0;
  font-size: 1.05rem;
}
.report-workspace-header span {
  color: #91a2af;
  font-size: 0.78rem;
}
.report-workspace-grid {
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 12px;
}
.report-workspace-panel {
  min-height: 0;
  border: 1px solid rgba(155, 174, 188, 0.16);
  border-radius: 8px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.03);
  overflow: hidden;
}
.operational-report-panel.workspace .report-row-list,
.generated-report-panel.workspace .generated-report-body {
  max-height: none;
  height: calc(100% - 48px);
}
.operational-report-panel.workspace .report-row {
  padding: 12px;
}
.operational-report-panel.workspace .report-row strong,
.generated-report-panel.workspace .generated-card strong {
  font-size: 0.92rem;
}
.generated-report-panel.workspace .generated-report-body {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  align-content: start;
}
.generated-report-panel.workspace .generated-empty,
.generated-report-panel.workspace .report-empty {
  grid-column: 1 / -1;
}
```

- [ ] **Step 2: Add responsive CSS**

Add:

```css
@media (max-width: 1180px) {
  .report-workspace-grid {
    grid-template-columns: 1fr;
    overflow-y: auto;
  }
}
```

- [ ] **Step 3: Run build**

Run:

```powershell
cd frontend
npm.cmd run build
```

Expected: build succeeds with the existing Three.js chunk-size warning.

## Task 6: Update Playwright E2E Coverage

**Files:**
- Modify: `frontend/e2e/app-v2.spec.ts`

- [ ] **Step 1: Add Reports workspace e2e test**

Add:

```ts
test("opens the wide reports workspace without using the right rail for report content", async ({ page }) => {
  await openFirstDocument(page);

  await page.getByRole("button", { name: "Reports" }).click();
  await expect(page.locator(".report-workspace")).toBeVisible();
  await expect(page.locator(".report-workspace")).toContainText("Operational Reports");
  await expect(page.locator(".report-workspace")).toContainText("Generated Intelligence");
  await expect(page.locator(".report-workspace .operational-report-panel.workspace")).toBeVisible();
  await expect(page.locator(".report-workspace .generated-report-panel.workspace")).toBeVisible();
  await expect(page.locator(".insight-panel")).toContainText("Selected Evidence");
  await expect(page.locator(".insight-panel")).toContainText("Critical Attention");
  await expect(page.locator(".insight-panel")).not.toContainText("Operational Reports");
  await expect(page.locator(".insight-panel")).not.toContainText("Generated Intelligence");
});
```

- [ ] **Step 2: Run e2e**

Run:

```powershell
cd frontend
npm.cmd run e2e
```

Expected: all Playwright tests pass.

## Task 7: Final Verification

**Files:**
- No new files beyond previous tasks.

- [ ] **Step 1: Run frontend checks**

Run:

```powershell
cd frontend
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
npm.cmd run e2e
```

Expected: all pass; build may show existing Three.js chunk-size warning.

- [ ] **Step 2: Run backend/static contracts**

Run:

```powershell
python -m pytest -q tests/test_frontend_v2_contract.py tests/test_frontend_canvas_hud.py tests/test_app_v2_static.py
```

Expected: all pass.

- [ ] **Step 3: Browser smoke**

Open:

```text
http://localhost:8000/app-v2
```

Verify manually:

- `Reports` appears beside `3D Canvas` and `Analyst Map`.
- Report workspace uses the center stage.
- Operational Reports are readable without the narrow right rail.
- Generated Intelligence is readable without the narrow right rail.
- Right rail still shows Selected Evidence, Critical Attention, and Report Channels.
- Do not click `Generate` or `Regenerate`.
