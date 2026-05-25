/**
 * Dev-only per-lesson configuration overlay.
 *
 * A dev account can override, per lesson:
 *   - which signs the lesson contains (and how many),
 *   - per sign, per STAGE (handshape / movement / whole-sign): the
 *     reference-clip sub-range [startSec, endSec] to show during that stage,
 *     and how many reps the student repeats that stage.
 *
 * The three stages are the handshape/movement/sign micro-stages the practice
 * machine cycles through for each sign. Each stage carries its own trim and its
 * own rep count, so a sign can show the first second of the clip during the
 * handshape stage, the middle during movement, and the whole thing for the
 * full sign -- each repeated a different number of times.
 *
 * Persisted in localStorage keyed by lesson slug, mirroring the read/write +
 * try-catch + versioned-key pattern in `practice-resume.ts` and `settings.ts`.
 * The practice flow overlays this on top of the backend/fallback defaults.
 *
 * Build-time gated: consumers live behind `isDevToolsEnabled()`, so the editor
 * and overlay reads are dropped from prod bundles when VITE_DEV_TOOLS=0.
 */
import type { DrillType } from '@/cv/types';

const CONFIG_PREFIX = 'asl-pilot.lessonConfig.v2.';

/** Where per-sign reference clips are served from. */
export const LESSON_VIDEO_BASE = '/videos/lessons/';

export type StageType = DrillType; // 'handshape' | 'movement' | 'sign'

export const STAGE_ORDER: StageType[] = ['handshape', 'movement', 'sign'];

export const STAGE_LABEL: Record<StageType, string> = {
  handshape: 'Handshape',
  movement: 'Movement',
  sign: 'Whole sign',
};

export interface StageSegment {
  startSec: number;
  endSec: number;
}

export interface StageConfig {
  /** Clip sub-range for this stage. {0,0} means "use the natural segment". */
  segment: StageSegment;
  /** How many times the student repeats this stage. */
  reps: number;
}

export interface SignConfig {
  /** Sign slug (e.g. "hello"). Matches a backend/fallback sign. */
  sign: string;
  /** Reference-clip source for this sign. */
  videoSrc: string;
  /** Per-stage trim + reps, keyed by stage. */
  stages: Record<StageType, StageConfig>;
}

export interface LessonConfig {
  slug: string;
  signs: SignConfig[];
}

export const DEFAULT_REPS = 3;
export const DEFAULT_SEGMENT: StageSegment = { startSec: 0, endSec: 0 };

/** True when a segment is unset (both bounds 0) — the natural/auto segment. */
export function isAutoSegment(seg: StageSegment | undefined): boolean {
  return !seg || (seg.startSec === 0 && seg.endSec === 0);
}

/** Reference-clip path for a sign slug. */
export function videoSrcForSign(sign: string): string {
  return `${LESSON_VIDEO_BASE}${sign}.mp4`;
}

function defaultStage(): StageConfig {
  return { segment: { ...DEFAULT_SEGMENT }, reps: DEFAULT_REPS };
}

/** A sensible default sign config: all three stages, default reps, no trim. */
export function defaultSignConfig(sign: string): SignConfig {
  return {
    sign,
    videoSrc: videoSrcForSign(sign),
    stages: {
      handshape: defaultStage(),
      movement: defaultStage(),
      sign: defaultStage(),
    },
  };
}

function isSegment(v: unknown): v is StageSegment {
  if (!v || typeof v !== 'object') return false;
  const s = v as Record<string, unknown>;
  return typeof s.startSec === 'number' && typeof s.endSec === 'number';
}

function isStage(v: unknown): v is StageConfig {
  if (!v || typeof v !== 'object') return false;
  const s = v as Record<string, unknown>;
  return typeof s.reps === 'number' && isSegment(s.segment);
}

function isSignConfig(v: unknown): v is SignConfig {
  if (!v || typeof v !== 'object') return false;
  const s = v as Record<string, unknown>;
  if (typeof s.sign !== 'string' || typeof s.videoSrc !== 'string') return false;
  const stages = s.stages as Record<string, unknown> | undefined;
  if (!stages) return false;
  return STAGE_ORDER.every((st) => isStage(stages[st]));
}

/** Read a lesson's dev config overlay, or null if none/invalid. */
export function readLessonConfig(slug: string): LessonConfig | null {
  if (!slug || typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(CONFIG_PREFIX + slug);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<LessonConfig>;
    if (!Array.isArray(parsed.signs)) return null;
    const signs = parsed.signs.filter(isSignConfig);
    if (signs.length === 0) return null;
    return { slug, signs };
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
      JSON.stringify({ slug: config.slug, signs: config.signs })
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

/** Build a starting config from the lesson's default signs. */
export function configFromSigns(
  slug: string,
  signs: { slug: string }[]
): LessonConfig {
  return {
    slug,
    signs: signs.map((s) => defaultSignConfig(s.slug)),
  };
}
