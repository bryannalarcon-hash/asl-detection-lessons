// V — verifier parity: mirror tests/test_sign_verifier.py's 9 cases against the
// TS SignVerifier port (vote / hysteresis / motion+presence gate). The Python
// classifier is sync; the TS one is async (injected ClassifyFn) but the
// vote/hysteresis/gate semantics are identical, so the verdicts must match.
//
// Synthetic keypoint frames are built EXACTLY as _make_frame in the Python test
// (right hand idx 0..20 + body anchors 45..48; ~6px/frame drift when moving).

import { describe, expect, it } from 'vitest';
import { SignVerifier, type ClassifyFn } from '../../src/cv/pipeline/verifier';
import { NUM_KEYPOINTS } from '../../src/cv/pipeline/features';

const GLOSS_TO_IDX: Record<string, number> = { DOG: 0, CAT: 1, MILK: 2, HELLO: 3 };
const NUM_CLASSES = Object.keys(GLOSS_TO_IDX).length;

// Port of _make_frame: returns a flat (49*2) Float32Array.
function makeFrame(t: number, moving: boolean): Float32Array {
  const k = new Float32Array(NUM_KEYPOINTS * 2);
  const drift = moving ? t * 6.0 : 0.0;
  for (let j = 0; j < 21; j++) {
    k[j * 2] = 300.0 + j * 3.0 + drift;
    k[j * 2 + 1] = 200.0 + j * 2.0;
  }
  const body = [45, 46, 47, 48];
  for (let kk = 0; kk < body.length; kk++) {
    const bi = body[kk];
    k[bi * 2] = 240.0 + 60.0 * kk;
    k[bi * 2 + 1] = 150.0;
  }
  return k;
}

// Port of _probs: length-NUM_CLASSES vector with controlled target prob,
// remaining mass spread over untouched classes.
function probs(
  targetIdx: number | null,
  targetP: number,
  topOtherIdx: number | null = null,
  topOtherP: number | null = null,
): Float32Array {
  const p = new Float32Array(NUM_CLASSES);
  let fixed = 0;
  if (targetIdx !== null) {
    p[targetIdx] = targetP;
    fixed += targetP;
  }
  if (topOtherIdx !== null && topOtherP !== null) {
    p[topOtherIdx] = topOtherP;
    fixed += topOtherP;
  }
  const free: number[] = [];
  for (let i = 0; i < NUM_CLASSES; i++) {
    if (p[i] === 0 && i !== targetIdx && i !== topOtherIdx) free.push(i);
  }
  if (free.length) {
    const rest = Math.max(0, 1 - fixed);
    for (const i of free) p[i] = rest / free.length;
  }
  return p;
}

async function feed(v: SignVerifier, n: number, moving: boolean, present: boolean): Promise<void> {
  for (let t = 0; t < n; t++) {
    await v.pushFrame(makeFrame(t, moving), present);
  }
}

// The TS SignVerifier reads frameW/frameH from opts (Python uses W/H=640/480
// defaults inside _build_per_frame_features via the dataset path). The motion
// gate runs on raw px so frame size doesn't affect the gate; the classifier is
// mocked so feature values don't matter to the verdict.

