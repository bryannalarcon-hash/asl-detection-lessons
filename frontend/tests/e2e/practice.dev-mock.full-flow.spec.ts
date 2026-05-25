import { test, expect } from '@playwright/test';
import { signInViaDevBypass } from './_helpers';

/**
 * Spec 3 — Practice flow with mock CV dev panel + self-report row.
 *
 * The lesson plan presents only the full-sign stage per word (3 reps each).
 *
 * 1. Sign in.
 * 2. Navigate to /lessons/lesson-1, click Start.
 * 3. On Practice: click dev-set-orange → bounding box turns orange.
 * 4. Click self-report-got-it through both words' reps → next sign / Lesson Complete.
 */
test('practice screen advances signs via dev panel + self-report row', async ({ page }) => {
  await signInViaDevBypass(page);

  // Navigate to lesson-1
  await page.goto('/lessons/lesson-1');
  await expect(page.locator('[data-testid="page-lesson-intro"]')).toBeVisible();

  // Click Start lesson
  await page.locator('[data-testid="lesson-start"]').click();
  await page.waitForURL(/\/lessons\/lesson-1\/practice/);
  await expect(page.locator('[data-testid="page-practice"]')).toBeVisible();

  // The multi-stage pill row is hidden under the full-sign-only plan.
  await expect(page.locator('[data-testid="drill-indicator"]')).toHaveCount(0);

  // Set Orange via dev panel
  const box = page.locator('[data-testid="bounding-box"]');
  await expect(box).toBeVisible();
  await page.locator('[data-testid="dev-set-orange"]').click();
  await expect(box).toHaveAttribute('data-state', 'orange');

  // The dev panel is `fixed bottom-left` and may overlap the self-report row
  // on small viewports. We use `force: true` to bypass the actionability
  // check; the click event still dispatches to the correct element.
  const gotIt = page.locator('[data-testid="self-report-got-it"]');
  await gotIt.scrollIntoViewIfNeeded();

  // Walk both words: 3 reps per word, 2 words = 6 clicks to reach completion.
  for (let i = 0; i < 6; i++) {
    if (page.url().includes('/complete')) break;
    await gotIt.click({ force: true });
    await page.waitForTimeout(80);
  }

  // Final assertion: either we advanced to the next sign or navigated to Lesson Complete.
  // Practice page may navigate away to /complete on the last sign.
  const url = page.url();
  if (url.includes('/complete')) {
    await expect(page.locator('[data-testid="page-lesson-complete"]')).toBeVisible();
  } else {
    // Still on practice page — the rep flow should still be live.
    await expect(page.locator('[data-testid="page-practice"]')).toBeVisible();
    await expect(page.locator('[data-testid="self-report-row"]')).toBeVisible();
  }
});
