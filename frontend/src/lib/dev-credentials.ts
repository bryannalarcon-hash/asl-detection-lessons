/**
 * Dev-account credentials surfaced by the seed script.
 *
 * Build-time gated: when VITE_DEV_TOOLS === '0', the literal strings below
 * never appear in the compiled bundle. Vite's `define` inlines
 * `import.meta.env.VITE_DEV_TOOLS` at build time, the ternary collapses to a
 * constant, and dead-code elimination drops the unused branch. This matters
 * because the dev password is a real credential against /api/auth/sign-in —
 * shipping it in a prod JS bundle would let anyone log in as the seeded user.
 *
 * Hard prod-deploy precondition: set `VITE_DEV_TOOLS=0` AND don't seed the
 * dev account on prod databases (see docs/handoffs/HANDOFF_FRONTEND.md "Gotchas").
 *
 * These must mirror `DEV_EMAIL` / `DEV_PASSWORD` in
 * `scripts/seed-dev-user.ts`. The seed script is the source of truth.
 */

const devToolsEnabled = import.meta.env.VITE_DEV_TOOLS !== '0';

export const DEV_EMAIL: string = devToolsEnabled ? 'dev@asl-pilot.local' : '';
export const DEV_PASSWORD: string = devToolsEnabled ? 'asl-dev-password' : '';

export const hasDevCredentials = (): boolean =>
  DEV_EMAIL.length > 0 && DEV_PASSWORD.length > 0;
