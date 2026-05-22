import { test, expect } from '@playwright/test';
import { signInViaDevBypass } from './_helpers';

/**
 * Spec 4 — Lesson Intro toggles persist into the Practice Screen.
 *
 * Case A: Reference OFF, Camera ON
 *   - reference-panel must NOT exist
 *   - camera-panel must exist
 *
 * Case B: Reference ON, Camera OFF
 *   - camera-panel must NOT exist
 *   - self-report-row must still be visible (and the practice page should
 *     render in quiz mode without a camera).
 */
test('lesson intro toggles pass through to practice (reference off)', async ({ page }) => {
  await signInViaDevBypass(page);
  await page.goto('/lessons/lesson-1');
  await expect(page.locator('[data-testid="page-lesson-intro"]')).toBeVisible();

  // Uncheck reference toggle (currently checked by default).
  const referenceToggle = page.locator('[data-testid="lesson-toggle-reference"]');
  await expect(referenceToggle).toBeVisible();
  // Base UI's Checkbox is a button with role=checkbox. Just click to toggle.
  await referenceToggle.click();

  await page.locator('[data-testid="lesson-start"]').click();
  await page.waitForURL(/\/lessons\/lesson-1\/practice/);

  await expect(page.locator('[data-testid="page-practice"]')).toBeVisible();
  await expect(page.locator('[data-testid="reference-panel"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="camera-panel"]')).toBeVisible();
});

test('lesson intro toggles pass through to practice (camera off)', async ({ page }) => {
  await signInViaDevBypass(page);
  await page.goto('/lessons/lesson-1');
  await expect(page.locator('[data-testid="page-lesson-intro"]')).toBeVisible();

  // Uncheck camera toggle.
  const cameraToggle = page.locator('[data-testid="lesson-toggle-camera"]');
  await expect(cameraToggle).toBeVisible();
  await cameraToggle.click();

  await page.locator('[data-testid="lesson-start"]').click();
  await page.waitForURL(/\/lessons\/lesson-1\/practice/);

  await expect(page.locator('[data-testid="page-practice"]')).toBeVisible();
  await expect(page.locator('[data-testid="camera-panel"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="self-report-row"]')).toBeVisible();
});
