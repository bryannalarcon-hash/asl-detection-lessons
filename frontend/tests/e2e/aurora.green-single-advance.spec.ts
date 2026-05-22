import { test, expect } from '@playwright/test';
import { signInViaDevBypass } from './_helpers';

/**
 * Bug regression: one Set-Green click must advance exactly one rep, not
 * chain-fire through subsequent SELF_REPORT entries while the box stays
 * green. The box must return to a non-green color before the next green
 * can trigger another advance.
 */
test('Set Green advances exactly one rep, not multiple', async ({ page }) => {
  await signInViaDevBypass(page);
  await page.goto('/lessons/lesson-1');
  await page.locator('[data-testid="lesson-start"]').click();
  await page.waitForURL(/\/lessons\/lesson-1\/practice/);
  await expect(page.getByTestId('page-practice')).toBeVisible();

  const repCounter = page.locator('[data-testid="rep-counter"]');
  await expect(repCounter).toHaveText(/1.*(of|\/).*3/i);

  // One Set-Green click.
  await page.locator('[data-testid="dev-set-green"]').click();

  // Rep ticks to 2 of 3.
  await expect(repCounter).toHaveText(/2.*(of|\/).*3/i, { timeout: 2_000 });

  // Wait long enough that any chain-fire would have settled at rep 3+. If
  // the green latch holds, rep stays at 2.
  await page.waitForTimeout(2_000);
  await expect(repCounter).toHaveText(/2.*(of|\/).*3/i);

  // A second Set-Green click should advance again.
  await page.locator('[data-testid="dev-set-green"]').click();
  await expect(repCounter).toHaveText(/3.*(of|\/).*3/i, { timeout: 2_000 });
});
