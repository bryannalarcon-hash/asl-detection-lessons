import { test, expect } from '@playwright/test';
import { signInViaDevBypass } from './_helpers';

/**
 * TDD: clicking [I got it] once (without force) must advance the drill rep
 * counter from 1/3 to 2/3 within 500ms. No force: true — if the button is
 * covered by another element, this test fails like a real user would.
 */
test('clicking I got it once advances the rep counter', async ({ page }) => {
  await signInViaDevBypass(page);
  await page.goto('/lessons/lesson-1');
  await page.locator('[data-testid="lesson-start"]').click();
  await page.waitForURL(/\/lessons\/lesson-1\/practice/);
  await expect(page.locator('[data-testid="page-practice"]')).toBeVisible();

  // RepCounter renders as `Rep N of M` somewhere. The component exposes
  // the index via aria so we can read it; otherwise fall back to text.
  const repCounter = page.locator('[data-testid="rep-counter"]');
  await expect(repCounter).toBeVisible({ timeout: 5_000 });

  const initialText = (await repCounter.textContent())?.trim() ?? '';
  // Normalize: expect something like "Rep 1 of 3" or "1 / 3"
  expect(initialText).toMatch(/1.*(of|\/).*3/i);

  // Click WITHOUT force — if anything covers this button, this test fails.
  const gotIt = page.locator('[data-testid="self-report-got-it"]');
  await expect(gotIt).toBeVisible();
  await expect(gotIt).toBeEnabled();
  await gotIt.click();

  // After one click, the counter should reflect "Rep 2 of 3".
  await expect(repCounter).toHaveText(/2.*(of|\/).*3/i, { timeout: 1_000 });
});

/**
 * Same setup, but click I got it nine times (3 reps per drill × 3 drills).
 * Verify that EVERY click advances some piece of state — no stuck stages.
 * If the user's report "buttons stop working at some stage" is real, this
 * test catches the dead transition.
 */
test('clicking I got it nine times walks through all three drills', async ({ page }) => {
  await signInViaDevBypass(page);
  await page.goto('/lessons/lesson-1');
  await page.locator('[data-testid="lesson-start"]').click();
  await page.waitForURL(/\/lessons\/lesson-1\/practice/);

  const gotIt = page.locator('[data-testid="self-report-got-it"]');
  const repCounter = page.locator('[data-testid="rep-counter"]');
  const dotHandshape = page.locator('[data-testid="drill-dot-handshape"]');
  const dotMovement = page.locator('[data-testid="drill-dot-movement"]');
  const dotSign = page.locator('[data-testid="drill-dot-sign"]');

  // Start: handshape, rep 1 of 3
  await expect(dotHandshape).toHaveAttribute('data-active', 'true');

  // Reps 1–3 of handshape
  await gotIt.click();
  await expect(repCounter).toHaveText(/2.*(of|\/).*3/i, { timeout: 1_000 });
  await gotIt.click();
  await expect(repCounter).toHaveText(/3.*(of|\/).*3/i, { timeout: 1_000 });
  await gotIt.click();
  // After the third pass, drill advances to movement
  await expect(dotMovement).toHaveAttribute('data-active', 'true', { timeout: 1_000 });
  await expect(repCounter).toHaveText(/1.*(of|\/).*3/i, { timeout: 1_000 });

  // Reps 1–3 of movement
  await gotIt.click();
  await expect(repCounter).toHaveText(/2.*(of|\/).*3/i, { timeout: 1_000 });
  await gotIt.click();
  await expect(repCounter).toHaveText(/3.*(of|\/).*3/i, { timeout: 1_000 });
  await gotIt.click();
  await expect(dotSign).toHaveAttribute('data-active', 'true', { timeout: 1_000 });
  await expect(repCounter).toHaveText(/1.*(of|\/).*3/i, { timeout: 1_000 });

  // Reps 1–3 of sign → next sign or lesson-complete navigation
  await gotIt.click();
  await expect(repCounter).toHaveText(/2.*(of|\/).*3/i, { timeout: 1_000 });
  await gotIt.click();
  await expect(repCounter).toHaveText(/3.*(of|\/).*3/i, { timeout: 1_000 });
  await gotIt.click();

  // We either advance to next sign (handshape active again with rep 1) or land on complete.
  await page.waitForTimeout(400);
  const url = page.url();
  if (url.includes('/complete')) {
    await expect(page.locator('[data-testid="page-lesson-complete"]')).toBeVisible();
  } else {
    // Next sign: drill should reset to handshape, rep to 1
    await expect(dotHandshape).toHaveAttribute('data-active', 'true');
    await expect(repCounter).toHaveText(/1.*(of|\/).*3/i);
  }
});

/**
 * Auto-advance behavior: forcing the bounding box to green via the dev panel
 * must advance the rep in SELF_REPORT — no Continue click required.
 */
test('forcing Set Green via dev panel auto-advances the rep', async ({ page }) => {
  await signInViaDevBypass(page);
  await page.goto('/lessons/lesson-1');
  await page.locator('[data-testid="lesson-start"]').click();
  await page.waitForURL(/\/lessons\/lesson-1\/practice/);

  // Initial state: rep 1 of 3
  const repCounter = page.locator('[data-testid="rep-counter"]');
  await expect(repCounter).toBeVisible();
  await expect(repCounter).toHaveText(/1.*(of|\/).*3/i);

  // Click Set Green — should auto-advance after the visible flash
  await page.locator('[data-testid="dev-set-green"]').click();
  await expect(repCounter).toHaveText(/2.*(of|\/).*3/i, { timeout: 2_000 });
});
