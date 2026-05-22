import { test, expect } from '@playwright/test';

/**
 * Spec 1 — Sign-in via the dev bypass.
 *
 * Visit /signin, click [data-testid="dev-skip-login"], expect URL to match
 * /dashboard. Page should contain the dev user's display name "Dev User" OR
 * a generic welcome heading.
 */
test('dev bypass signs in and lands on the dashboard', async ({ page }) => {
  await page.goto('/signin');
  await expect(page).toHaveURL(/\/signin$/);

  const skipButton = page.locator('[data-testid="dev-skip-login"]');
  await expect(skipButton).toBeVisible();
  await skipButton.click();

  await page.waitForURL(/\/dashboard$/);
  await expect(page).toHaveURL(/\/dashboard$/);

  // Dashboard renders Welcome back, Dev User. heading.
  const h1 = page.locator('main[data-testid="page-dashboard"] h1');
  await expect(h1).toBeVisible();
  const text = await h1.textContent();
  expect(text).toMatch(/Welcome|Dev User/i);
});
