// Rule-based attempt diagnosis (lib/hint-diagnosis.ts): a failed RepVerdict +
// optional per-sign hint copy resolves to exactly one targeted parameter, chosen
// by what the verdict says the learner did. Covers the four decision branches in
// priority order: framing -> handshape -> movement -> timing.
import { describe, it, expect } from 'vitest';
import { diagnoseAttempt } from '@/lib/hint-diagnosis';
import type { RepVerdict } from '@/cv/captureRep';
import type { SignHint } from '@/data/sign-hints';

// Minimal RepVerdict with plenty of hands frames and a near-miss top-3 by default;
// each test overrides only the fields its branch keys on.
function makeVerdict(over: Partial<RepVerdict> = {}): RepVerdict {
  return {
    pass: false,
    verifierPassed: false,
    isTop1: false,
    inTop3: true,
    top3: [{ gloss: 'MOM', prob: 0.4 }],
    targetConf: 0.4,
    cascadeMs: 0,
    classifyMs: 0,
    framesProcessed: 30,
    handsFrames: 30,
    net1Ms: 0,
    net2Ms: 0,
    net3Ms: 0,
    glueMs: 0,
    passFraction: 0,
    nWindows: 0,
    targetConfMean: 0,
    ...over,
  };
}

describe('diagnoseAttempt', () => {
  it('flags framing when the hands ratio is below 0.4', () => {
    // 11/30 = 0.367 < 0.4; framing dominates even though inTop3 is true.
    const v = makeVerdict({ handsFrames: 11, framesProcessed: 30, inTop3: true });
    const out = diagnoseAttempt(v, null);
    expect(out.parameter).toBe('framing');
  });

  it('flags handshape when the sign is not in the top 3, using hint copy when present', () => {
    const v = makeVerdict({ inTop3: false });
    const hint: SignHint = { default: 'd', handshape: 'spread all five fingers' };
    const out = diagnoseAttempt(v, hint);
    expect(out.parameter).toBe('handshape');
    expect(out.hint).toBe('spread all five fingers');
  });

  it('falls back to generic handshape copy when no hint is provided', () => {
    const out = diagnoseAttempt(makeVerdict({ inTop3: false }), null);
    expect(out.parameter).toBe('handshape');
    expect(out.hint).toBe('Check your handshape against the reference.');
  });

  it('flags movement when in top 3 but not top 1, using hint copy when present', () => {
    const v = makeVerdict({ inTop3: true, isTop1: false });
    const hint: SignHint = { default: 'd', movement: 'match the forward arc' };
    const out = diagnoseAttempt(v, hint);
    expect(out.parameter).toBe('movement');
    expect(out.hint).toBe('match the forward arc');
  });

  it('flags timing on a top-3 near-miss when in top 1', () => {
    // inTop3 && isTop1 but not a pass: only timing remains.
    const out = diagnoseAttempt(makeVerdict({ inTop3: true, isTop1: true }), null);
    expect(out.parameter).toBe('timing');
  });
});
