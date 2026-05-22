import { Hono } from 'hono';
import { eq, sql } from 'drizzle-orm';
import { z } from 'zod';
import { db } from '../db/client';
import { user } from '../db/schema';
import { clearSession, getSessionUserId, setSession } from '../lib/session';
import { hashPassword, verifyPassword } from '../lib/passwords';

const app = new Hono();

const DEV_EMAIL = 'dev@asl-pilot.local';
const DEV_DISPLAY_NAME = 'Dev User';

// Pre-computed bcrypt cost-12 hash of an unguessable random string. Used by
// /sign-in to keep response timing uniform between "no such user" and "wrong
// password" — verifyPassword against this hash always returns false but burns
// the same ~250ms a legitimate compare would. Regenerating this value has no
// security impact; it just needs to be a valid bcrypt hash that no user has.
const DUMMY_BCRYPT_HASH =
  '$2b$12$NZh/XrSP9rcieF/CQrOzJuD0.YnG28kM4s42MKE.SZHhzwm0Ezb2m';

/**
 * Dev-tools gate.
 *
 * `/dev-login` is a developer convenience and MUST be off in production
 * deployments. Default is ON for local + preview; set DEV_TOOLS_ENABLED=0
 * in prod env to disable. When gated off the endpoint returns 404 so the
 * URL surface is indistinguishable from "no such route".
 */
function devToolsEnabled(): boolean {
  return process.env.DEV_TOOLS_ENABLED !== '0';
}

// === Validation schemas ===

const signUpSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8).max(72), // bcrypt input cap is 72 bytes
  displayName: z.string().min(1).max(80),
});

const signInSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1).max(200), // permissive on sign-in; verify will fail
});

// === Helpers ===

async function safeParseJson(c: import('hono').Context): Promise<unknown | null> {
  try {
    return await c.req.json();
  } catch {
    return null;
  }
}

function userDto(row: { id: string; email: string; displayName: string }) {
  return { id: row.id, email: row.email, displayName: row.displayName };
}

// === Routes ===

/**
 * POST /api/auth/sign-up
 *
 * Body: { email, password, displayName }.
 * Creates a new user with a bcrypt-hashed password, sets the session cookie,
 * returns `{ user }`.
 *
 * NOTE on email verification: we intentionally leave `emailVerifiedAt: null`
 * here. Real email verification (transactional email + token flow) is
 * deferred until post-pilot — the pilot cohort signs up in-person with
 * known-good emails, so we don't gate sign-in on a verification click.
 *
 * Duplicate email handling: a unique index on LOWER(email) enforces
 * case-insensitive uniqueness. We pre-check (for a clean 409) and also
 * catch the Postgres 23505 unique_violation in case of a race.
 */
app.post('/sign-up', async (c) => {
  const body = await safeParseJson(c);
  if (body === null) {
    return c.json({ error: 'Invalid JSON body' }, 400);
  }

  const parsed = signUpSchema.safeParse(body);
  if (!parsed.success) {
    return c.json({ error: 'Invalid body', details: parsed.error.flatten() }, 400);
  }

  const { email, password, displayName } = parsed.data;
  const normalizedEmail = email.trim();

  // Pre-check for duplicate (case-insensitive against LOWER(email) unique index).
  const existing = await db
    .select({ id: user.id })
    .from(user)
    .where(sql`lower(${user.email}) = ${normalizedEmail.toLowerCase()}`)
    .limit(1);
  if (existing[0]) {
    return c.json({ error: 'Email already registered' }, 409);
  }

  const passwordHash = await hashPassword(password);

  let row;
  try {
    const inserted = await db
      .insert(user)
      .values({
        email: normalizedEmail,
        displayName,
        passwordHash,
        emailVerifiedAt: null,
      })
      .returning();
    row = inserted[0];
  } catch (err: unknown) {
    // Postgres unique_violation — race against the pre-check.
    const code = (err as { code?: string } | null)?.code;
    if (code === '23505') {
      return c.json({ error: 'Email already registered' }, 409);
    }
    throw err;
  }

  if (!row) {
    return c.json({ error: 'Failed to create user' }, 500);
  }

  setSession(c, row.id);
  return c.json({ user: userDto(row) });
});

