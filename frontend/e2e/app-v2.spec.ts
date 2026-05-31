import { expect, test } from "@playwright/test";

async function openFirstDocument(page: import("@playwright/test").Page) {
  await page.goto("/app-v2");
  await expect(page.getByText("COMMAND CENTER")).toBeVisible();
  const firstDocument = page.locator(".doc-button").first();
  await expect(firstDocument).toBeVisible();
  await firstDocument.click();
  await expect(page.getByText(/nodes analysed/i)).toBeVisible();
}

async function openRiskFixtureDocument(page: import("@playwright/test").Page) {
  await page.goto("/app-v2");
  await expect(page.getByText("COMMAND CENTER")).toBeVisible();
  const fixtureDocument = page.locator(".doc-button", { hasText: "e2e_test_document.md" }).first();
  await expect(fixtureDocument).toBeVisible();
  await fixtureDocument.click();
  await expect(page.getByText(/nodes analysed/i)).toBeVisible();
  await expect(page.locator(".attention-item").first()).toBeVisible();
}

test.describe("Diamond Miner app-v2", () => {
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

    await page.getByRole("button", { name: "Clear selection" }).click();
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

    await page.getByRole("button", { name: "Reports" }).click();
    await expect(page.locator(".report-workspace")).toBeVisible();
    await expect(page.locator(".report-workspace")).toContainText("Operational Reports");
    await expect(page.locator(".report-workspace")).toContainText("Generated Intelligence");
    await expect(page.locator(".report-workspace .operational-report-panel.workspace")).toBeVisible();
    await expect(page.locator(".report-workspace .generated-report-panel.workspace")).toBeVisible();
    await expect(page.locator(".command-actions")).toContainText("PDF Export");
    await expect(page.locator(".command-actions")).toContainText("Word Export");
    await expect(page.locator(".insight-panel")).toContainText("Selected Evidence");
    await expect(page.locator(".insight-panel")).toContainText("Critical Attention");
    await expect(page.locator(".insight-panel")).not.toContainText("Report Channels");
    await expect(page.locator(".insight-panel")).not.toContainText("Operational Reports");
    await expect(page.locator(".insight-panel")).not.toContainText("Generated Intelligence");
  });
});
