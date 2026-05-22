import { cors } from 'hono/cors';

/**
 * CORS configuration for the local-only dev setup.
 *
 * Frontend lives on http://localhost:5173 (Vite default). `credentials: true`
 * is required so the browser sends/receives the `asl_session` cookie on
 * cross-port requests.
 */
export const corsMiddleware = cors({
  origin: ['http://localhost:5173'],
  credentials: true,
  allowMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
});
