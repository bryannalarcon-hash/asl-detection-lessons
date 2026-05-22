/**
 * Captures one screenshot per route into a timestamped subfolder of
 * `screenshots/`. Runs against the live dev servers (frontend:5173,
 * backend:3000). Signs in as the dev account so authenticated pages render
 * the real signed-in shell, not a redirect.
 *
 * Usage:
 *   node --import tsx scripts/screenshot-all-pages.ts [out_dir]
 */
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';

const FRONTEND = process.env.FRONTEND_URL ?? 'http://localhost:5173';
const BACKEND = process.env.BACKEND_URL ?? 'http://localhost:3000';

interface Shot {
  name: string;
  path: string;
  needsAuth?: boolean;
  /** Run before screenshot — e.g. wait for a testid, open a modal. */
  prep?: (page: import('playwright').Page) => Promise<void>;
}

const ROUTES: Shot[] = [
  { name: '01-landing', path: '/' },
  { name: '02-signin', path: '/signin' },
  { name: '03-signup', path: '/signup' },
  { name: '04-forgot-password', path: '/forgot-password' },
  { name: '05-verify-email', path: '/verify-email' },
  { name: '06-onboarding-welcome', path: '/onboarding/welcome' },
  { name: '07-onboarding-camera', path: '/onboarding/camera' },
  { name: '08-onboarding-calibration', path: '/onboarding/calibration' },
  { name: '09-onboarding-first-sign', path: '/onboarding/first-sign' },
  { name: '10-dashboard', path: '/dashboard', needsAuth: true },
  { name: '11-lessons-catalog', path: '/lessons', needsAuth: true },
  { name: '12-lesson-intro', path: '/lessons/greetings/', needsAuth: true },
  {
    name: '13-lesson-practice',
    path: '/lessons/greetings/practice',
    needsAuth: true,
    prep: async (page) => {
      await page
        .getByTestId('camera-panel')
        .waitFor({ timeout: 5_000 })
        .catch(() => undefined);
      await page
        .getByTestId('dev-camera-force-allow')
        .click({ timeout: 2_000 })
        .catch(() => undefined);
      await page.waitForTimeout(800);
    },
  },
  { name: '14-lesson-complete', path: '/lessons/greetings/complete', needsAuth: true },
  { name: '15-settings-account', path: '/settings/account', needsAuth: true },
  { name: '16-settings-app', path: '/settings/app', needsAuth: true },
  { name: '17-settings-notifications', path: '/settings/notifications', needsAuth: true },
  { name: '18-privacy', path: '/privacy', needsAuth: true },
  { name: '19-help', path: '/help', needsAuth: true },
  { name: '20-about', path: '/about', needsAuth: true },
  { name: '21-errors-camera-denied', path: '/errors/camera-denied', needsAuth: true },
  { name: '22-errors-offline', path: '/errors/offline', needsAuth: true },
  { name: '23-not-found', path: '/this-does-not-exist', needsAuth: true },
];

async function main() {
  const outDir = process.argv[2]
    ? resolve(process.argv[2])
    : resolve(
        process.cwd(),
        `screenshots/all-pages-${new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)}`,
      );
  await mkdir(outDir, { recursive: true });
  console.log(`[screenshots] writing to ${outDir}`);

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  });

  // Sign in as the dev account via the real API so the session cookie is set
  // before any authenticated route is visited.
  const apiContext = await context.request;
  const signin = await apiContext.post(`${BACKEND}/api/auth/sign-in`, {
    data: { email: 'dev@asl-pilot.local', password: 'asl-dev-password' },
  });
  if (!signin.ok()) {
    console.error('[screenshots] dev sign-in failed:', signin.status(), await signin.text());
    process.exit(1);
  }
  console.log('[screenshots] signed in as dev@asl-pilot.local');

  const page = await context.newPage();
  page.on('pageerror', (err) => console.warn('[pageerror]', err.message));

  let succeeded = 0;
  let failed = 0;

  for (const route of ROUTES) {
    const file = `${outDir}/${route.name}.png`;
    try {
      await page.goto(`${FRONTEND}${route.path}`, { waitUntil: 'domcontentloaded', timeout: 15_000 });
      // Let lazy chunks + fonts + first paint settle.
      await page.waitForLoadState('networkidle', { timeout: 8_000 }).catch(() => undefined);
      await page.waitForTimeout(400);
      if (route.prep) await route.prep(page);
      await page.screenshot({ path: file, fullPage: true });
      console.log(`  ✓ ${route.name.padEnd(30)} ${route.path}`);
      succeeded++;
    } catch (err) {
      console.log(`  ✗ ${route.name.padEnd(30)} ${route.path}  (${(err as Error).message.split('\n')[0]})`);
      try {
        await page.screenshot({ path: file, fullPage: true });
      } catch {
        /* page is wedged */
      }
      failed++;
    }
  }

  await browser.close();
  console.log(`\n[screenshots] done: ${succeeded} ok, ${failed} failed, in ${outDir}`);
  if (failed > 0) process.exitCode = 1;
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