describe('V verifier parity (TS port vs tests/test_sign_verifier.py) [9 cases]', () => {
  it('test_happy_path_verified', async () => {
    const classify: ClassifyFn = async () => probs(GLOSS_TO_IDX.DOG, 0.92);
    const v = new SignVerifier(classify, GLOSS_TO_IDX);
    await feed(v, 60, true, true);
    const r = v.verify('DOG');
    expect(r.verified).toBe(true);
    expect(r.passFraction).toBeGreaterThan(0.99);
    expect(r.nWindows).toBeGreaterThan(0);
    expect(r.gatedOut).toBe(0);
    expect(r.targetConfMean).toBeGreaterThan(0.9);
  });

  it('test_wrong_sign_not_verified', async () => {
    const classify: ClassifyFn = async () => probs(GLOSS_TO_IDX.CAT, 0.9);
    const v = new SignVerifier(classify, GLOSS_TO_IDX);
    await feed(v, 60, true, true);
    const r = v.verify('DOG');
    expect(r.verified).toBe(false);
    expect(r.targetConfMean).toBeLessThan(v.opts.confThresh);
    expect(r.passFraction).toBe(0.0);
  });

  it('test_no_hand_all_gated_out', async () => {
    const classify: ClassifyFn = async () => probs(GLOSS_TO_IDX.DOG, 0.99);
    const v = new SignVerifier(classify, GLOSS_TO_IDX);
    await feed(v, 60, true, false);
    const r = v.verify('DOG');
    expect(r.verified).toBe(false);
    expect(r.nWindows).toBeGreaterThan(0);
    expect(r.gatedOut).toBe(r.nWindows);
    expect(r.passFraction).toBe(0.0);
  });

  it('test_still_hand_motion_gate', async () => {
    const classify: ClassifyFn = async () => probs(GLOSS_TO_IDX.DOG, 0.99);
    const v = new SignVerifier(classify, GLOSS_TO_IDX);
    await feed(v, 60, false, true);
    const r = v.verify('DOG');
    expect(r.verified).toBe(false);
    expect(r.gatedOut).toBeGreaterThan(0);
    expect(r.targetConfMean).toBe(0.0);
  });

  it('test_persistence_transient_does_not_trigger', async () => {
    let n = 0;
    const classify: ClassifyFn = async () => {
      n += 1;
      const p = n <= 2 ? 0.95 : 0.1;
      return probs(GLOSS_TO_IDX.DOG, p);
    };
    const v = new SignVerifier(classify, GLOSS_TO_IDX);
    await feed(v, 60, true, true);
    const r = v.verify('DOG');
    expect(r.verified).toBe(false);
    expect(r.passFraction).toBeLessThan(v.opts.voteFrac);
    expect(r.nWindows).toBeGreaterThanOrEqual(v.opts.minGatedWindows);
  });

  it('test_target_consistent_runner_up_still_verifies', async () => {
    const classify: ClassifyFn = async () =>
      probs(GLOSS_TO_IDX.DOG, 0.4, GLOSS_TO_IDX.CAT, 0.5);
    const v = new SignVerifier(classify, GLOSS_TO_IDX, { confThresh: 0.35 });
    await feed(v, 60, true, true);
    const r = v.verify('DOG');
    expect(r.verified).toBe(true);
    expect(r.passFraction).toBeGreaterThan(0.99);
  });

  it('test_knob_sanity_thresholds_flip_borderline', async () => {
    const classify: ClassifyFn = async () => probs(GLOSS_TO_IDX.DOG, 0.45);
    const strict = new SignVerifier(classify, GLOSS_TO_IDX); // confThresh 0.5
    await feed(strict, 60, true, true);
    expect(strict.verify('DOG').verified).toBe(false);

    const loose = new SignVerifier(classify, GLOSS_TO_IDX, { confThresh: 0.4 });
    await feed(loose, 60, true, true);
    expect(loose.verify('DOG').verified).toBe(true);

    // vote_frac knob: half windows pass at 0.55, half at 0.45.
    let n1 = 0;
    const alt1: ClassifyFn = async () => {
      n1 += 1;
      return probs(GLOSS_TO_IDX.DOG, n1 % 2 === 0 ? 0.55 : 0.45);
    };
    const highVf = new SignVerifier(alt1, GLOSS_TO_IDX, { voteFrac: 0.8 });
    await feed(highVf, 60, true, true);
    expect(highVf.verify('DOG').verified).toBe(false);

    let n2 = 0;
    const alt2: ClassifyFn = async () => {
      n2 += 1;
      return probs(GLOSS_TO_IDX.DOG, n2 % 2 === 0 ? 0.55 : 0.45);
    };
    const lowVf = new SignVerifier(alt2, GLOSS_TO_IDX, { voteFrac: 0.4, minGatedWindows: 2 });
    await feed(lowVf, 60, true, true);
    expect(lowVf.verify('DOG').verified).toBe(true);
  });

  it('test_gloss_index_and_window_shape_contract', async () => {
    const seenShapes: [number, number][] = [];
    const classify: ClassifyFn = async (_feat, T, C) => {
      seenShapes.push([T, C]);
      return probs(GLOSS_TO_IDX.MILK, 1.0);
    };
    const v = new SignVerifier(classify, GLOSS_TO_IDX, { windowLen: 30 });
    await feed(v, 60, true, true);

    expect(seenShapes.length).toBeGreaterThan(0);
    for (const [t, c] of seenShapes) {
      expect(t).toBeLessThanOrEqual(v.opts.windowLen); // T <= window_len
      expect(c).toBe(343); // feat_dim == 343
    }
    // Non-target indices first (avoid arming hysteresis), then the real target.
    expect(v.verify('DOG').verified).toBe(false);
    expect(v.verify('CAT').verified).toBe(false);
    expect(v.verify('MILK').verified).toBe(true);
    // Unknown gloss raises.
    expect(() => v.verify('NOT_A_SIGN')).toThrow();
  });

  it('test_hysteresis_holds_after_pass', async () => {
    const state = { low: false };
    const classify: ClassifyFn = async () =>
      probs(GLOSS_TO_IDX.DOG, state.low ? 0.05 : 0.95);
    const v = new SignVerifier(classify, GLOSS_TO_IDX, { spanSec: 0.5, holdSec: 2.0 });
    await feed(v, 60, true, true);
    const r1 = v.verify('DOG'); // arms hysteresis
    expect(r1.verified).toBe(true);
    expect(v.holdFramesLeftValue).toBeGreaterThan(0);

    state.low = true;
    await feed(v, v.windowsPerSpan * v.opts.stride + 2, true, true);
    const r2 = v.verify('DOG');
    expect(r2.passFraction).toBeLessThan(v.opts.voteFrac); // raw pass fails now
    expect(v.holdFramesLeftValue).toBeGreaterThan(0); // still inside hold
    expect(r2.verified).toBe(true); // hysteresis holds
  });
});
