import { defineConfig } from '@playwright/test';

/**
 * Playwright config for the 6 anchor specs (Phase 3).
 * - Boots backend + frontend in parallel via webServer.
 * - Uses fake media stream so getUserMedia() resolves in headless Chromium.
 * - fullyParallel: false because the seeded dev account is shared global state.
 */
export default defineConfig({
  testDir: './frontend/tests',
  // Only run e2e + a11y specs — unit specs are Vitest-only.
  testMatch: ['e2e/**/*.spec.ts', 'a11y/**/*.spec.ts'],
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    launchOptions: {
      args: [
        '--use-fake-ui-for-media-stream',
        '--use-fake-device-for-media-stream',
      ],
    },
    trace: 'on-first-retry',
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
  },
  webServer: [
    {
      command: 'npm --workspace backend run dev',
      port: 3000,
      reuseExistingServer: true,
      timeout: 30_000,
      env: {
        // Forward DATABASE_URL so the backend connects to the seeded Postgres.
        DATABASE_URL:
          process.env.DATABASE_URL ??
          'postgres://asl:asl_dev_only@localhost:5433/asl_pilot',
        BACKEND_PORT: '3000',
      },
    },
    {
      command: 'npm --workspace frontend run dev',
      port: 5173,
      reuseExistingServer: true,
      timeout: 30_000,
    },
  ],
});
