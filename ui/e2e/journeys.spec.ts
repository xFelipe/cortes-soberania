/**
 * E2E browser journeys — Onda 8
 *
 * Prerequisites (manual, once per machine):
 *   sudo npx playwright install-deps chromium
 *   npx playwright install chromium
 *
 * Tests are skipped automatically when Chromium is not installed so that CI
 * without sudo doesn't break. To run locally: pnpm exec playwright test
 *
 * Assumes:
 *   - `cs serve` (backend) running on http://localhost:8000
 *   - `pnpm dev` (Vite) started by webServer in playwright.config.ts
 */

import { test, expect, type Page } from "@playwright/test";
import { execSync } from "child_process";

// ---------------------------------------------------------------------------
// Skip if Chromium binary is not installed
// ---------------------------------------------------------------------------

function isBrowserInstalled(): boolean {
  try {
    // playwright stores chromium under ~/.cache/ms-playwright
    execSync("npx playwright --version", { stdio: "ignore" });
    const result = execSync("npx playwright install --dry-run chromium 2>&1", {
      encoding: "utf-8",
    });
    // If no install needed, browser exists
    return result.includes("no install needed") || result.includes("already installed");
  } catch {
    return false;
  }
}

const SKIP_REASON =
  "Chromium not installed — run: sudo npx playwright install-deps chromium && npx playwright install chromium";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function waitForInbox(page: Page) {
  // Inbox is at the root route ("/")
  await page.goto("/");
  await page.waitForLoadState("networkidle");
}

// ---------------------------------------------------------------------------
// Journey 1 — Approve a clip via card button
// ---------------------------------------------------------------------------

test("journey: approve clip from inbox card", async ({ page }) => {
  test.skip(!isBrowserInstalled(), SKIP_REASON);

  await waitForInbox(page);

  // Look for any clip card that has an "Aprovar" action button
  const approveBtn = page.locator('[data-testid="approve-clip"]').first();

  if (!(await approveBtn.isVisible({ timeout: 3000 }).catch(() => false))) {
    test.skip(true, "No metadata_ready clips in inbox — seed the DB first");
    return;
  }

  const cardTitle = await approveBtn
    .locator("xpath=ancestor::*[@data-testid='clip-card']")
    .first()
    .textContent()
    .catch(() => "unknown");

  await approveBtn.click();

  // Expect a success toast or the card to disappear from inbox
  const toast = page.locator('[data-sonner-toast]').first();
  await expect(toast).toBeVisible({ timeout: 5000 });

  console.log(`Approved clip card: ${cardTitle}`);
});

// ---------------------------------------------------------------------------
// Journey 2 — Bulk approve via toolbar
// ---------------------------------------------------------------------------

test("journey: bulk approve clips via toolbar", async ({ page }) => {
  test.skip(!isBrowserInstalled(), SKIP_REASON);

  await waitForInbox(page);

  // Select first checkbox (bulk select)
  const firstCheckbox = page.locator('[data-testid="clip-select"]').first();

  if (!(await firstCheckbox.isVisible({ timeout: 3000 }).catch(() => false))) {
    test.skip(true, "No selectable clips — seed the DB first");
    return;
  }

  await firstCheckbox.click();

  // Bulk toolbar should appear
  const bulkToolbar = page.locator('[data-testid="bulk-toolbar"]');
  await expect(bulkToolbar).toBeVisible({ timeout: 2000 });

  // Click bulk approve
  const bulkApprove = bulkToolbar.locator('button:has-text("Aprovar")');
  await bulkApprove.click();

  const toast = page.locator('[data-sonner-toast]').first();
  await expect(toast).toBeVisible({ timeout: 5000 });
});

// ---------------------------------------------------------------------------
// Journey 3 — Command palette restore (Ctrl+K)
// ---------------------------------------------------------------------------

test("journey: command palette opens with Ctrl+K", async ({ page }) => {
  test.skip(!isBrowserInstalled(), SKIP_REASON);

  await waitForInbox(page);

  // Open command palette
  await page.keyboard.press("Control+k");

  const palette = page.locator('[role="dialog"][data-slot="dialog-content"]').first();
  await expect(palette).toBeVisible({ timeout: 2000 });

  // Type to search
  await page.keyboard.type("restaurar");

  // Close
  await page.keyboard.press("Escape");
  await expect(palette).not.toBeVisible({ timeout: 1000 });
});
