import { test, expect } from '@playwright/test';
import { signInViaDevBypass } from './_helpers';

/**
 * Aurora practice screen layout.
 *
 * The lesson plan presents only the full-sign stage, so the multi-stage drill
 * pill row is hidden. The rep counter and advance CTA still render.
 */

test('practice hides the multi-stage drill indicator for the full-sign plan', async ({ page }) => {
  await signInViaDevBypass(page);
  await page.goto('/lessons/lesson-1/practice');
  await expect(page.locator('[data-testid="page-practice"]')).toBeVisible();

  // With a single full-sign stage per sign, the pill row is not rendered.
  await expect(page.locator('[data-testid="drill-indicator"]')).toHaveCount(0);
});

test('practice surfaces rep counter and advance CTA', async ({ page }) => {
  await signInViaDevBypass(page);
  await page.goto('/lessons/lesson-1/practice');

  const repCounter = page.locator('[data-testid="rep-counter"]');
  await expect(repCounter).toBeVisible({ timeout: 5_000 });
  // Counter starts at 1 / 3 (or "Rep 1 of 3" — accept either).
  await expect(repCounter).toHaveText(/1.*(of|\/).*3/i);

  const gotIt = page.locator('[data-testid="self-report-got-it"]');
  await expect(gotIt).toBeVisible();
  // First rep of a multi-rep sign reads "Next rep (...)".
  await expect(gotIt).toHaveText(/next rep/i);
});
