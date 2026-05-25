// SignVerifier vote/hysteresis parity. Mirrors the 9 cases in
// `tests/test_sign_verifier.py`: synthetic (49,2) keypoint frames + a mocked
// classify closure returning controlled prob vectors. The verifier exercises
// the REAL feature builder end-to-end (buildPerFrameFeatures), so window shape
// and feat_dim==343 are checked too. classify is async here (ORT contract);
// vote/hysteresis semantics are identical to the sync Python reference.
import { describe, it, expect } from 'vitest';
import { SignVerifier, ClassifyFn } from '../../src/cv/pipeline/verifier';

const GLOSS_TO_IDX: Record<string, number> = { DOG: 0, CAT: 1, MILK: 2, HELLO: 3 };
const NUM_CLASSES = 4;
const FEAT_DIM = 343;

/** One (49,2) frame, flat (98). Right hand 0..20 + body 45..48 populated. */
function makeFrame(t: number, moving: boolean): Float32Array {
  const k = new Float32Array(49 * 2);
  const drift = moving ? t * 6.0 : 0.0;
  for (let j = 0; j < 21; j++) {
    k[j * 2] = 300.0 + j * 3.0 + drift;
    k[j * 2 + 1] = 200.0 + j * 2.0;
  }
  const body = [45, 46, 47, 48];
  for (let bk = 0; bk < body.length; bk++) {
    k[body[bk] * 2] = 240.0 + 60.0 * bk;
    k[body[bk] * 2 + 1] = 150.0;
  }
  return k;
}

