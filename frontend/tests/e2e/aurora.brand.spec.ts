import { test, expect } from '@playwright/test';
import { signInViaDevBypass } from './_helpers';

/**
 * Aurora brand identity assertions.
 *
 * Verifies the new wordmark + brand-mark surface on the shells that own
 * them and confirms the practice route stays shell-less (its own header)
 * per the Aurora handoff. Landing is intentionally shell-less and uses
 * the gradient hero headline as its brand surface — we assert that
 * instead of a wordmark.
 */

test('landing renders the gradient hero (no shell wordmark by design)', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('[data-testid="page-landing"]')).toBeVisible();
  // Landing is shell-less; brand identity is the gradient hero headline.
  const gradientHero = page.locator('h1 .gradient-text');
  await expect(gradientHero).toBeVisible();
  await expect(gradientHero).toHaveText(/asl/i);
  // Wordmark should NOT be present here (Landing has no shell).
  await expect(page.locator('[data-testid="wordmark"]')).toHaveCount(0);
});

test('signin renders the AuthShell wordmark + brand-mark with "ASL PILOT"', async ({ page }) => {
  await page.goto('/signin');
  const wordmark = page.locator('[data-testid="wordmark"]');
  await expect(wordmark).toBeVisible();
  // aria-label carries the brand text; visible text is uppercased via CSS but
  // the source value is identical, so a case-insensitive match works for both.
  await expect(wordmark).toHaveText(/asl pilot/i);

  const brandMark = page.locator('[data-testid="brand-mark"]');
  await expect(brandMark).toBeVisible();
});

test('dashboard renders the AppShell wordmark + brand-mark', async ({ page }) => {
  await signInViaDevBypass(page);
  const wordmark = page.locator('[data-testid="wordmark"]');
  await expect(wordmark).toBeVisible();
  await expect(wordmark).toHaveText(/asl pilot/i);

  const brandMark = page.locator('[data-testid="brand-mark"]');
  await expect(brandMark).toBeVisible();
});

test('practice route is shell-less and uses the practice-specific header', async ({ page }) => {
  await signInViaDevBypass(page);
  await page.goto('/lessons/lesson-1/practice');
  await expect(page.locator('[data-testid="page-practice"]')).toBeVisible();

  // Practice owns its own 56px header with back-drill control.
  const practiceHeader = page.locator('[data-testid="practice-header"]');
  await expect(practiceHeader).toBeVisible();
  await expect(page.locator('[data-testid="practice-back-drill"]')).toBeVisible();

  // The global AppShell wordmark should NOT be present on the practice page.
  await expect(page.locator('[data-testid="wordmark"]')).toHaveCount(0);
  // And the global nav-logo link is also absent.
  await expect(page.locator('[data-testid="nav-logo"]')).toHaveCount(0);
});
