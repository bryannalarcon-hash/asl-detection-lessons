import { test, expect, devices } from '@playwright/test';
import { signInViaDevBypass } from './_helpers';

/**
 * Mobile responsiveness regression. Encodes the design's mobile motifs
 * (design_handoff_asl_pilot SCREENS.md §"Responsive / mobile"): below 760px the
 * desktop top-nav links collapse into a fixed bottom tab bar, signed-in pages do
 * not scroll horizontally, and the two-column layouts stack to one column.
 */

const PHONE = devices['iPhone 12'];

// Signed-in app-shell routes that previously overflowed because of the top nav.
const SHELL_ROUTES = [
  '/dashboard',
  '/lessons',
  '/lessons/lesson-1',
  '/lessons/lesson-1/complete',
  '/settings/account',
  '/settings/app',
  '/settings/notifications',
  '/privacy',
  '/help',
  '/about',
];

test.describe('mobile (iPhone 12 / 390px)', () => {
  test.use({ viewport: PHONE.viewport, isMobile: true, hasTouch: true });

  test('shell routes do not scroll horizontally', async ({ page }) => {
    await signInViaDevBypass(page);
    for (const path of SHELL_ROUTES) {
      await page.goto(path, { waitUntil: 'load' });
      await page.waitForTimeout(300);
      const { scrollW, clientW } = await page.evaluate(() => ({
        scrollW: document.documentElement.scrollWidth,
        clientW: document.documentElement.clientWidth,
      }));
      // Allow 1px rounding slack.
      expect(scrollW - clientW, `${path} overflows by ${scrollW - clientW}px`).toBeLessThanOrEqual(1);
    }
  });

  test('bottom tab bar replaces the desktop nav links', async ({ page }) => {
    await signInViaDevBypass(page);
    await page.goto('/dashboard', { waitUntil: 'load' });

    // Tab bar present + visible.
    const tabbar = page.locator('[data-testid="mobile-tabbar"]');
    await expect(tabbar).toBeVisible();

    // All four destinations are reachable from the bar.
    for (const id of ['tabbar-home', 'tabbar-lessons', 'tabbar-settings', 'tabbar-help']) {
      await expect(page.locator(`[data-testid="${id}"]`)).toBeVisible();
    }

    // Desktop inline nav links are hidden on mobile (moved to the tab bar).
    await expect(page.locator('[data-testid="nav-lessons"]')).toBeHidden();
  });

  test('tab bar navigates to lessons and reflects the active route', async ({ page }) => {
    await signInViaDevBypass(page);
    await page.goto('/dashboard', { waitUntil: 'load' });

    await page.locator('[data-testid="tabbar-lessons"]').click();
    await page.waitForURL(/\/lessons$/);
    await expect(page.locator('[data-testid="tabbar-lessons"]')).toHaveAttribute('aria-current', 'page');
  });
});

test.describe('desktop (1280px)', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('keeps the top nav and hides the bottom tab bar', async ({ page }) => {
    await signInViaDevBypass(page);
    await page.goto('/dashboard', { waitUntil: 'load' });

    await expect(page.locator('[data-testid="nav-lessons"]')).toBeVisible();
    await expect(page.locator('[data-testid="mobile-tabbar"]')).toBeHidden();
  });
});

test.describe('mobile practice is immersive (mock 17-21)', () => {
  test.use({ viewport: PHONE.viewport, isMobile: true, hasTouch: true });

  test('renders the immersive shell, not the desktop grid, with no overflow', async ({ page }) => {
    await signInViaDevBypass(page);
    await page.goto('/lessons/lesson-1/practice', { waitUntil: 'load' });

    await expect(page.locator('[data-testid="practice-immersive"]')).toBeVisible();
    await expect(page.locator('[data-testid="page-practice"]')).toBeVisible();
    // The immersive layout has its own chrome — the desktop practice header is absent.
    await expect(page.locator('[data-testid="practice-header"]')).toHaveCount(0);

    const { scrollW, clientW } = await page.evaluate(() => ({
      scrollW: document.documentElement.scrollWidth,
      clientW: document.documentElement.clientWidth,
    }));
    expect(scrollW - clientW).toBeLessThanOrEqual(1);
  });

  test('swap control and options sheet are reachable', async ({ page }) => {
    await signInViaDevBypass(page);
    await page.goto('/lessons/lesson-1/practice', { waitUntil: 'load' });
    await expect(page.locator('[data-testid="practice-immersive"]')).toBeVisible();

    await page.locator('[data-testid="practice-more"]').click();
    await expect(page.locator('[data-testid="practice-options-sheet"]')).toBeVisible();
    // Continue (advance) control is present in the dock.
    await expect(page.locator('[data-testid="self-report-got-it"]')).toBeVisible();
  });
});

test.describe('desktop practice keeps the grid layout', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('uses the desktop practice header, not the immersive shell', async ({ page }) => {
    await signInViaDevBypass(page);
    await page.goto('/lessons/lesson-1/practice', { waitUntil: 'load' });

    await expect(page.locator('[data-testid="practice-header"]')).toBeVisible();
    await expect(page.locator('[data-testid="practice-immersive"]')).toHaveCount(0);
  });
});
