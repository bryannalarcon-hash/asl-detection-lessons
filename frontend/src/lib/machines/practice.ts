// XState v5 practice machine. See docs/ux-spec.md §"Hierarchy of state machines".
// Lesson → Sign → Drill → Rep. Drill cycle: handshape → movement → sign. 3 reps each.
import { setup, assign } from 'xstate';
import type { DrillType } from '@/cv/types';

export interface PracticeSign {
  id: string;
  slug: string;
  englishGloss: string;
  drills: { drillType: DrillType; target: string }[];
}

export interface PracticeContext {
  signs: PracticeSign[];
  signIndex: number;
  drillIndex: number;
  repIndex: number;
  repsPerDrill: number;
  lastOutcome: 'pass' | 'fail' | 'skip' | null;
}

export type PracticeEvent =
  | { type: 'START' }
  | { type: 'PROMPT_READY' }
  | { type: 'COUNTDOWN_DONE' }
  | { type: 'REC_DONE' }
  | { type: 'PASS' }
  | { type: 'FAIL' }
  | { type: 'SKIP' }
  | { type: 'SKIP_DRILL' }
  | { type: 'BACK_DRILL' }
  | { type: 'BACK_SIGN' }
  | { type: 'RESET' };

interface CreateInput {
  signs: PracticeSign[];
  repsPerDrill?: number;
  /** Resume cursor — restored from localStorage on Practice mount. */
  initialSignIndex?: number;
  initialDrillIndex?: number;
  initialRepIndex?: number;
}

export const practiceMachine = setup({
  types: {
    context: {} as PracticeContext,
    events: {} as PracticeEvent,
    input: {} as CreateInput,
  },
  guards: {
    hasMoreReps: ({ context }) => context.repIndex + 1 < context.repsPerDrill,
    hasMoreDrills: ({ context }) => {
      const sign = context.signs[context.signIndex];
      if (!sign) return false;
      return context.drillIndex + 1 < sign.drills.length;
    },
    hasMoreSigns: ({ context }) => context.signIndex + 1 < context.signs.length,
  },
  actions: {
    advanceRep: assign(({ context }) => ({ repIndex: context.repIndex + 1 })),
    advanceDrill: assign(({ context }) => ({
      drillIndex: context.drillIndex + 1,
      repIndex: 0,
    })),
    advanceSign: assign(({ context }) => ({
      signIndex: context.signIndex + 1,
      drillIndex: 0,
      repIndex: 0,
    })),
    backDrill: assign(({ context }) => ({
      drillIndex: Math.max(0, context.drillIndex - 1),
      repIndex: 0,
    })),
    backSign: assign(({ context }) => ({
      signIndex: Math.max(0, context.signIndex - 1),
      drillIndex: 0,
      repIndex: 0,
    })),
    setOutcomePass: assign(() => ({ lastOutcome: 'pass' as const })),
    setOutcomeFail: assign(() => ({ lastOutcome: 'fail' as const })),
    setOutcomeSkip: assign(() => ({ lastOutcome: 'skip' as const })),
    clearOutcome: assign(() => ({ lastOutcome: null })),
  },
}).createMachine({
  id: 'practice',
  initial: 'IDLE',
  context: ({ input }) => {
    const repsPerDrill = input.repsPerDrill ?? 3;
    // Clamp restored cursors so an out-of-date save can't crash the machine.
    const signIndex = clampIdx(input.initialSignIndex, 0, input.signs.length - 1);
    const drillsInSign = input.signs[signIndex]?.drills.length ?? 1;
    const drillIndex = clampIdx(input.initialDrillIndex, 0, drillsInSign - 1);
    const repIndex = clampIdx(input.initialRepIndex, 0, repsPerDrill - 1);
    return {
      signs: input.signs,
      signIndex,
      drillIndex,
      repIndex,
      repsPerDrill,
      lastOutcome: null,
    };
  },
  states: {
    IDLE: {
      on: { START: 'READY' },
    },
    READY: {
      on: { PROMPT_READY: 'PROMPT_SHOWN' },
    },
    PROMPT_SHOWN: {
      on: { COUNTDOWN_DONE: 'COUNTDOWN' },
    },
    COUNTDOWN: {
      on: { REC_DONE: 'RECORDING' },
    },
    RECORDING: {
      on: { REC_DONE: 'SELF_REPORT' },
    },
    SELF_REPORT: {
      on: {
        PASS: { target: 'REP_PASS', actions: 'setOutcomePass' },
        FAIL: { target: 'REP_RETRY', actions: 'setOutcomeFail' },
        SKIP: { target: 'REP_PASS', actions: 'setOutcomeSkip' },
        SKIP_DRILL: { target: 'DRILL_COMPLETE', actions: 'setOutcomeSkip' },
      },
    },
    REP_PASS: {
      always: [
        // More reps in this drill? advance rep, go back to PROMPT_SHOWN
        {
          guard: 'hasMoreReps',
          target: 'PROMPT_SHOWN',
          actions: 'advanceRep',
        },
        // Otherwise the drill is done
        { target: 'DRILL_COMPLETE' },
      ],
    },
    REP_RETRY: {
      // Retry the same rep — go back to PROMPT_SHOWN without advancing rep counter
      on: {
        PROMPT_READY: 'PROMPT_SHOWN',
      },
      after: {
        // Auto-progress retry after 250ms so the state isn't a dead-end during dev
        250: 'PROMPT_SHOWN',
      },
    },
    DRILL_COMPLETE: {
      always: [
        {
          guard: 'hasMoreDrills',
          target: 'PROMPT_SHOWN',
          actions: 'advanceDrill',
        },
        { target: 'SIGN_COMPLETE' },
      ],
    },
    SIGN_COMPLETE: {
      always: [
        {
          guard: 'hasMoreSigns',
          target: 'PROMPT_SHOWN',
          actions: 'advanceSign',
        },
        { target: 'LESSON_COMPLETE' },
      ],
    },
    LESSON_COMPLETE: {
      type: 'final',
      on: { RESET: 'IDLE' },
    },
  },
  on: {
    RESET: { target: '.IDLE', actions: 'clearOutcome' },
    // Back navigation works from anywhere except IDLE/LESSON_COMPLETE.
    // Lands the user at PROMPT_SHOWN of the previous drill (or previous sign).
    BACK_DRILL: { target: '.PROMPT_SHOWN', actions: 'backDrill' },
    BACK_SIGN: { target: '.PROMPT_SHOWN', actions: 'backSign' },
  },
});

function clampIdx(v: number | undefined, lo: number, hi: number): number {
  if (typeof v !== 'number' || !Number.isFinite(v)) return lo;
  return Math.max(lo, Math.min(hi, Math.trunc(v)));
}

// === Selectors ===

export function selectCurrentSign(ctx: PracticeContext): PracticeSign | null {
  return ctx.signs[ctx.signIndex] ?? null;
}

export function selectCurrentDrill(
  ctx: PracticeContext
): { drillType: DrillType; target: string } | null {
  const sign = selectCurrentSign(ctx);
  if (!sign) return null;
  return sign.drills[ctx.drillIndex] ?? null;
}
