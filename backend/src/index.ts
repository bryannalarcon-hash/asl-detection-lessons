/**
 * Backend entry point: builds the Hono app, wires CORS plus the health, auth,
 * lessons, progress, and seed-asset API routes, and serves runtime assets and
 * the built SPA. Verifies migrations are applied before binding the HTTP server.
 */
import 'dotenv/config';
import { Hono } from 'hono';
import { serve } from '@hono/node-server';
import { serveStatic } from '@hono/node-server/serve-static';
import { sql as dbSql } from './db/client';
import { corsMiddleware } from './lib/cors';
import healthRoutes from './routes/health';
import authRoutes from './routes/auth';
import lessonsRoutes from './routes/lessons';
import progressRoutes from './routes/progress';
import seedAssetsRoutes from './routes/seed-assets';

const app = new Hono();

app.use('/api/*', corsMiddleware);

app.route('/api/health', healthRoutes);
app.route('/api/auth', authRoutes);
app.route('/api/lessons', lessonsRoutes);
app.route('/api/progress', progressRoutes);
app.route('/api/_seed', seedAssetsRoutes);

// Large runtime assets (CV models, lesson videos) live on a mounted volume in
// prod (ASSETS_DIR) because they're gitignored + too big to ride the deploy
// upload. Serve them from there ahead of the SPA fallback; a miss falls through
// to the SPA static below. Unset locally, where they sit in frontend/public.
const ASSETS_DIR = process.env.ASSETS_DIR;
if (ASSETS_DIR) {
  app.use('/models/*', serveStatic({ root: ASSETS_DIR }));
  app.use('/videos/*', serveStatic({ root: ASSETS_DIR }));
}

// Serve the built SPA (frontend/dist) for everything non-/api. In single-service
// deploys (Railway) this hosts the app + API under one origin; in local dev the
// dist is absent and these no-op (the frontend runs on Vite). STATIC_ROOT lets
// the deploy point at the build output.
const STATIC_ROOT = process.env.STATIC_ROOT ?? 'frontend/dist';
app.use('/*', serveStatic({ root: STATIC_ROOT }));
// SPA fallback: unmatched non-file routes return index.html for client routing.
app.get('/*', serveStatic({ path: `${STATIC_ROOT}/index.html` }));

/**
 * Boot-time safety: refuse to start if migrations haven't been applied.
 *
 * We query `__drizzle_migrations` (the bookkeeping table Drizzle creates the
 * first time you run `db:migrate`). A "relation does not exist" error means
 * the developer hasn't migrated yet — exit with a clear message rather than
 * limping along until the first failing query.
 *
 * Other errors (DB down, auth failure, etc.) are logged at warn level but do
 * NOT exit — the server still boots so `/api/health` can report
 * `dbReachable: false` and aid debugging.
 */
async function ensureMigrationsApplied(): Promise<void> {
  try {
    // drizzle-kit migrate (CLI) writes to `drizzle.__drizzle_migrations`,
    // while older programmatic runs write to `public.__drizzle_migrations`.
    // Accept either: check for the bookkeeping table in either schema. If
    // both are missing we fall through to the "does not exist" branch.
    await dbSql`
      SELECT 1
      WHERE EXISTS (
        SELECT 1 FROM pg_tables
        WHERE tablename = '__drizzle_migrations'
          AND schemaname IN ('drizzle', 'public')
      )
    `;
    // Above returns rows when at least one matching table exists. If neither
    // exists, the SELECT returns zero rows but does NOT throw — so we
    // explicitly probe public."user" as a defensive double-check.
    await dbSql`SELECT 1 FROM public."user" LIMIT 1`;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    if (message.includes('does not exist')) {
      console.error('Run npm run db:migrate first');
      process.exit(1);
    }
    // DB unreachable / auth error / etc. — let the server boot so health
    // and any future read-only endpoints can report state.
    console.warn(`[backend] db precheck warning (server will still start): ${message}`);
  }
}

// Railway (and most PaaS) inject PORT; fall back to BACKEND_PORT then 3000.
const port = Number(process.env.PORT ?? process.env.BACKEND_PORT ?? 3000);

await ensureMigrationsApplied();

serve({ fetch: app.fetch, port }, ({ port }) => {
  console.log(`[backend] listening on http://localhost:${port}`);
});
