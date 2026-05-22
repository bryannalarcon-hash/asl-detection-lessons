import { test, expect } from '@playwright/test';
import { signInViaDevBypass } from './_helpers';

/**
 * Aurora practice screen layout.
 *
 * - The three drill pill tabs render (handshape, movement, sign).
 * - The first tab carries the active state via data-state="active".
 * - The rep counter and Continue CTA both render with their Aurora labels.
 */

test('practice renders three drill pill tabs with handshape active first', async ({ page }) => {
  await signInViaDevBypass(page);
  await page.goto('/lessons/lesson-1/practice');
  await expect(page.locator('[data-testid="page-practice"]')).toBeVisible();

  const handshape = page.locator('[data-testid="drill-tab-handshape"]');
  const movement = page.locator('[data-testid="drill-tab-movement"]');
  const sign = page.locator('[data-testid="drill-tab-sign"]');

  await expect(handshape).toBeVisible();
  await expect(movement).toBeVisible();
  await expect(sign).toBeVisible();

  // Active drill is the first one (handshape). DrillIndicator exposes
  // data-state="active" on the active tab plus data-active="true" on its dot.
  await expect(handshape).toHaveAttribute('data-state', 'active');
  await expect(page.locator('[data-testid="drill-dot-handshape"]')).toHaveAttribute(
    'data-active',
    'true',
  );
});

test('practice surfaces rep counter and Continue CTA', async ({ page }) => {
  await signInViaDevBypass(page);
  await page.goto('/lessons/lesson-1/practice');

  const repCounter = page.locator('[data-testid="rep-counter"]');
  await expect(repCounter).toBeVisible({ timeout: 5_000 });
  // Counter starts at 1 / 3 (or "Rep 1 of 3" — accept either).
  await expect(repCounter).toHaveText(/1.*(of|\/).*3/i);

  const gotIt = page.locator('[data-testid="self-report-got-it"]');
  await expect(gotIt).toBeVisible();
  // SelfReportRow defaults to "Continue →".
  await expect(gotIt).toHaveText(/continue|next/i);
});
