import { cors } from 'hono/cors';

/**
 * CORS configuration for the local-only dev setup.
 *
 * Frontend lives on http://localhost:5173 (Vite default). `credentials: true`
 * is required so the browser sends/receives the `asl_session` cookie on
 * cross-port requests.
 */
// Single-origin deploys (backend serves the SPA) don't trigger CORS, but allow
// an env-configured list so a split-origin or preview deploy still works.
// CORS_ORIGINS is a comma-separated list; defaults to the local Vite origin.
const allowedOrigins = (process.env.CORS_ORIGINS ?? 'http://localhost:5173')
  .split(',')
  .map((s) => s.trim())
  .filter(Boolean);

export const corsMiddleware = cors({
  origin: allowedOrigins,
  credentials: true,
  allowMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
});
