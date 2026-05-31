# Report Workspace Layout Design

## Context

The V2 command center currently places operational reports, generated intelligence, report exports, selected evidence, and critical attention in the same slim right rail. This makes operational and generated report content hard to read, especially long friction analyses, schedule collapse explanations, and generated report previews. The center workspace has much more available space and should carry report-reading workflows.

## Chosen Direction

Use **A. Reports Workspace** from the visual companion.

Add a third main workspace mode beside `3D Canvas` and `Analyst Map`:

```text
3D Canvas | Analyst Map | Reports
```

When `Reports` is active, the center stage becomes a wide reports workspace. The existing 3D and Analyst Map modes remain graph-first.

## Goals

- Make Operational Reports readable in the main center workspace.
- Make Generated Intelligence readable in the main center workspace.
- Keep backend API contracts unchanged.
- Preserve existing report item click behavior: report rows still select the corresponding graph node/link and update Selected Evidence.
- Keep the right rail useful by narrowing it back to evidence, critical attention, and export channels.
- Keep layout responsive at desktop and narrower widths.

## Non-Goals

- Do not rewrite backend report endpoints.
- Do not change report data schemas.
- Do not replace legacy `/`.
- Do not redesign generated report content structure beyond giving it a wider surface.
- Do not trigger live report generation during automated browser tests.

## UI Structure

### Top Command

Add `Reports` as a view button:

```text
3D Canvas | Analyst Map | Reports | Export PDF
```

The app view mode becomes:

```ts
type ViewMode = "spatial" | "analyst" | "reports";
```

### Center Workspace

For `spatial` and `analyst`, the center workspace remains graph focused.

For `reports`, render a full-width report workspace inside the existing `stage-shell`.

The report workspace contains:

- A header with document context and report purpose.
- A wide Operational Reports panel.
- A wide Generated Intelligence panel.

Operational reports should retain the existing tab set:

```text
Friction Queue | Bottlenecks | Schedule Collapse | Risk Matrix
```

Generated Intelligence should retain the existing tab set:

```text
Executive Summary | Narrative Report | Risk Simulator
```

### Right Rail

Remove Operational Reports and Generated Intelligence from the slim right rail.

Keep:

- Selected Evidence.
- Critical Attention.
- Report Channels.

## Component Strategy

Reuse existing components:

- `OperationalReportsPanel`
- `GeneratedReportsPanel`

Extend `OperationalReportsPanel` with an optional display density/layout prop:

```ts
variant?: "rail" | "workspace";
```

The workspace variant should:

- Use wider rows.
- Allow larger max-height.
- Show slightly longer snippets.
- Use a larger Risk Matrix grid.

`GeneratedReportsPanel` can also accept:

```ts
variant?: "rail" | "workspace";
```

The workspace variant should:

- Allow taller report bodies.
- Use wider report cards.
- Use a two-column layout where appropriate.

Create a focused workspace wrapper component:

```text
frontend/src/components/ReportWorkspace.tsx
```

Responsibilities:

- Present report workspace heading/context.
- Render `OperationalReportsPanel` with `variant="workspace"`.
- Render `GeneratedReportsPanel` with `variant="workspace"`.
- Pass through graph selection callbacks.

## Testing

### Source/Contract Tests

Update `CommandCenterApp.contract.test.ts` to assert:

- `ViewMode` includes `reports`.
- `ReportWorkspace` is imported/rendered.
- The right rail no longer mounts `OperationalReportsPanel`.
- The right rail no longer mounts `GeneratedReportsPanel`.

Add or update component contract tests to assert:

- `ReportWorkspace` renders both report panels.
- `OperationalReportsPanel` supports `variant`.
- `GeneratedReportsPanel` supports `variant`.

### Browser E2E

Update Playwright tests to assert:

- `Reports` button is visible.
- Clicking `Reports` renders the report workspace.
- Operational Reports are visible in the center workspace.
- Generated Intelligence is visible in the center workspace.
- Right rail still shows Selected Evidence and Critical Attention.
- The e2e suite does not click Generate or Regenerate.

## Verification Commands

```powershell
cd frontend
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
npm.cmd run e2e
```

```powershell
python -m pytest -q tests/test_frontend_v2_contract.py tests/test_frontend_canvas_hud.py tests/test_app_v2_static.py
```

## Risks

- The right rail may still become tall if Critical Attention text is long; this pass does not solve that completely.
- Moving reports to the center workspace changes user navigation expectations, so the `Reports` button must be obvious.
- Existing tests that assume reports live in the right rail must be updated to match the new product direction.
