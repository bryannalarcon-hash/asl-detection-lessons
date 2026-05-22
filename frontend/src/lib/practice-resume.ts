/**
 * Resume-cursor persistence for the Practice screen.
 *
 * Keyed by lesson slug. Stores the (signIndex, drillIndex, repIndex) tuple
 * + an `updatedAt` epoch. Read on Practice mount (if <7 days old). Written
 * on every cursor change. Cleared when the machine reaches LESSON_COMPLETE.
 */

const RESUME_PREFIX = 'asl-pilot.practice-resume.';
const RESUME_MAX_AGE_MS = 1000 * 60 * 60 * 24 * 7; // 7 days

export interface ResumeState {
  signIndex: number;
  drillIndex: number;
  repIndex: number;
  updatedAt: number;
}

export function readResume(slug: string): ResumeState | null {
  if (!slug || typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(RESUME_PREFIX + slug);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ResumeState>;
    if (
      typeof parsed.signIndex !== 'number' ||
      typeof parsed.drillIndex !== 'number' ||
      typeof parsed.repIndex !== 'number' ||
      typeof parsed.updatedAt !== 'number'
    ) {
      return null;
    }
    if (Date.now() - parsed.updatedAt > RESUME_MAX_AGE_MS) return null;
    return parsed as ResumeState;
  } catch {
    return null;
  }
}

export function writeResume(slug: string, partial: Omit<ResumeState, 'updatedAt'>): void {
  if (!slug || typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(
      RESUME_PREFIX + slug,
      JSON.stringify({ ...partial, updatedAt: Date.now() })
    );
  } catch {
    // localStorage full or disabled — non-fatal.
  }
}

export function clearResume(slug: string): void {
  if (!slug || typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(RESUME_PREFIX + slug);
  } catch {
    // ignore
  }
}
