import { test, expect } from '@playwright/test';
import { signInViaDevBypass } from './_helpers';

test.describe('practice: adaptive hint surfacing', () => {
  test.beforeEach(async ({ page }) => {
    await signInViaDevBypass(page);
    await page.goto('/lessons/lesson-1');
    await page.locator('[data-testid="lesson-start"]').click();
    await page.waitForURL(/\/lessons\/lesson-1\/practice/);
    await expect(page.getByTestId('page-practice')).toBeVisible();
  });

  test('hint button shows quiet state at 0 fails, urgent at 2+, auto-opens at 3', async ({
    page,
  }) => {
    // Wait for the machine to reach SELF_REPORT (3-event fast-forward settles).
    await expect(page.getByTestId('self-report-got-it')).toBeVisible();

    const hint = page.getByTestId('hint-button');
    await expect(hint).toBeVisible();
    await expect(hint).toHaveAttribute('data-fail-count', '0');
    await expect(hint).toContainText(/show a hint/i);
    await expect(page.getByTestId('hint-urgent-caption')).toHaveCount(0);

    // Helper: send a FAIL and wait for the machine to absorb it. REP_RETRY → 250ms →
    // PROMPT_SHOWN → fast-forward effect → SELF_REPORT. The 400ms wait covers the
    // 250ms machine timer + the React render + fast-forward sends.
    const failOnce = async (expected: string) => {
      await page.getByTestId('dev-fail-rep').click();
      await expect(hint).toHaveAttribute('data-fail-count', expected, { timeout: 3000 });
      await page.waitForTimeout(400);
    };

    await failOnce('1');
    await expect(page.getByTestId('hint-urgent-caption')).toHaveCount(0);

    await failOnce('2');
    await expect(hint).toContainText(/stuck/i);
    await expect(page.getByTestId('hint-urgent-caption')).toBeVisible();

    await failOnce('3');
    await expect(page.getByRole('dialog')).toBeVisible();
  });
});
