import { expect, type Page, test } from "@playwright/test";

const mockDocument = {
  id: "doc_e2e_mock",
  name: "e2e_test_document.md",
  created_at: "2026-05-31T10:00:00Z",
};

const mockCanvas = {
  nodes: [
    { id: "auth", name: "Central Authentication Service", label: "service" },
    { id: "portal", name: "Customer Portal", label: "application" },
    { id: "gateway", name: "API Gateway", label: "service" },
    { id: "migration", name: "Cloud Migration", label: "milestone" },
  ],
  edges: [
    { source: "auth", target: "gateway", relationship: "supports" },
    { source: "gateway", target: "portal", relationship: "routes" },
    { source: "migration", target: "portal", relationship: "predecessor" },
  ],
  friction_lines: [
    {
      source: "auth",
      target: "portal",
      diamond: "Authentication and portal launch have a high-risk dependency conflict.",
      severity: 4,
      probability: 4,
      finding: {
        title: "Cloud migration starts before security gate can be passed",
        risk_type: "approval gate",
        affected_entity: "Cloud Migration Start Gate",
        blocked_work: "migration start approval and board readiness sign-off",
        blocking_condition: "security certification, penetration testing, and network segmentation completion",
        evidence_summary: "The source states that Cloud Migration starts before the security certification path can be completed. The certification path depends on penetration testing, and penetration testing cannot start until the network segmentation upgrade has completed.",
        why_it_matters: "The programme could be forced to begin migration without a valid security gate, creating compliance, rework, and approval risk. This is intentionally long enough to reproduce the selected-evidence sidebar height seen in production.",
        recommended_action: "Move Cloud Migration after certification or formally accept the security-gate risk at board level.",
        confidence: 0.86,
        assumptions: ["Security certification is mandatory before migration starts."],
      },
    },
  ],
  chronological_friction_lines: [
    {
      source: "migration",
      target: "portal",
      diamond: "Cloud migration is scheduled too close to portal launch.",
      severity: 4,
      probability: 3,
    },
  ],
  fragility_lines: [
    {
      hub_node_id: "auth",
      insight: "Authentication is a single point of failure.",
      dependency_count: 6,
      cascade_nodes: ["API Gateway", "Customer Portal"],
    },
  ],
};

async function mockAppApis(page: Page) {
  await page.route("**/api/v1/documents", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: { documents: [mockDocument] } });
      return;
    }
    await route.fallback();
  });
  await page.route("**/api/v1/documents/doc_e2e_mock", async (route) => {
    await route.fulfill({ json: { status: "deleted", document_id: mockDocument.id } });
  });
  await page.route("**/api/v1/canvas/doc_e2e_mock", async (route) => {
    await route.fulfill({ json: mockCanvas });
  });
  await page.route("**/api/v1/reports/friction-queue/doc_e2e_mock", async (route) => {
    await route.fulfill({
      json: {
        friction_queue: [
          { type: "structural", source: "auth", target: "portal", diamond: mockCanvas.friction_lines[0].diamond, severity: 4, probability: 4 },
        ],
      },
    });
  });
  await page.route("**/api/v1/reports/bottlenecks/doc_e2e_mock", async (route) => {
    await route.fulfill({ json: { bottlenecks: [{ id: "auth", name: "Central Authentication Service", label: "service", dependency_count: 6 }] } });
  });
  await page.route("**/api/v1/reports/schedule-collapse/doc_e2e_mock", async (route) => {
    await route.fulfill({
      json: {
        schedule_collapse: [
          {
            predecessor_name: "Cloud Migration",
            successor_name: "Customer Portal",
            pred_end_date: "2026-08-10",
            succ_start_date: "2026-08-11",
            days_at_risk: 12,
            analysis: mockCanvas.chronological_friction_lines[0].diamond,
          },
        ],
      },
    });
  });
  await page.route("**/api/v1/reports/risk-matrix/doc_e2e_mock", async (route) => {
    await route.fulfill({
      json: {
        risk_matrix: [
          { type: "structural", source: "auth", target: "portal", analysis: mockCanvas.friction_lines[0].diamond, severity: 4, probability: 4 },
        ],
      },
    });
  });
  await page.route("**/api/v1/reports/executive-summary/doc_e2e_mock", async (route) => {
    await route.fulfill({ json: { cached: true, report: { executive_summary: "Mock executive summary." } } });
  });
  await page.route("**/api/v1/reports/narrative/doc_e2e_mock", async (route) => {
    await route.fulfill({ json: { cached: false } });
  });
  await page.route("**/api/v1/reports/risk-simulation/doc_e2e_mock", async (route) => {
    await route.fulfill({ json: { cached: true, result: { monte_carlo: { available: true, p95_delay_days: 45 } } } });
  });
  await page.route("**/api/v1/config", async (route) => {
    await route.fulfill({
      json: {
        LLM_PROVIDER: "openrouter",
        OPENAI_API_KEY: "",
        OPENROUTER_API_KEY: "",
        FAST_MODEL: "mock-fast",
        SMART_MODEL: "mock-smart",
        VAULT_PATH: "./vaults",
      },
    });
  });
}

