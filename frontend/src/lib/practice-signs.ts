/**
 * Builds the PracticeSign list the practice machine consumes, collapsing each
 * backend sign to a single full-sign drill. Also applies a dev Lesson Config overlay,
 * letting it redefine the sign set, order, per-stage reps, and reference-clip trim.
 */
import type { PracticeSign } from '@/lib/machines/practice';
import { isAutoSegment, type LessonConfig } from '@/lib/lesson-config';
import type { DrillType } from '@/cv/types';

/**
 * Build practice signs from backend data. The lesson plan presents only the
 * full-sign stage, so the handshape/movement drills are dropped here and each
 * sign keeps exactly one drill (`drillType === 'sign'`). When the backend
 * omits a sign drill, the first available drill is retargeted as the sign so
 * the sign still has a stage to run.
 */
export function buildSignsFromBackend(
  signs: { id: string; slug: string; englishGloss: string }[],
  drills: { signId: string; drillType: DrillType; targetString: string; orderIndex: number }[]
): PracticeSign[] {
  return signs.map((sign) => {
    const signDrills = drills
      .filter((d) => d.signId === sign.id)
      .sort((a, b) => a.orderIndex - b.orderIndex)
      .map((d) => ({ drillType: d.drillType, target: d.targetString }));
    return {
      id: sign.id,
      slug: sign.slug,
      englishGloss: sign.englishGloss,
      drills: toFullSignDrills(signDrills, sign.englishGloss),
    };
  });
}

/**
 * Collapse a sign's drill list to a single full-sign drill. Prefers the
 * existing `sign` stage (carrying any reps/segment overlay); falls back to the
 * first drill retargeted as the sign, or a synthesized drill when the list is
 * empty, so every sign always has exactly one stage to practice.
 */
function toFullSignDrills(
  drills: PracticeSign['drills'],
  englishGloss: string
): PracticeSign['drills'] {
  const signDrill = drills.find((d) => d.drillType === 'sign');
  if (signDrill) return [signDrill];
  const first = drills[0];
  if (first) return [{ ...first, drillType: 'sign' }];
  return [{ drillType: 'sign', target: englishGloss }];
}

/**
 * Apply a dev Lesson Config overlay onto the default signs. The overlay's sign
 * list defines the lesson's sign count and order; each entry carries per-stage
 * reps + clip trim. We overlay onto each sign's existing drills by matching
 * stage (drillType). Unknown slugs are dropped. An unset trim ({0,0}) is left
 * off so the reference video falls back to its natural segment.
 */
export function applyLessonConfig(
  defaults: PracticeSign[],
  config: LessonConfig
): PracticeSign[] {
  const bySlug = new Map(defaults.map((s) => [s.slug, s]));
  const out: PracticeSign[] = [];
  for (const sc of config.signs) {
    const base = bySlug.get(sc.sign);
    if (!base) continue;
    out.push({
      ...base,
      videoSrc: sc.videoSrc,
      drills: base.drills.map((d) => {
        const stage = sc.stages[d.drillType];
        if (!stage) return d;
        return {
          ...d,
          reps: stage.reps,
          segment: isAutoSegment(stage.segment) ? undefined : stage.segment,
        };
      }),
    });
  }
  return out.length > 0 ? out : defaults;
}
