import { test, expect } from '@playwright/test';
import { signInViaDevBypass, ALL_ROUTES } from './_helpers';

/**
 * Spec 6 — Routes smoke. Visit all 23 routes, confirm none emit console.error
 * and each renders either page-placeholder or page-real (data-testid="page-*").
 */
test.describe('every route renders without console errors', () => {
  test('walks the full 23-route map', async ({ page }) => {
    // Auth once before walking the routes — most routes are behind the AppShell.
    await signInViaDevBypass(page);

    const errors: { route: string; text: string }[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        // Ignore expected errors: video decoding (no real mp4), favicons, etc.
        const text = msg.text();
        if (
          /favicon|sw\.js|workbox|manifest|Failed to load resource|net::ERR/i.test(text)
        ) {
          return;
        }
        errors.push({ route: page.url(), text });
      }
    });
    page.on('pageerror', (err) => {
      errors.push({ route: page.url(), text: `[pageerror] ${err.message}` });
    });

    for (const { path, label } of ALL_ROUTES) {
      await page.goto(path, { waitUntil: 'load' });
      // Each rendered page exposes one of these data-testids.
      const candidates = page.locator(
        '[data-testid^="page-"], [data-testid="page-placeholder"]',
      );
      const found = await candidates.count();
      expect(
        found,
        `route ${label} (${path}) should render a [data-testid^="page-"] element`,
      ).toBeGreaterThan(0);
    }

    expect(
      errors,
      `console.error / pageerror surfaced on these routes:\n${JSON.stringify(errors, null, 2)}`,
    ).toHaveLength(0);
  });
});
