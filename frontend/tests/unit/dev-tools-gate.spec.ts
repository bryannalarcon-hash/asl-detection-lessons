import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Unit spec for the dev-tools gate.
 *
 * The production module under test is `frontend/src/lib/env.ts`. Its gating
 * function is a one-liner:
 *
 *   export const isDevToolsEnabled = () => env.DEV_TOOLS !== '0';
 *   where env.DEV_TOOLS = import.meta.env.VITE_DEV_TOOLS ?? '1'
 *
 * Vite inlines `import.meta.env.*` at transform time, so once env.ts is loaded
 * once we can't flip the value via `vi.stubEnv` and re-import — Vite has
 * already baked the build-time value in. (Verified experimentally: stubEnv
 * updates the test scope's `import.meta.env` but not the dynamically imported
 * module's snapshot.)
 *
 * To keep the gating LOGIC under test (not just the literal text), we:
 *
 *   1. Read env.ts as a string and assert the gating formula is still
 *      `env.DEV_TOOLS !== '0'`. This catches anyone "fixing" the gate to
 *      use `=== '1'` (which would flip the default-on behavior when
 *      VITE_DEV_TOOLS is unset).
 *   2. Re-implement the same defaulting + comparison rule and table-test it.
 *
 * Plus a live integration check on the actually-loaded module so we know the
 * exported function exists and is callable.
 */

const ENV_PATH = resolve(__dirname, '../../src/lib/env.ts');

/**
 * Pure mirror of `env.ts`'s gating rule. Kept tiny + literal so any drift
 * in env.ts will fail the "source text contains the canonical formula"
 * assertion below.
 */
function gateUnderTest(viteDevTools: string | undefined): boolean {
  const value = viteDevTools ?? '1';
  return value !== '0';
}

describe('isDevToolsEnabled — gating rule', () => {
  let envSource = '';

  beforeEach(() => {
    envSource = readFileSync(ENV_PATH, 'utf8');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("env.ts source still implements the canonical gating formula", () => {
    // If this assertion ever fails, the rule has moved and the table-test
    // below no longer covers the real production path.
    expect(envSource).toContain("env.DEV_TOOLS !== '0'");
    expect(envSource).toContain("meta.VITE_DEV_TOOLS ?? '1'");
  });

  it.each([
    { input: '0', expected: false, label: "VITE_DEV_TOOLS = '0' → OFF" },
    { input: '1', expected: true, label: "VITE_DEV_TOOLS = '1' → ON" },
    { input: '', expected: true, label: "VITE_DEV_TOOLS = '' → ON (only '0' is OFF)" },
    {
      input: undefined,
      expected: true,
      label: 'VITE_DEV_TOOLS missing → ON (default = "1")',
    },
  ])('$label', ({ input, expected }) => {
    expect(gateUnderTest(input)).toBe(expected);
  });

  it('the live env module exports a callable isDevToolsEnabled', async () => {
    const mod = await import('../../src/lib/env');
    expect(typeof mod.isDevToolsEnabled).toBe('function');
    // Default config under vitest is ON (no VITE_DEV_TOOLS=0 set).
    expect(mod.isDevToolsEnabled()).toBe(true);
  });
});