/** Controlled prob vector with a chosen target prob; rest spread to sum ~1. */
function probs(
  targetIdx: number | null,
  targetP: number,
  topOtherIdx?: number,
  topOtherP?: number,
): Float32Array {
  const p = new Float32Array(NUM_CLASSES);
  let fixed = 0;
  if (targetIdx !== null) {
    p[targetIdx] = targetP;
    fixed += targetP;
  }
  if (topOtherIdx !== undefined && topOtherP !== undefined) {
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

async function feed(
  v: SignVerifier,
  nFrames: number,
  opts: { moving: boolean; present: boolean },
): Promise<void> {
  for (let t = 0; t < nFrames; t++) {
    await v.pushFrame(makeFrame(t, opts.moving), opts.present);
  }
}

describe('SignVerifier vote/hysteresis parity', () => {
  it('happy path: target-dominant + moving present hand => verified', async () => {
    const classify: ClassifyFn = async () => probs(GLOSS_TO_IDX.DOG, 0.92);
    const v = new SignVerifier(classify, GLOSS_TO_IDX);
    await feed(v, 60, { moving: true, present: true });
    const r = v.verify('DOG');
    expect(r.verified).toBe(true);
    expect(r.passFraction).toBeGreaterThan(0.99);
    expect(r.nWindows).toBeGreaterThan(0);
    expect(r.gatedOut).toBe(0);
    expect(r.targetConfMean).toBeGreaterThan(0.9);
  });

  it('wrong sign: different class dominant => not verified', async () => {
    const classify: ClassifyFn = async () => probs(GLOSS_TO_IDX.CAT, 0.9);
    const v = new SignVerifier(classify, GLOSS_TO_IDX);
    await feed(v, 60, { moving: true, present: true });
    const r = v.verify('DOG');
    expect(r.verified).toBe(false);
    expect(r.targetConfMean).toBeLessThan(v.opts.confThresh);
    expect(r.passFraction).toBe(0.0);
  });

  it('no hand: present=false => every window gated out', async () => {
    const classify: ClassifyFn = async () => probs(GLOSS_TO_IDX.DOG, 0.99);
    const v = new SignVerifier(classify, GLOSS_TO_IDX);
    await feed(v, 60, { moving: true, present: false });
    const r = v.verify('DOG');
    expect(r.verified).toBe(false);
    expect(r.nWindows).toBeGreaterThan(0);
    expect(r.gatedOut).toBe(r.nWindows);
    expect(r.passFraction).toBe(0.0);
  });

  it('still hand: present but no motion => motion gate rejects', async () => {
    const classify: ClassifyFn = async () => probs(GLOSS_TO_IDX.DOG, 0.99);
    const v = new SignVerifier(classify, GLOSS_TO_IDX);
    await feed(v, 60, { moving: false, present: true });
    const r = v.verify('DOG');
    expect(r.verified).toBe(false);
    expect(r.gatedOut).toBeGreaterThan(0);
    expect(r.targetConfMean).toBe(0.0);
  });

  it('persistence: a transient high blip does not verify', async () => {
    let n = 0;
    const classify: ClassifyFn = async () => {
      n += 1;
      const p = n <= 2 ? 0.95 : 0.1;
      return probs(GLOSS_TO_IDX.DOG, p);
    };
    const v = new SignVerifier(classify, GLOSS_TO_IDX);
    await feed(v, 60, { moving: true, present: true });
    const r = v.verify('DOG');
    expect(r.verified).toBe(false);
    expect(r.passFraction).toBeLessThan(v.opts.voteFrac);
    expect(r.nWindows).toBeGreaterThanOrEqual(v.opts.minGatedWindows);
  });

  it('consistent runner-up still verifies (scores target, not top-1)', async () => {
    const classify: ClassifyFn = async () =>
      probs(GLOSS_TO_IDX.DOG, 0.4, GLOSS_TO_IDX.CAT, 0.5);
    const v = new SignVerifier(classify, GLOSS_TO_IDX, { confThresh: 0.35 });
    await feed(v, 60, { moving: true, present: true });
    const r = v.verify('DOG');
    const sample = await classify(new Float32Array(0), 0, 0);
    // CAT really is top-1 while DOG still clears conf_thresh.
    let argmax = 0;
    for (let i = 1; i < NUM_CLASSES; i++) if (sample[i] > sample[argmax]) argmax = i;
    expect(argmax).toBe(GLOSS_TO_IDX.CAT);
    expect(sample[GLOSS_TO_IDX.DOG]).toBeGreaterThanOrEqual(v.opts.confThresh);
    expect(sample[GLOSS_TO_IDX.DOG]).toBeLessThan(sample[GLOSS_TO_IDX.CAT]);
    expect(r.verified).toBe(true);
    expect(r.passFraction).toBeGreaterThan(0.99);
  });

  it('knob sanity: conf_thresh and vote_frac flip a borderline case', async () => {
    const classify: ClassifyFn = async () => probs(GLOSS_TO_IDX.DOG, 0.45);

    const strict = new SignVerifier(classify, GLOSS_TO_IDX); // confThresh 0.5
    await feed(strict, 60, { moving: true, present: true });
    expect(strict.verify('DOG').verified).toBe(false);

    const loose = new SignVerifier(classify, GLOSS_TO_IDX, { confThresh: 0.4 });
    await feed(loose, 60, { moving: true, present: true });
    expect(loose.verify('DOG').verified).toBe(true);

    // vote_frac: half windows pass at 0.55, half at 0.45.
    let n = 0;
    const alt: ClassifyFn = async () => {
      n += 1;
      return probs(GLOSS_TO_IDX.DOG, n % 2 === 0 ? 0.55 : 0.45);
    };
    const highVf = new SignVerifier(alt, GLOSS_TO_IDX, { voteFrac: 0.8 });
    await feed(highVf, 60, { moving: true, present: true });
    expect(highVf.verify('DOG').verified).toBe(false); // ~50% < 0.8

    n = 0;
    const lowVf = new SignVerifier(alt, GLOSS_TO_IDX, { voteFrac: 0.4, minGatedWindows: 2 });
    await feed(lowVf, 60, { moving: true, present: true });
    expect(lowVf.verify('DOG').verified).toBe(true); // ~50% >= 0.4
  });

  it('gloss index + window-shape contract', async () => {
    const seenShapes: Array<[number, number]> = [];
    const classify: ClassifyFn = async (_feat, T, C) => {
      seenShapes.push([T, C]);
      return probs(GLOSS_TO_IDX.MILK, 1.0); // one-hot on MILK
    };
    const v = new SignVerifier(classify, GLOSS_TO_IDX, { windowLen: 30 });
    await feed(v, 60, { moving: true, present: true });

    expect(seenShapes.length).toBeGreaterThan(0);
    for (const [t, c] of seenShapes) {
      expect(t).toBeLessThanOrEqual(v.opts.windowLen);
      expect(c).toBe(FEAT_DIM);
    }

    // Non-target indices first (avoids arming hysteresis from a MILK pass).
    expect(v.verify('DOG').verified).toBe(false);
    expect(v.verify('CAT').verified).toBe(false);
    expect(v.verify('MILK').verified).toBe(true);

    expect(() => v.verify('NOT_A_SIGN')).toThrow();
  });

  it('hysteresis holds after a pass within hold_sec', async () => {
    const state = { low: false };
    const classify: ClassifyFn = async () =>
      probs(GLOSS_TO_IDX.DOG, state.low ? 0.05 : 0.95);
    const v = new SignVerifier(classify, GLOSS_TO_IDX, { spanSec: 0.5, holdSec: 2.0 });
    await feed(v, 60, { moving: true, present: true });
    const r1 = v.verify('DOG'); // arms hysteresis (raw_pass true)
    expect(r1.verified).toBe(true);
    expect(v.holdFramesLeftValue).toBeGreaterThan(0);

    state.low = true;
    await feed(v, v.windowsPerSpan * v.opts.stride + 2, { moving: true, present: true });
    const r2 = v.verify('DOG');
    expect(r2.passFraction).toBeLessThan(v.opts.voteFrac); // raw pass fails now
    expect(v.holdFramesLeftValue).toBeGreaterThan(0); // still inside hold window
    expect(r2.verified).toBe(true); // hysteresis holds
  });
});
