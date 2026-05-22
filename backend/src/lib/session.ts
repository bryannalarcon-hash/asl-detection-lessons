import type { Context } from 'hono';
import { setCookie, getCookie, deleteCookie } from 'hono/cookie';

/**
 * Dev-grade session handling.
 *
 * The cookie value is the user UUID stored as plain text. This is intentional
 * scaffold-grade: no signing, no encryption, no opaque token. Per the PRD,
 * real auth (Better Auth / Lucia / hand-rolled with signing) is deferred.
 *
 * For production: wrap the value with HMAC signing or replace with an opaque
 * session ID + `session` table lookup.
 */

export const SESSION_COOKIE_NAME = 'asl_session';

const COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30; // 30 days

export function setSession(c: Context, userId: string): void {
  setCookie(c, SESSION_COOKIE_NAME, userId, {
    httpOnly: true,
    sameSite: 'Lax',
    secure: false, // dev only — set true behind HTTPS in prod
    path: '/',
    maxAge: COOKIE_MAX_AGE_SECONDS,
  });
}

export function clearSession(c: Context): void {
  deleteCookie(c, SESSION_COOKIE_NAME, { path: '/' });
}

export function getSessionUserId(c: Context): string | null {
  const value = getCookie(c, SESSION_COOKIE_NAME);
  if (!value) return null;
  // Basic UUID shape sanity check — full validation happens when the DB lookup
  // returns no user.
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)) {
    return null;
  }
  return value;
}
