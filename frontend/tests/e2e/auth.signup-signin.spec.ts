import { test, expect } from '@playwright/test';

/**
 * Spec — Real sign-up + sign-in round-trip.
 *
 * Covers:
 *   1. POST /api/auth/sign-up with valid body → arrives at /onboarding/welcome.
 *   2. After sign-out, GET /api/auth/me returns 401.
 *   3. POST /api/auth/sign-in with the same credentials → arrives at /dashboard.
 *   4. Sign-in with WRONG password → sign-in-error renders "Invalid email or password".
 *   5. Sign-up with the SAME email → sign-up-error mentions "already".
 *
 * Each run uses a unique email (timestamp suffix) so re-runs don't collide with
 * prior state. The dev-account is never touched.
 */

const PASSWORD = 'pilot-test-password-123';
const WRONG_PASSWORD = 'definitely-the-wrong-password';

function uniqueEmail(suffix: string): string {
  return `e2e-${Date.now()}-${suffix}@asl-test.local`;
}

async function clearSession(page: import('@playwright/test').Page): Promise<void> {
  // Backend clears the session cookie; do this via the real endpoint so the
  // cookie jar (HttpOnly) sees the Set-Cookie reset.
  await page.request.post('http://localhost:3000/api/auth/sign-out');
}

test.describe('auth: sign-up + sign-in round-trip', () => {
  test.beforeEach(async ({ page }) => {
    await clearSession(page);
  });

  test('sign-up lands on /onboarding/welcome', async ({ page }) => {
    const email = uniqueEmail('signup-welcome');

    await page.goto('/signup');
    await expect(page.locator('[data-testid="page-sign-up"]')).toBeVisible();

    await page.locator('[data-testid="sign-up-display-name"]').fill('Pilot Tester');
    await page.locator('[data-testid="sign-up-email"]').fill(email);
    await page.locator('[data-testid="sign-up-password"]').fill(PASSWORD);
    await page.locator('[data-testid="sign-up-confirm"]').fill(PASSWORD);
    await page.locator('[data-testid="sign-up-submit"]').click();

    await page.waitForURL(/\/onboarding\/welcome$/);
    expect(page.url()).not.toContain('/signup');
  });

  test('after sign-out, /me returns 401', async ({ page }) => {
    const email = uniqueEmail('signout-me');

    // First sign-up to establish a session.
    await page.goto('/signup');
    await page.locator('[data-testid="sign-up-display-name"]').fill('Pilot Tester');
    await page.locator('[data-testid="sign-up-email"]').fill(email);
    await page.locator('[data-testid="sign-up-password"]').fill(PASSWORD);
    await page.locator('[data-testid="sign-up-confirm"]').fill(PASSWORD);
    await page.locator('[data-testid="sign-up-submit"]').click();
    await page.waitForURL(/\/onboarding\/welcome$/);

    // Sign out via the API (cookie cleared on the same context).
    const signOutRes = await page.request.post('http://localhost:3000/api/auth/sign-out');
    expect(signOutRes.status()).toBe(200);

    const meRes = await page.request.get('http://localhost:3000/api/auth/me');
    expect(meRes.status()).toBe(401);
  });

  test('sign-in with correct password lands on /dashboard', async ({ page }) => {
    const email = uniqueEmail('signin-ok');

    // Create the account first.
    await page.goto('/signup');
    await page.locator('[data-testid="sign-up-display-name"]').fill('Pilot Tester');
    await page.locator('[data-testid="sign-up-email"]').fill(email);
    await page.locator('[data-testid="sign-up-password"]').fill(PASSWORD);
    await page.locator('[data-testid="sign-up-confirm"]').fill(PASSWORD);
    await page.locator('[data-testid="sign-up-submit"]').click();
    await page.waitForURL(/\/onboarding\/welcome$/);

    // Sign out to clear the session.
    await clearSession(page);

    // Now sign back in via the form.
    await page.goto('/signin');
    await expect(page.locator('[data-testid="page-sign-in"]')).toBeVisible();
    await page.locator('[data-testid="sign-in-email"]').fill(email);
    await page.locator('[data-testid="sign-in-password"]').fill(PASSWORD);
    await page.locator('[data-testid="sign-in-submit"]').click();

    await page.waitForURL(/\/dashboard$/);
    await expect(page.locator('[data-testid="page-dashboard"]')).toBeVisible();
  });

  test('sign-in with wrong password shows error', async ({ page }) => {
    const email = uniqueEmail('signin-bad');

    // Create the account.
    await page.goto('/signup');
    await page.locator('[data-testid="sign-up-display-name"]').fill('Pilot Tester');
    await page.locator('[data-testid="sign-up-email"]').fill(email);
    await page.locator('[data-testid="sign-up-password"]').fill(PASSWORD);
    await page.locator('[data-testid="sign-up-confirm"]').fill(PASSWORD);
    await page.locator('[data-testid="sign-up-submit"]').click();
    await page.waitForURL(/\/onboarding\/welcome$/);

    await clearSession(page);

    // Now attempt with the wrong password.
    await page.goto('/signin');
    await page.locator('[data-testid="sign-in-email"]').fill(email);
    await page.locator('[data-testid="sign-in-password"]').fill(WRONG_PASSWORD);
    await page.locator('[data-testid="sign-in-submit"]').click();

    const error = page.locator('[data-testid="sign-in-error"]');
    await expect(error).toBeVisible();
    await expect(error).toHaveText(/Invalid email or password/i);
    // Should not navigate away from /signin.
    expect(page.url()).toMatch(/\/signin$/);
  });

  test('sign-up with duplicate email shows error', async ({ page }) => {
    const email = uniqueEmail('signup-dup');

    // First sign-up succeeds.
    await page.goto('/signup');
    await page.locator('[data-testid="sign-up-display-name"]').fill('Pilot Tester');
    await page.locator('[data-testid="sign-up-email"]').fill(email);
    await page.locator('[data-testid="sign-up-password"]').fill(PASSWORD);
    await page.locator('[data-testid="sign-up-confirm"]').fill(PASSWORD);
    await page.locator('[data-testid="sign-up-submit"]').click();
    await page.waitForURL(/\/onboarding\/welcome$/);

    await clearSession(page);

    // Second sign-up with the SAME email + a different password → 409 + error.
    await page.goto('/signup');
    await page.locator('[data-testid="sign-up-display-name"]').fill('Pilot Tester Twin');
    await page.locator('[data-testid="sign-up-email"]').fill(email);
    await page.locator('[data-testid="sign-up-password"]').fill(`${PASSWORD}-alt`);
    await page.locator('[data-testid="sign-up-confirm"]').fill(`${PASSWORD}-alt`);
    await page.locator('[data-testid="sign-up-submit"]').click();

    const error = page.locator('[data-testid="sign-up-error"]');
    await expect(error).toBeVisible();
    await expect(error).toHaveText(/already (exists|registered)/i);
    expect(page.url()).toMatch(/\/signup$/);
  });
});
