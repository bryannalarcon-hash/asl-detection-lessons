/**
 * Test-side mirror of the dev-account credentials.
 *
 * The canonical source is `scripts/seed-dev-user.ts` (`DEV_EMAIL` /
 * `DEV_PASSWORD`). The frontend module `frontend/src/lib/dev-credentials.ts`
 * also mirrors them but cannot be imported directly from Playwright specs:
 * it reads `import.meta.env.VITE_DEV_TOOLS` at module load, which is
 * undefined under Playwright's Node TS loader.
 *
 * Keep these literals in lockstep with both of the above. If you rotate the
 * dev password, update all three.
 */

export const DEV_EMAIL = 'dev@asl-pilot.local';
export const DEV_PASSWORD = 'asl-dev-password';