/**
 * POST /api/auth/sign-in
 *
 * Body: { email, password }.
 * On success sets the session cookie and returns `{ user }`. On any failure
 * mode (no such user, no password set, wrong password) returns a uniform
 * 401 — never leaks which condition failed.
 */
app.post('/sign-in', async (c) => {
  const body = await safeParseJson(c);
  if (body === null) {
    return c.json({ error: 'Invalid JSON body' }, 400);
  }

  const parsed = signInSchema.safeParse(body);
  if (!parsed.success) {
    return c.json({ error: 'Invalid body', details: parsed.error.flatten() }, 400);
  }

  const { email, password } = parsed.data;

  const rows = await db
    .select()
    .from(user)
    .where(sql`lower(${user.email}) = ${email.trim().toLowerCase()}`)
    .limit(1);
  const row = rows[0];

  // Constant-time-ish path: ALWAYS run a bcrypt compare so the response time
  // for "no such user" matches the response time for "wrong password". A naive
  // early-return on missing user would leak ~250ms vs ~5ms, letting an
  // attacker enumerate registered emails. The dummy hash below is a real
  // cost-12 bcrypt of an unguessable string; verifyPassword against it always
  // returns false but burns the same CPU as a legitimate compare.
  const hashForCompare = row?.passwordHash ?? DUMMY_BCRYPT_HASH;
  const passwordOk = await verifyPassword(password, hashForCompare);

  if (!row || !passwordOk) {
    return c.json({ error: 'Invalid email or password' }, 401);
  }

  setSession(c, row.id);
  return c.json({ user: userDto(row) });
});

/**
 * POST /api/auth/dev-login
 *
 * Dev-only: finds-or-creates the seeded `dev@asl-pilot.local` user, sets the
 * session cookie, returns `{ user }`. Gated by DEV_TOOLS_ENABLED — when set
 * to '0' (production), this endpoint returns 404 and is undiscoverable.
 */
app.post('/dev-login', async (c) => {
  if (!devToolsEnabled()) {
    return c.json({ error: 'Not found' }, 404);
  }

  // Find by case-insensitive email match (matches the LOWER(email) unique index).
  const existing = await db
    .select()
    .from(user)
    .where(sql`lower(${user.email}) = ${DEV_EMAIL.toLowerCase()}`)
    .limit(1);

  let row = existing[0];
  if (!row) {
    const inserted = await db
      .insert(user)
      .values({
        email: DEV_EMAIL,
        displayName: DEV_DISPLAY_NAME,
        emailVerifiedAt: new Date(),
      })
      .returning();
    row = inserted[0];
  }

  if (!row) {
    return c.json({ error: 'Failed to create or fetch dev user' }, 500);
  }

  setSession(c, row.id);
  return c.json({ user: userDto(row) });
});

/**
 * POST /api/auth/sign-out
 *
 * Clears the session cookie. Always 200.
 */
app.post('/sign-out', (c) => {
  clearSession(c);
  return c.json({ ok: true });
});

/**
 * GET /api/auth/me
 *
 * Returns the current session user or 401.
 */
app.get('/me', async (c) => {
  const userId = getSessionUserId(c);
  if (!userId) return c.json({ error: 'Unauthorized' }, 401);

  const rows = await db.select().from(user).where(eq(user.id, userId)).limit(1);
  const row = rows[0];
  if (!row) {
    // Stale cookie — clear it
    clearSession(c);
    return c.json({ error: 'Unauthorized' }, 401);
  }

  return c.json({ user: userDto(row) });
});

export default app;
