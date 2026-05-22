import { test, expect } from '@playwright/test';
import { signInViaDevBypass } from './_helpers';

/**
 * TDD: from the Dashboard, click "Continue last lesson", land on Lesson Intro,
 * click "Back to catalog" — should return to the Dashboard (the origin), NOT
 * to the lesson catalog page.
 */
test('back-to-catalog from Lesson Intro returns to dashboard when arrived from dashboard', async ({
  page,
}) => {
  await signInViaDevBypass(page);
  await page.waitForURL(/\/dashboard$/);

  // Click Continue last lesson
  const continueLink = page.locator('[data-testid="continue-last-lesson"]');
  await expect(continueLink).toBeVisible();
  await continueLink.click();
  await page.waitForURL(/\/lessons\/[^/]+$/);

  // Click Back to catalog — semantic should be "back to where you came from"
  await page.locator('[data-testid="lesson-back-to-catalog"]').click();

  // Should return to dashboard (the entry point), not /lessons.
  await page.waitForLoadState('networkidle');
  expect(page.url()).toContain('/dashboard');
});

/**
 * Inverse: when the user navigates DIRECTLY to a Lesson Intro (e.g. from
 * /lessons catalog or a deep link), the back affordance should go to the
 * catalog, since that's the natural up-tree.
 */
test('back-to-catalog goes to /lessons when arrived directly', async ({ page }) => {
  await signInViaDevBypass(page);
  await page.goto('/lessons/lesson-1');

  await page.locator('[data-testid="lesson-back-to-catalog"]').click();

  await page.waitForLoadState('networkidle');
  expect(page.url()).toContain('/lessons');
  expect(page.url()).not.toContain('/lessons/lesson-1');
});
