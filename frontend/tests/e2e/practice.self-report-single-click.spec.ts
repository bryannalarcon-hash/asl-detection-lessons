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
 * Same setup, but click I got it through a full sign's reps and into the next
 * word. The lesson plan presents only the full sign per word (no handshape /
 * movement stages), so every click advances a rep until the sign's last rep,
 * after which the next click moves to a new word. Verify EVERY click advances
 * some piece of state — no stuck stages.
 */
test('clicking I got it walks through a sign\'s reps and on to the next word', async ({ page }) => {
  await signInViaDevBypass(page);
  await page.goto('/lessons/lesson-1');
  await page.locator('[data-testid="lesson-start"]').click();
  await page.waitForURL(/\/lessons\/lesson-1\/practice/);

  const gotIt = page.locator('[data-testid="self-report-got-it"]');
  const repCounter = page.locator('[data-testid="rep-counter"]');
  const title = page.locator('[data-testid="page-practice"] h1').first();

  // The multi-stage pill row is hidden under the full-sign-only plan.
  await expect(page.locator('[data-testid="drill-indicator"]')).toHaveCount(0);

  // Start: rep 1 of 3 on the first word.
  await expect(repCounter).toHaveText(/1.*(of|\/).*3/i);
  const firstWord = (await title.textContent())?.trim() ?? '';

  // Within-sign rep advances read "Next rep".
  await expect(gotIt).toHaveText(/next rep/i);
  await gotIt.click();
  await expect(repCounter).toHaveText(/2.*(of|\/).*3/i, { timeout: 1_000 });
  await gotIt.click();
  await expect(repCounter).toHaveText(/3.*(of|\/).*3/i, { timeout: 1_000 });

  // Last rep of the word: the next press starts a new word -> "Continue".
  await expect(gotIt).toHaveText(/continue/i);
  await gotIt.click();

  // Either we advanced to the next word (rep 1 again, different title) or landed
  // on the lesson-complete page.
  await page.waitForTimeout(400);
  const url = page.url();
  if (url.includes('/complete')) {
    await expect(page.locator('[data-testid="page-lesson-complete"]')).toBeVisible();
  } else {
    await expect(repCounter).toHaveText(/1.*(of|\/).*3/i);
    const nextWord = (await title.textContent())?.trim() ?? '';
    expect(nextWord).not.toBe(firstWord);
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

  // Click Set Green — auto-advances after the ~3s visible green hold (Practice.tsx).
  await page.locator('[data-testid="dev-set-green"]').click();
  await expect(repCounter).toHaveText(/2.*(of|\/).*3/i, { timeout: 4_000 });
});
