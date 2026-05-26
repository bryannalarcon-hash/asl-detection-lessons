// Rule-based attempt diagnosis: turn a failed RepVerdict into a single targeted
// hint, leaning on the per-parameter copy in data/sign-hints.ts when present and
// a generic fallback otherwise. The aim is one observable thing to fix next,
// chosen by what the verdict says the learner actually did.

import type { RepVerdict } from '@/cv/captureRep';
import type { HintParameter, SignHint } from '@/data/sign-hints';

export interface DiagnosedHint {
  parameter: HintParameter;
  hint: string;
}

// Below this share of frames with a detected hand the clip is mostly empty —
// the learner likely fell out of frame, so framing dominates everything else.
const MIN_HANDS_FRACTION = 0.4;

export function diagnoseAttempt(
  verdict: RepVerdict,
  hint: SignHint | null
): DiagnosedHint {
  const handsFraction = verdict.handsFrames / Math.max(1, verdict.framesProcessed);

  if (handsFraction < MIN_HANDS_FRACTION) {
    return {
      parameter: 'framing',
      hint: 'Keep both hands in view for the whole sign — center yourself so nothing leaves the frame.',
    };
  }

  if (!verdict.inTop3) {
    return {
      parameter: 'handshape',
      hint: hint?.handshape ?? 'Check your handshape against the reference.',
    };
  }

  if (!verdict.isTop1) {
    return {
      parameter: 'movement',
      hint: hint?.movement ?? 'Close — match the movement and timing more closely.',
    };
  }

  return {
    parameter: 'timing',
    hint: 'Almost there — hold the sign a moment longer and match the reference pacing.',
  };
}
