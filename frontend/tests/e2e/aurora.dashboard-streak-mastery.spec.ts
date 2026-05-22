import { test, expect } from '@playwright/test';
import { signInViaDevBypass } from './_helpers';

/**
 * Aurora dashboard hero: mastery bar + streak indicator.
 *
 * - mastery-progress reads "<N> / 75 signs in progress" (live count drifts
 *   with seed re-runs; only the `/ 75` denominator is stable).
 * - streak-indicator renders a non-empty numeric day count.
 */

test('dashboard mastery card shows "X / 75" copy', async ({ page }) => {
  await signInViaDevBypass(page);
  const masteryProgress = page.locator('[data-testid="mastery-progress"]');
  await expect(masteryProgress).toBeVisible();
  // The component renders "<N> / 75 signs in progress". Match the numerator
  // + " / 75" suffix loosely to absorb whitespace + the prose tail.
  await expect(masteryProgress).toHaveText(/[0-9]+\s*\/\s*75/);
});

test('dashboard streak-indicator renders a numeric day count', async ({ page }) => {
  await signInViaDevBypass(page);
  const streak = page.locator('[data-testid="streak-indicator"]');
  await expect(streak).toBeVisible();
  // StreakIndicator pads to two digits ("01", "07", "23") via gradient-text.
  await expect(streak).toHaveText(/[0-9]{2,}/);
  // aria-label spells out the streak — confirm the wording lands.
  await expect(streak).toHaveAttribute('aria-label', /day\s+[0-9]+\s+streak/i);
});
