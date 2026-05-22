import { test, expect } from '@playwright/test';

/**
 * Aurora verify-email 6-digit code input.
 *
 * - Typing a digit auto-focuses the next cell.
 * - Filling all six cells navigates to /onboarding/welcome (300ms debounce).
 * - Backspace on an empty cell moves focus back to the previous cell.
 */

test('typing 6 digits walks focus forward and navigates to onboarding', async ({ page }) => {
  await page.goto('/verify-email');
  await expect(page.locator('[data-testid="page-verify-email"]')).toBeVisible();

  // Focus the first cell explicitly.
  const cell0 = page.locator('[data-testid="verify-code-0"]');
  await cell0.focus();
  await expect(cell0).toBeFocused();

  // Type each digit and verify focus advances to the next cell.
  for (let i = 0; i < 6; i++) {
    const cell = page.locator(`[data-testid="verify-code-${i}"]`);
    await cell.fill(String(i + 1));
    if (i < 5) {
      await expect(page.locator(`[data-testid="verify-code-${i + 1}"]`)).toBeFocused({
        timeout: 1_000,
      });
    }
  }

  // After the 6th digit, the page should navigate to /onboarding/welcome
  // (the component uses setTimeout(..., 300) after the last digit lands).
  await page.waitForURL(/\/onboarding\/welcome$/, { timeout: 2_000 });
  await expect(page).toHaveURL(/\/onboarding\/welcome$/);
});

test('backspace on an empty cell moves focus to the previous cell', async ({ page }) => {
  await page.goto('/verify-email');

  // Type 1, 2, 3 — cursor lands on cell 3.
  await page.locator('[data-testid="verify-code-0"]').focus();
  await page.locator('[data-testid="verify-code-0"]').fill('1');
  await page.locator('[data-testid="verify-code-1"]').fill('2');
  await page.locator('[data-testid="verify-code-2"]').fill('3');

  // Cell 3 is now focused (and empty). Backspace should move focus to cell 2.
  await expect(page.locator('[data-testid="verify-code-3"]')).toBeFocused();
  await page.keyboard.press('Backspace');
  await expect(page.locator('[data-testid="verify-code-2"]')).toBeFocused({
    timeout: 1_000,
  });
});
