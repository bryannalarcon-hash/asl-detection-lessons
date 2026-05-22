import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { signInViaDevBypass } from '../e2e/_helpers';

/**
 * Spec 5 — Dashboard a11y scan. Expect zero WCAG 2.2 AA violations.
 */
test('dashboard has no axe-core WCAG violations', async ({ page }) => {
  await signInViaDevBypass(page);
  await page.waitForSelector('[data-testid="page-dashboard"]', { timeout: 10_000 });
  // Heatmap takes a tick to render once dashboard data arrives.
  await page.waitForSelector('[data-testid="heatmap-cell"]', { timeout: 10_000 });

  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag22aa'])
    .analyze();

  if (results.violations.length > 0) {
    // Log a structured digest so failures are diagnosable in CI.
    console.log(
      JSON.stringify(
        results.violations.map((v) => ({
          id: v.id,
          impact: v.impact,
          help: v.help,
          nodes: v.nodes.length,
        })),
        null,
        2,
      ),
    );
  }
  expect(results.violations).toEqual([]);
});
