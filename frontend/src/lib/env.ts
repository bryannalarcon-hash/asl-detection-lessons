// Typed access to import.meta.env. Centralized so we don't litter checks across the app.

interface AppEnv {
  /**
   * '1' when the build is treated as a dev build.
   * Historically also gated dev UI affordances — prefer `DEV_TOOLS` / `isDevToolsEnabled()`
   * for any new dev-only UI (skip-login, dev panels, force-state toolboxes).
   */
  DEV_MODE: string;
  /**
   * Controls whether dev affordances are rendered in the UI
   * (Skip-login button, mock-CV dev panel, force-state buttons, camera dev toolbox).
   * Defaults to ON; explicitly set `VITE_DEV_TOOLS=0` to hide all dev UI
   * (useful for previewing the real user experience while keeping a dev build).
   */
  DEV_TOOLS: string;
  /** Backend base URL. Defaults to http://localhost:3000. */
  API_URL: string;
  /** Optional bundle URL for the ML model (v2). */
  MODEL_BUNDLE_URL: string | undefined;
}

const meta = (import.meta as ImportMeta & { env: Record<string, string | undefined> }).env;

export const env: AppEnv = {
  DEV_MODE: meta.VITE_DEV_MODE ?? '1',
  DEV_TOOLS: meta.VITE_DEV_TOOLS ?? '1',
  API_URL: meta.VITE_API_URL ?? 'http://localhost:3000',
  MODEL_BUNDLE_URL: meta.VITE_MODEL_BUNDLE_URL,
};

/**
 * Legacy "is this a dev build" check. Kept for compatibility with anything that
 * conceptually means "dev build" rather than "show dev UI" (e.g. enabling
 * React StrictMode, allowing dev-only API endpoints).
 *
 * Prefer `isDevToolsEnabled()` for any new dev-only UI gating.
 */
export const isDevMode = () => env.DEV_MODE === '1';

/**
 * Gate for dev-only UI affordances (Skip-login button, dev panels, force-state
 * toolboxes, camera dev toolbox, etc.). Defaults ON so local dev "just works";
 * set `VITE_DEV_TOOLS=0` to preview the real user experience.
 */
export const isDevToolsEnabled = () => env.DEV_TOOLS !== '0';
