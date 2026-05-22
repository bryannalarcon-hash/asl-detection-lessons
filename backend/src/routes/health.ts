import { Hono } from 'hono';
import { sql as dbSql } from '../db/client';

const app = new Hono();

/**
 * GET /api/health
 *
 * Lightweight liveness check that also reports DB reachability. The DB check
 * has a 500ms timeout so a downed Postgres doesn't slow this endpoint.
 */
app.get('/', async (c) => {
  const dbReachable = await checkDbReachable();
  return c.json({ ok: true, dbReachable });
});

async function checkDbReachable(): Promise<boolean> {
  try {
    const timeoutPromise = new Promise<never>((_, reject) => {
      setTimeout(() => reject(new Error('db-check-timeout')), 500);
    });
    await Promise.race([dbSql`SELECT 1`, timeoutPromise]);
    return true;
  } catch {
    return false;
  }
}

export default app;
