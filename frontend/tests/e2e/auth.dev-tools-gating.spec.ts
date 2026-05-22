import { test, expect } from '@playwright/test';
import { signInViaDevBypass } from './_helpers';

/**
 * Spec — Dev-tools UI gating.
 *
 * The Vite dev server reads `VITE_DEV_TOOLS` at startup, so we cannot flip the
 * env per test from inside Playwright. This spec verifies the ON-case
 * (default) — that `[data-testid="dev-skip-login"]` is visible on /signin and
 * that `[data-testid="dev-camera-toolbox"]` is visible on the practice screen
 * (the existing camera-permission spec also touches this, but here we assert
 * the gating contract explicitly).
 *
 * The OFF-case (`VITE_DEV_TOOLS=0` hides all dev UI) is covered by the unit
 * spec `frontend/tests/unit/dev-tools-gate.spec.ts`, which table-tests
 * `isDevToolsEnabled()` against the four meaningful input values. That keeps
 * the gating logic locked down without depending on a flaky env-flip.
 */
test.describe('dev-tools gating (default ON)', () => {
  test('skip-login is visible on /signin', async ({ page }) => {
    await page.request.post('http://localhost:3000/api/auth/sign-out');
    await page.goto('/signin');
    await expect(page.locator('[data-testid="page-sign-in"]')).toBeVisible();

    const skip = page.locator('[data-testid="dev-skip-login"]');
    await expect(skip).toBeVisible();
    // The component sets a sentinel attribute to make the override obvious to
    // users — assert it so any future styling regression that drops the
    // attribute is caught.
    await expect(skip).toHaveAttribute('data-dev-override', 'true');

    // The sign-in dev hint with the dev credentials is also gated by DEV_TOOLS.
    await expect(page.locator('[data-testid="sign-in-dev-hint"]')).toBeVisible();
  });

  test('camera dev toolbox is visible on /lessons/:slug/practice', async ({ page, context }) => {
    // Block the real camera so the auto-request settles in a deterministic
    // state — we only care that the toolbox is rendered.
    await context.grantPermissions([], { origin: 'http://localhost:5173' });

    await signInViaDevBypass(page);
    await page.goto('/lessons/lesson-1/practice');

    await expect(page.locator('[data-testid="page-practice"]')).toBeVisible();

    const toolbox = page.locator('[data-testid="dev-camera-toolbox"]');
    await expect(toolbox).toBeVisible();
    await expect(toolbox).toHaveAttribute('data-dev-override', 'true');
  });

  test.skip('VITE_DEV_TOOLS=0 hides dev UI [covered by unit/dev-tools-gate.spec.ts]', () => {
    // Intentionally skipped — see file-level comment. The unit spec drives the
    // gating logic directly via `vi.stubEnv` + `vi.resetModules()`, which is
    // strictly more reliable than restarting the Vite dev server per case.
  });
});
