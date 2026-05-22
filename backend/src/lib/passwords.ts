// Password hashing helpers backed by bcryptjs.
//
// Cost factor 12 is the project standard. Bcryptjs (pure JS) is intentional —
// avoids native build steps on student/laptop dev envs (no node-gyp / Python
// toolchain required). For higher-throughput auth we can swap to argon2 later.
import bcrypt from 'bcryptjs';

const BCRYPT_COST = 12;

/** Hash a plaintext password. Caller is responsible for length validation. */
export async function hashPassword(plain: string): Promise<string> {
  return bcrypt.hash(plain, BCRYPT_COST);
}

/**
 * Verify a plaintext password against a bcrypt hash.
 *
 * Returns false (does NOT throw) when `hash` is null/empty so route handlers
 * can treat "user has no password yet" identically to "wrong password" —
 * never leaking that distinction back to the client.
 */
export async function verifyPassword(
  plain: string,
  hash: string | null | undefined,
): Promise<boolean> {
  if (!hash) return false;
  try {
    return await bcrypt.compare(plain, hash);
  } catch {
    return false;
  }
}
