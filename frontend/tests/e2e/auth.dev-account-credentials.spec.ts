import { test, expect } from '@playwright/test';
import { DEV_EMAIL, DEV_PASSWORD } from './_dev-credentials';

/**
 * Spec — Dev account is always reachable via real email + password.
 *
 * The seed script writes a bcrypt hash for `DEV_EMAIL` / `DEV_PASSWORD`, so the
 * dev account can be signed in either via the [Dev: Skip login] shortcut
 * (covered in auth.signin.dev-bypass.spec.ts) or via the normal email/password
 * form. This spec proves the second path so the dev account doubles as a
 * "known-good real user" if Skip-login is hidden by VITE_DEV_TOOLS=0.
 */
test.describe('auth: dev account via email + password', () => {
  test.beforeEach(async ({ page }) => {
    // Ensure no stale session leaks in from earlier tests.
    await page.request.post('http://localhost:3000/api/auth/sign-out');
  });

  test('email + password sign-in for the dev account lands on /dashboard', async ({ page }) => {
    await page.goto('/signin');
    await expect(page.locator('[data-testid="page-sign-in"]')).toBeVisible();

    await page.locator('[data-testid="sign-in-email"]').fill(DEV_EMAIL);
    await page.locator('[data-testid="sign-in-password"]').fill(DEV_PASSWORD);
    await page.locator('[data-testid="sign-in-submit"]').click();

    await page.waitForURL(/\/dashboard$/);
    await expect(page.locator('[data-testid="page-dashboard"]')).toBeVisible();
  });
});
