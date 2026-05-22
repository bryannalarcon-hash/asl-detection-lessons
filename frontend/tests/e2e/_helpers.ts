import type { Page } from '@playwright/test';

/**
 * Signs in via the dev-bypass button on /signin and waits for /dashboard.
 * Used by every e2e spec that needs an authenticated session.
 */
export async function signInViaDevBypass(page: Page): Promise<void> {
  await page.goto('/signin');
  await page.locator('[data-testid="dev-skip-login"]').click();
  await page.waitForURL(/\/dashboard$/);
}

/**
 * Full 23-route map per PRD §"Route Map". The :slug placeholders are
 * replaced with `lesson-1` (seeded by seed-dev-user.ts).
 */
export const ALL_ROUTES: { path: string; label: string }[] = [
  { path: '/', label: 'Landing' },
  { path: '/signup', label: 'Sign-up' },
  { path: '/signin', label: 'Sign-in' },
  { path: '/forgot-password', label: 'Forgot password' },
  { path: '/verify-email', label: 'Email verification' },
  { path: '/onboarding/welcome', label: 'Onboarding: Welcome' },
  { path: '/onboarding/camera', label: 'Onboarding: Camera' },
  { path: '/onboarding/calibration', label: 'Onboarding: Calibration' },
  { path: '/onboarding/first-sign', label: 'Onboarding: First-Sign Tutorial' },
  { path: '/dashboard', label: 'Dashboard' },
  { path: '/lessons', label: 'Lesson Catalog' },
  { path: '/lessons/lesson-1', label: 'Lesson Intro' },
  { path: '/lessons/lesson-1/practice', label: 'Practice' },
  { path: '/lessons/lesson-1/complete', label: 'Lesson Complete' },
  { path: '/settings/account', label: 'Account Settings' },
  { path: '/settings/app', label: 'App Settings' },
  { path: '/settings/notifications', label: 'Notification Preferences' },
  { path: '/privacy', label: 'Privacy & Data' },
  { path: '/help', label: 'Help' },
  { path: '/about', label: 'About' },
  { path: '/errors/camera-denied', label: 'Camera Denied' },
  { path: '/errors/offline', label: 'Offline' },
  { path: '/this-route-does-not-exist', label: '404' },
];
