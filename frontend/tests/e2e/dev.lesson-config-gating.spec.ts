import { test, expect } from '@playwright/test';
import { signInViaDevBypass } from './_helpers';

/**
 * Spec — [Dev: Lesson Config] editor gating + reachability.
 *
 * Like `auth.dev-tools-gating.spec.ts`, the Vite dev server reads
 * `VITE_DEV_TOOLS` at startup, so we can only exercise the ON-case (default)
 * from inside Playwright. This spec asserts:
 *
 *   1. the `[Dev: Lesson Config]` entry link is visible on a lesson intro,
 *   2. the dev route `/dev/lesson-config` renders the editor page,
 *   3. the editor exposes the sign-count + per-sign/per-stage controls.
 *
 * The OFF-case (`VITE_DEV_TOOLS=0` hides the link, drops the route, and DCE
 * removes the page from the bundle) is covered by the unit spec
 * `tests/unit/lesson-config-gate.spec.ts`, which asserts the source guards the
 * editor behind `isDevToolsEnabled()`. The bundle string-absence under
 * `VITE_DEV_TOOLS=0` is verified manually, not in CI.
 */
test.describe('dev lesson-config gating (default ON)', () => {
  test('lesson intro surfaces the [Dev: Lesson Config] link', async ({ page }) => {
    await signInViaDevBypass(page);
    await page.goto('/lessons/lesson-1');
    await expect(page.locator('[data-testid="page-lesson-intro"]')).toBeVisible();

    const link = page.locator('[data-testid="dev-lesson-config-link"]');
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute('data-dev-override', 'true');
  });

  test('the editor route renders sign + per-stage trim/reps controls', async ({ page }) => {
    await signInViaDevBypass(page);
    await page.goto('/dev/lesson-config');

    const root = page.locator('[data-testid="page-dev-lesson-config"]');
    await expect(root).toBeVisible();
    await expect(root).toHaveAttribute('data-dev-override', 'true');

    // Core controls exist (sign count, plus per-sign select + video preview and
    // per-stage trim/reps once a lesson is loaded — at least one sign is seeded).
    await expect(page.locator('[data-testid="dev-lesson-config-sign-count"]')).toBeVisible();
    await expect(page.locator('[data-testid="dev-sign-config"]').first()).toBeVisible();
    await expect(page.locator('[data-testid="dev-sign-select"]').first()).toBeVisible();
    await expect(page.locator('[data-testid="dev-sign-video"]').first()).toBeVisible();
    // Handshape stage controls (start/end/reps) + preview.
    await expect(
      page.locator('[data-testid="dev-stage-start-handshape"]').first()
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="dev-stage-reps-handshape"]').first()
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="dev-stage-preview-handshape"]').first()
    ).toBeVisible();
    await expect(page.locator('[data-testid="dev-lesson-config-save"]')).toBeVisible();
  });

  test('saving a stage reps override persists and drives the practice rep counter', async ({
    page,
  }) => {
    await signInViaDevBypass(page);
    await page.goto('/dev/lesson-config');
    await expect(page.locator('[data-testid="page-dev-lesson-config"]')).toBeVisible();

    // Set the first sign's full-sign-stage reps to 5 and save. The lesson plan
    // presents only the full sign, so practice opens on that stage and the rep
    // counter denominator should become 5.
    const reps = page.locator('[data-testid="dev-stage-reps-sign"]').first();
    await reps.fill('5');
    await page.locator('[data-testid="dev-lesson-config-save"]').click();
    await expect(page.locator('[data-testid="dev-lesson-config-saved"]')).toBeVisible();

    // Read the active lesson slug from the selector so we navigate to the same
    // lesson we just configured.
    const slug = await page
      .locator('[data-testid="dev-lesson-config-lesson-select"]')
      .inputValue();

    await page.goto(`/lessons/${slug}/practice?camera=0&reference=0`);
    await expect(page.locator('[data-testid="page-practice"]')).toBeVisible();

    // The rep counter total should reflect the overlay (5), not the default (3).
    // RepCounter renders "<cur> / <total>" — assert the denominator is 5.
    await expect(page.locator('[data-testid="rep-counter"]')).toContainText('/ 5');
  });
});
