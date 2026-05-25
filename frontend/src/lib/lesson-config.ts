/**
 * Dev-only per-lesson configuration overlay.
 *
 * A dev account can override, per lesson:
 *   - how many drills the lesson contains (drill count),
 *   - per drill: which sign + the reference-clip segment [startSec, endSec],
 *   - how many reps the student repeats each drill.
 *
 * In this overlay a "drill" is one sign-practice unit (sign + video segment +
 * reps), NOT the handshape/movement/sign micro-stages the practice machine
 * cycles internally. The lesson's drill count is therefore the number of signs
 * presented.
 *
 * Persisted in localStorage keyed by lesson slug, mirroring the read/write +
 * try-catch + versioned-key pattern in `practice-resume.ts` and `settings.ts`.
 * The practice flow overlays this on top of the backend/fallback defaults so
 * reps, segments, and drill count actually take effect.
 *
 * Build-time gated: this module's consumers live behind `isDevToolsEnabled()`,
 * and the editor UI is dropped from prod bundles via Vite `define` + DCE when
 * VITE_DEV_TOOLS=0. The config never affects prod default lessons.
 */

const CONFIG_PREFIX = 'asl-pilot.lessonConfig.v1.';

/** Where per-sign reference clips will be served from once available. */
export const LESSON_VIDEO_BASE = '/videos/lessons/';

export interface DrillSegment {
  startSec: number;
  endSec: number;
}

export interface DrillConfig {
  /** Sign slug this drill drills (e.g. "hello"). Matches a backend/fallback sign. */
  sign: string;
  /** Reference-clip source for this drill's sign. */
  videoSrc: string;
  /** Sub-range of the clip to show. */
  segment: DrillSegment;
  /** How many times the student repeats this drill. */
  reps: number;
}

export interface LessonConfig {
  slug: string;
  drills: DrillConfig[];
}

export const DEFAULT_REPS = 3;
export const DEFAULT_SEGMENT: DrillSegment = { startSec: 0, endSec: 0 };

/** Reference-clip path for a sign slug (placeholder until clips are served). */
export function videoSrcForSign(sign: string): string {
  return `${LESSON_VIDEO_BASE}${sign}.mp4`;
}

/** A sensible default drill for a given sign slug. */
export function defaultDrillForSign(sign: string): DrillConfig {
  return {
    sign,
    videoSrc: videoSrcForSign(sign),
    segment: { ...DEFAULT_SEGMENT },
    reps: DEFAULT_REPS,
  };
}

function isSegment(v: unknown): v is DrillSegment {
  if (!v || typeof v !== 'object') return false;
  const s = v as Record<string, unknown>;
  return typeof s.startSec === 'number' && typeof s.endSec === 'number';
}

function isDrill(v: unknown): v is DrillConfig {
  if (!v || typeof v !== 'object') return false;
  const d = v as Record<string, unknown>;
  return (
    typeof d.sign === 'string' &&
    typeof d.videoSrc === 'string' &&
    typeof d.reps === 'number' &&
    isSegment(d.segment)
  );
}

/** Read a lesson's dev config overlay, or null if none/invalid. */
export function readLessonConfig(slug: string): LessonConfig | null {
  if (!slug || typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(CONFIG_PREFIX + slug);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<LessonConfig>;
    if (!Array.isArray(parsed.drills)) return null;
    const drills = parsed.drills.filter(isDrill);
    if (drills.length === 0) return null;
    return { slug, drills };
  } catch {
    return null;
  }
}

/** Persist a lesson's dev config overlay. */
export function writeLessonConfig(config: LessonConfig): void {
  if (!config.slug || typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(
      CONFIG_PREFIX + config.slug,
      JSON.stringify({ slug: config.slug, drills: config.drills })
    );
  } catch {
    // localStorage full or disabled — non-fatal.
  }
}

/** Remove a lesson's dev config overlay (revert to defaults). */
export function clearLessonConfig(slug: string): void {
  if (!slug || typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(CONFIG_PREFIX + slug);
  } catch {
    // ignore
  }
}

/**
 * Build a starting config from the lesson's default signs. Each default sign
 * becomes one drill with default reps and a placeholder segment.
 */
export function configFromSigns(
  slug: string,
  signs: { slug: string }[]
): LessonConfig {
  return {
    slug,
    drills: signs.map((s) => defaultDrillForSign(s.slug)),
  };
}
