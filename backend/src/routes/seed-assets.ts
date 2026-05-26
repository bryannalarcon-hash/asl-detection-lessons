import { Hono } from 'hono';
import { mkdir, writeFile, stat } from 'node:fs/promises';
import { dirname, join, resolve, sep } from 'node:path';
import { timingSafeEqual } from 'node:crypto';

/**
 * One-time admin route to populate the assets volume on a fresh deploy.
 *
 * The CV models and lesson videos are large + gitignored, so they don't ride
 * `railway up`. This lets us push them file-by-file into the mounted volume
 * (ASSETS_DIR) over HTTP, where the static handler in index.ts then serves
 * them at /models and /videos.
 *
 * It is OFF unless BOTH ASSETS_DIR and SEED_TOKEN are set in the environment,
 * and every request must present the token. After seeding, unset SEED_TOKEN
 * and redeploy to close it.
 */

const seed = new Hono();

const ASSETS_DIR = process.env.ASSETS_DIR;
const SEED_TOKEN = process.env.SEED_TOKEN;
const enabled = Boolean(ASSETS_DIR && SEED_TOKEN);

// Only files under these top-level dirs may be written, and only with these
// extensions — a request can't escape the volume or drop arbitrary scripts.
const ALLOWED_PREFIXES = ['models/', 'videos/'];
const ALLOWED_EXT = /\.(onnx|json|mp4|webm)$/i;

function tokenOk(provided: string | undefined): boolean {
  if (!SEED_TOKEN || !provided) return false;
  const a = Buffer.from(provided);
  const b = Buffer.from(SEED_TOKEN);
  return a.length === b.length && timingSafeEqual(a, b);
}

/**
 * Resolve a client-supplied relative path against the volume root and confirm
 * it stays inside it (defends against `..`, absolute paths, symlink-ish input).
 * Returns null if the path is disallowed.
 */
function safeTarget(rel: string | undefined): string | null {
  if (!rel || !ASSETS_DIR) return null;
  if (rel.includes('\0')) return null;
  if (!ALLOWED_PREFIXES.some((p) => rel.startsWith(p))) return null;
  if (!ALLOWED_EXT.test(rel)) return null;
  const root = resolve(ASSETS_DIR);
  const target = resolve(root, rel);
  if (target !== root && !target.startsWith(root + sep)) return null;
  return target;
}

seed.put('/asset', async (c) => {
  if (!enabled) return c.json({ error: 'seed route disabled' }, 404);
  if (!tokenOk(c.req.header('x-seed-token'))) {
    return c.json({ error: 'unauthorized' }, 401);
  }
  const target = safeTarget(c.req.query('path'));
  if (!target) return c.json({ error: 'invalid path' }, 400);

  const body = Buffer.from(await c.req.arrayBuffer());
  if (body.length === 0) return c.json({ error: 'empty body' }, 400);

  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, body);
  return c.json({ ok: true, path: c.req.query('path'), bytes: body.length });
});

seed.get('/manifest', async (c) => {
  if (!enabled) return c.json({ error: 'seed route disabled' }, 404);
  if (!tokenOk(c.req.header('x-seed-token'))) {
    return c.json({ error: 'unauthorized' }, 401);
  }
  const root = resolve(ASSETS_DIR as string);
  const files: Array<{ path: string; bytes: number }> = [];
  async function walk(dir: string, relBase: string): Promise<void> {
    const { readdir } = await import('node:fs/promises');
    let entries;
    try {
      entries = await readdir(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      const abs = join(dir, e.name);
      const rel = relBase ? `${relBase}/${e.name}` : e.name;
      if (e.isDirectory()) await walk(abs, rel);
      else {
        const s = await stat(abs);
        files.push({ path: rel, bytes: s.size });
      }
    }
  }
  await walk(root, '');
  files.sort((a, b) => a.path.localeCompare(b.path));
  return c.json({ count: files.length, totalBytes: files.reduce((n, f) => n + f.bytes, 0), files });
});

export default seed;
