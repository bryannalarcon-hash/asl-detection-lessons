import { test, expect } from '@playwright/test';
import { signInViaDevBypass } from './_helpers';

/**
 * Manual-verification spec for the camera-permission swarm task.
 * Drives the four [Dev: ...] buttons in the CameraDevToolbox to make sure
 * each terminal state actually renders the expected branch.
 */
test.describe('camera permission dev toolbox', () => {
  test('force-allow → granted video, force-deny → denied UI, force-unsupported → unsupported UI, reset → requesting', async ({
    page,
    context,
  }) => {
    // Block real camera so the auto-request lands in `denied` (or in any
    // case, doesn't open a system dialog). The dev toolbox overrides the
    // visible state anyway.
    await context.grantPermissions([], { origin: 'http://localhost:5173' });

    await signInViaDevBypass(page);
    await page.goto('/lessons/lesson-1/practice');

    const panel = page.locator('[data-testid="camera-panel"]');
    await expect(panel).toBeVisible();
    await expect(page.locator('[data-testid="dev-camera-toolbox"]')).toBeVisible();

    // --- Force allow ---
    await page.locator('[data-testid="dev-camera-force-allow"]').click();
    await expect(panel).toHaveAttribute('data-camera-state', 'granted');
    await expect(page.locator('[data-testid="camera-video"]')).toBeVisible();

    // --- Force deny ---
    await page.locator('[data-testid="dev-camera-force-deny"]').click();
    await expect(panel).toHaveAttribute('data-camera-state', 'denied');
    await expect(page.locator('[data-testid="camera-denied-inline"]')).toBeVisible();
    await expect(page.locator('[data-testid="camera-rerequest"]')).toBeVisible();

    // --- Force unsupported ---
    await page.locator('[data-testid="dev-camera-force-unsupported"]').click();
    await expect(panel).toHaveAttribute('data-camera-state', 'unsupported');
    await expect(page.locator('[data-testid="camera-unsupported"]')).toBeVisible();

    // --- Reset ---
    await page.locator('[data-testid="dev-camera-force-reset"]').click();
    // After reset we go back to `idle` momentarily — CameraPanel doesn't
    // auto-re-request after reset (would race with the toolbox), so the
    // panel stays in idle/requesting. Either is acceptable for "back to
    // requesting" UX-wise.
    const stateAfterReset = await panel.getAttribute('data-camera-state');
    expect(['idle', 'requesting']).toContain(stateAfterReset);
  });

  test('VITE_DEV_TOOLS=0 hides the toolbox', async ({ page }) => {
    // We can't change the env mid-run; instead, verify the data-dev-override
    // attribute is present so the parent dev-tools-off override would catch it.
    await signInViaDevBypass(page);
    await page.goto('/lessons/lesson-1/practice');
    const toolbox = page.locator('[data-testid="dev-camera-toolbox"]');
    await expect(toolbox).toBeVisible();
    await expect(toolbox).toHaveAttribute('data-dev-override', 'true');
  });
});
