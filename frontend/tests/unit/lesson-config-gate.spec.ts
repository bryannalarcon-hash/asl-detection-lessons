import { describe, it, expect, beforeEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  readLessonConfig,
  writeLessonConfig,
  clearLessonConfig,
  configFromSigns,
  defaultSignConfig,
  type LessonConfig,
} from '../../src/lib/lesson-config';

/**
 * Unit spec for the dev Lesson Config overlay.
 *
 * Two concerns:
 *   1. Persistence round-trip (read/write/clear + validation) — pure localStorage.
 *   2. The OFF-case gating contract: the editor page + the dev route + the
 *      practice overlay read are all guarded by `isDevToolsEnabled()`, which
 *      collapses to a build-time constant. We can't flip the Vite-inlined env
 *      at runtime (see dev-tools-gate.spec.ts), so instead we assert by SOURCE
 *      that every consumer is gated. This catches anyone removing a guard and
 *      leaking the dev surface (or its localStorage read) into prod.
 */

const SRC = resolve(__dirname, '../../src');

function read(rel: string): string {
  return readFileSync(resolve(SRC, rel), 'utf8');
}

describe('lesson-config persistence', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('round-trips a per-stage config keyed by slug', () => {
    const cfg: LessonConfig = {
      slug: 'lesson-1',
      signs: [
        {
          sign: 'hello',
          videoSrc: '/videos/lessons/hello.mp4',
          stages: {
            handshape: { segment: { startSec: 0, endSec: 1.2 }, reps: 5 },
            movement: { segment: { startSec: 1.2, endSec: 2.5 }, reps: 2 },
            sign: { segment: { startSec: 0, endSec: 0 }, reps: 3 },
          },
        },
      ],
    };
    writeLessonConfig(cfg);
    expect(readLessonConfig('lesson-1')).toEqual(cfg);
  });

  it('returns null for an absent or empty config', () => {
    expect(readLessonConfig('nope')).toBeNull();
    writeLessonConfig({ slug: 'lesson-2', signs: [] });
    // Empty sign list is treated as "no overlay".
    expect(readLessonConfig('lesson-2')).toBeNull();
  });

  it('drops malformed signs and falls back to null when none survive', () => {
    window.localStorage.setItem(
      'asl-pilot.lessonConfig.v2.lesson-3',
      JSON.stringify({ slug: 'lesson-3', signs: [{ sign: 'x' }] })
    );
    expect(readLessonConfig('lesson-3')).toBeNull();
  });

  it('clears a config', () => {
    writeLessonConfig({
      slug: 'lesson-4',
      signs: [defaultSignConfig('hello')],
    });
    clearLessonConfig('lesson-4');
    expect(readLessonConfig('lesson-4')).toBeNull();
  });

  it('seeds defaults from a lesson signs list', () => {
    const cfg = configFromSigns('lesson-5', [{ slug: 'a' }, { slug: 'b' }]);
    expect(cfg.signs).toHaveLength(2);
    expect(cfg.signs[0]).toEqual(defaultSignConfig('a'));
    expect(cfg.signs[0].stages.handshape.reps).toBe(3);
  });
});

describe('lesson-config dev-gating contract (source-level, OFF-case lock)', () => {
  it('the editor page early-returns behind isDevToolsEnabled()', () => {
    const page = read('pages/DevLessonConfig.tsx');
    expect(page).toContain("from '@/lib/env'");
    expect(page).toContain('isDevToolsEnabled()');
  });

  it('the dev route is gated so DCE drops it from prod bundles', () => {
    const router = read('router.tsx');
    expect(router).toContain('isDevToolsEnabled()');
    expect(router).toContain('/dev/lesson-config');
  });

  it('the practice overlay read is gated so prod never applies dev config', () => {
    const practice = read('pages/Practice.tsx');
    expect(practice).toContain('isDevToolsEnabled()');
    expect(practice).toContain('readLessonConfig');
  });

  it('the lesson-intro entry link is gated', () => {
    const intro = read('pages/LessonIntro.tsx');
    expect(intro).toContain('isDevToolsEnabled()');
    expect(intro).toContain('dev-lesson-config-link');
  });
});
