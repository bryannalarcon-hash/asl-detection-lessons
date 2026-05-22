import 'dotenv/config';
import { Hono } from 'hono';
import { serve } from '@hono/node-server';
import { sql as dbSql } from './db/client';
import { corsMiddleware } from './lib/cors';
import healthRoutes from './routes/health';
import authRoutes from './routes/auth';
import lessonsRoutes from './routes/lessons';
import progressRoutes from './routes/progress';

const app = new Hono();

app.use('/api/*', corsMiddleware);

app.route('/api/health', healthRoutes);
app.route('/api/auth', authRoutes);
app.route('/api/lessons', lessonsRoutes);
app.route('/api/progress', progressRoutes);

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

const port = Number(process.env.BACKEND_PORT ?? 3000);

await ensureMigrationsApplied();

serve({ fetch: app.fetch, port }, ({ port }) => {
  console.log(`[backend] listening on http://localhost:${port}`);
});