async function openFirstDocument(page: Page) {
  await mockAppApis(page);
  await page.goto("/app-v2");
  await expect(page.getByText("COMMAND CENTER")).toBeVisible();
  const firstDocument = page.locator(".doc-button").first();
  await expect(firstDocument).toBeVisible();
  await firstDocument.click();
  await expect(page.getByText(/nodes analysed/i)).toBeVisible();
}

async function openRiskFixtureDocument(page: Page) {
  await mockAppApis(page);
  await page.goto("/app-v2");
  await expect(page.getByText("COMMAND CENTER")).toBeVisible();
  const fixtureDocument = page.locator(".doc-button", { hasText: "e2e_test_document.md" }).first();
  await expect(fixtureDocument).toBeVisible();
  await fixtureDocument.click();
  await expect(page.getByText(/nodes analysed/i)).toBeVisible();
  await expect(page.locator(".attention-item").first()).toBeVisible();
}

test.describe("Diamond Miner app-v2", () => {
  test.afterEach(async ({ page }) => {
    await page.goto("about:blank").catch(() => undefined);
    await page.close().catch(() => undefined);
  });

  test("loads the command center and renders the 3D canvas controls", async ({ page }) => {
    await openFirstDocument(page);

    await expect(page.getByRole("button", { name: "3D Canvas" })).toHaveClass(/active/);
    await expect(page.getByRole("button", { name: "Analyst Map" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Reset View" })).toBeVisible();
    await expect(page.locator(".label-density")).toBeVisible();
    await expect(page.locator(".metrics-strip")).toContainText("Nodes");
  });

  test("shows document deletion controls without deleting when cancelled", async ({ page }) => {
    await openFirstDocument(page);

    await expect(page.locator(".doc-delete-action").first()).toBeVisible();
    await page.locator(".doc-delete-action").first().click();
    await expect(page.locator(".doc-confirm-row")).toContainText("Delete this document?");
    await page.locator(".doc-confirm-row").getByRole("button", { name: "Cancel" }).click();
    await expect(page.locator(".doc-confirm-row")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Clear Vault" })).toBeVisible();
  });

  test("shows ingestion telemetry while upload status is processing", async ({ page }) => {
    await mockAppApis(page);
    await page.route("**/api/v1/ingest", async (route) => {
      await route.fulfill({ json: { job_id: "job_mock_progress", document_id: "doc_mock_progress", status: "pending" } });
    });
    await page.route("**/api/v1/status/job_mock_progress", async (route) => {
      await route.fulfill({ json: { status: "processing", document_id: "doc_mock_progress", log: ["Parsing source file", "Extracting dependency graph"] } });
    });

    await page.goto("/app-v2");
    await page.locator('.upload-drop input[type="file"]').setInputFiles({
      name: "progress_fixture.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("# Progress fixture\n\nA depends on B."),
    });

    await expect(page.locator(".ingestion-progress-panel")).toContainText("progress_fixture.md");
    await expect(page.locator(".ingestion-progress-panel")).toContainText("Processing");
    await expect(page.locator(".ingestion-progress-panel")).toContainText("Extracting dependency graph");
  });

  test("switches to Analyst Map and keeps selected risk evidence visible", async ({ page }) => {
    await openRiskFixtureDocument(page);

    await page.getByRole("button", { name: "Analyst Map" }).click();
    await expect(page.locator(".sigma-container canvas").first()).toBeVisible();
    await expect(page.locator(".analyst-map-hud")).toContainText("nodes");
    await expect(page.locator(".analyst-map-hud")).toContainText("No selection");

    await page.locator(".attention-item").first().click();
    await expect(page.locator(".analyst-map-hud")).toContainText("Selection focused");
    await expect(page.locator(".attention-item.active")).toHaveCount(1);
    await expect(page.locator(".panel-section").first()).not.toContainText("Select a node or risk path");

    await page.locator(".analyst-map-hud").getByRole("button", { name: "Clear selection" }).click();
    await expect(page.locator(".analyst-map-hud")).toContainText("No selection");
    await expect(page.locator(".attention-item.active")).toHaveCount(0);
  });

  test("keeps the label density dropdown readable", async ({ page }) => {
    await openFirstDocument(page);

    const contrast = await page.locator(".label-density").evaluate((select) => {
      const option = select.querySelector('option[value="selected-neighbors"]');
      const selected = select.querySelector("option:checked");
      const selectStyle = getComputedStyle(select);
      const optionStyle = option ? getComputedStyle(option) : null;
      const selectedStyle = selected ? getComputedStyle(selected) : null;
      return {
        selectColor: selectStyle.color,
        selectBackground: selectStyle.backgroundColor,
        optionColor: optionStyle?.color,
        optionBackground: optionStyle?.backgroundColor,
        selectedColor: selectedStyle?.color,
        selectedBackground: selectedStyle?.backgroundColor,
      };
    });

    expect(contrast.selectColor).toBe("rgb(237, 244, 247)");
    expect(contrast.optionColor).toBe("rgb(237, 244, 247)");
    expect(contrast.optionBackground).not.toBe("rgb(255, 255, 255)");
    expect(contrast.selectedColor).toBe("rgb(255, 255, 255)");
    expect(contrast.selectedBackground).not.toBe("rgb(255, 255, 255)");
  });

  test("opens the wide reports workspace without using the right rail for report content", async ({ page }) => {
    await openFirstDocument(page);

    await page.getByRole("button", { name: "Reports", exact: true }).click();
    await expect(page.locator(".report-workspace")).toBeVisible();
    await expect(page.locator(".metrics-strip")).toHaveCount(0);
    await expect(page.locator(".lens-bar")).toHaveCount(0);
    await expect(page.locator(".node-search-panel")).toHaveCount(0);
    await expect(page.locator(".report-workspace")).toContainText("Operational Reports");
    await expect(page.locator(".report-workspace")).toContainText("Generated Intelligence");
    await expect(page.locator(".report-workspace .operational-report-panel.workspace")).toBeVisible();
    await expect(page.locator(".report-workspace .generated-report-panel.workspace")).toBeVisible();
    await expect(page.locator(".command-actions")).toContainText("PDF Export");
    await expect(page.locator(".command-actions")).toContainText("Word Export");
    await expect(page.locator(".insight-panel")).not.toBeVisible();
    await expect(page.locator(".insight-panel")).not.toContainText("Report Channels");
  });

  test("keeps loaded command chrome compact at a medium viewport", async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 900 });
    await openFirstDocument(page);

    const chromeHeight = await page.locator(".top-command").evaluate((element) => element.getBoundingClientRect().height);
    const stageHeight = await page.locator(".stage-shell").evaluate((element) => element.getBoundingClientRect().height);

    expect(chromeHeight).toBeLessThanOrEqual(145);
    expect(stageHeight).toBeGreaterThanOrEqual(500);
    await expect(page.getByRole("link", { name: "PDF Export" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Word Export" })).toBeVisible();
  });

  test("focuses report evidence in Analyst Map and can return to Reports", async ({ page }) => {
    await openRiskFixtureDocument(page);

    await page.getByRole("button", { name: "Reports", exact: true }).click();
    await expect(page.locator(".report-workspace")).toBeVisible();

    const firstReportRow = page.locator(".operational-report-panel.workspace .report-row").first();
    await expect(firstReportRow).toBeVisible();
    await expect(firstReportRow).toContainText("Focus evidence");
    await firstReportRow.click();

    await expect(page.getByRole("button", { name: "Analyst Map" })).toHaveClass(/active/);
    await expect(page.locator(".graph-focus-banner")).toContainText("Focused from report");
    await expect(page.locator(".selected-evidence-panel")).toContainText("Selected Evidence");
    await expect(page.locator(".selected-evidence-panel")).not.toContainText("Select a node or risk path");
    await expect(page.locator(".analyst-map-hud")).toBeVisible();

    const analystLayout = await page.evaluate(() => {
      const stage = document.querySelector(".stage-shell");
      const search = document.querySelector(".node-search-panel");
      const sigma = document.querySelector(".sigma-container");
      return {
        stageTop: stage?.getBoundingClientRect().top ?? 9999,
        searchHeight: search?.getBoundingClientRect().height ?? 9999,
        sigmaTop: sigma?.getBoundingClientRect().top ?? 9999,
        viewportHeight: window.innerHeight,
      };
    });
    expect(analystLayout.searchHeight).toBeLessThan(90);
    expect(analystLayout.stageTop).toBeLessThan(analystLayout.viewportHeight - 180);
    expect(analystLayout.sigmaTop).toBeLessThan(analystLayout.viewportHeight - 160);

    await page.getByRole("button", { name: "Back to Reports" }).first().click();
    await expect(page.getByRole("button", { name: "Reports", exact: true })).toHaveClass(/active/);
    await expect(page.locator(".report-workspace")).toBeVisible();
  });

  test("keeps the current mode when configuration is opened and closed", async ({ page }) => {
    await openFirstDocument(page);

    await page.getByRole("button", { name: "Reports", exact: true }).click();
    await expect(page.getByRole("button", { name: "Reports", exact: true })).toHaveClass(/active/);
    await page.getByRole("button", { name: "Configuration" }).click();
    await expect(page.locator(".config-drawer.open")).toBeVisible();
    await page.locator(".config-drawer").getByRole("button", { name: "Close" }).click();

    await expect(page.getByRole("button", { name: "Reports", exact: true })).toHaveClass(/active/);
    await expect(page.locator(".report-workspace")).toBeVisible();
  });

  test("keeps reports usable at a narrower viewport without horizontal overflow", async ({ page }) => {
    await page.setViewportSize({ width: 900, height: 900 });
    await openRiskFixtureDocument(page);

    await page.getByRole("button", { name: "Reports", exact: true }).click();
    await expect(page.locator(".report-workspace")).toBeVisible();
    await expect(page.locator(".report-workspace-grid")).toBeVisible();
    await expect(page.locator(".insight-panel")).not.toBeVisible();

    const layout = await page.evaluate(() => {
      const rootOverflow = document.documentElement.scrollWidth - document.documentElement.clientWidth;
      const rowList = document.querySelector(".operational-report-panel.workspace .report-row-list");
      const stage = document.querySelector(".stage-shell.reports-stage");
      const rowStyle = rowList ? getComputedStyle(rowList) : null;
      const stageStyle = stage ? getComputedStyle(stage) : null;
      return {
        rootOverflow,
        rowOverflowY: rowStyle?.overflowY,
        stageOverflowY: stageStyle?.overflowY,
      };
    });
    expect(layout.rootOverflow).toBeLessThanOrEqual(2);
    expect(layout.rowOverflowY).not.toBe("auto");
    expect(layout.stageOverflowY).toBe("auto");

    await expect(page.locator(".report-workspace-panel").first()).toBeVisible();
  });
});
