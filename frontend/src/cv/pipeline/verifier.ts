// Live sign VERIFICATION for the lesson practice loop. Faithful TS port of
// `src/stage2/sign_verifier.py` (SignVerifier): sliding-window + persistence
// vote against ONE known target sign, gated by motion + hand presence, with
// hysteresis on the decision.
//
// The classifier is INJECTED as a callable so this module never imports ORT or
// Net 4 — it stays portable and unit-testable, exactly as the Python reference.
// Per-frame features are built with the SAME helper Net 4's dataset uses
// (`buildPerFrameFeatures`) so live features match training. That helper
// normalises coords (scale/translation invariant), so the motion gate is
// computed on the RAW pixel keypoints, which retain real velocity magnitude.

import {
  DEFAULT_FEATURE_OPTS,
  FeatureOpts,
  NUM_KEYPOINTS,
  buildPerFrameFeatures,
} from './features';

/** (window feat (T,C) flat) -> probs (numClasses). Async (ORT is async). */
export type ClassifyFn = (feat: Float32Array, T: number, C: number) => Promise<Float32Array>;

export interface VerifierOptions extends FeatureOpts {
  windowLen: number;
  stride: number;
  spanSec: number;
  fps: number;
  confThresh: number;
  voteFrac: number;
  motionMinSpeed: number;
  presenceMin: number;
  minGatedWindows: number;
  holdSec: number;
  frameW: number;
  frameH: number;
}

export const DEFAULT_VERIFIER_OPTIONS: VerifierOptions = {
  ...DEFAULT_FEATURE_OPTS,
  windowLen: 30,
  stride: 2,
  spanSec: 2.0,
  fps: 30,
  confThresh: 0.5,
  voteFrac: 0.8,
  motionMinSpeed: 1.5,
  presenceMin: 0.6,
  minGatedWindows: 2,
  holdSec: 0.75,
  frameW: 640,
  frameH: 480,
};

export interface VerifyResult {
  verified: boolean;
  targetConfMean: number;
  passFraction: number;
  nWindows: number;
  gatedOut: number;
}

/** Fixed-capacity ring buffer mirroring Python's `deque(maxlen=n)`. */
class RingBuffer<T> {
  private items: T[] = [];
  constructor(private readonly maxlen: number) {}
  push(x: T): void {
    this.items.push(x);
    if (this.items.length > this.maxlen) this.items.shift();
  }
  clear(): void {
    this.items = [];
  }
  get length(): number {
    return this.items.length;
  }
  /** Last `n` items as a plain array (matches `list(deque)[-n:]`). */
  tail(n: number): T[] {
    return this.items.slice(Math.max(0, this.items.length - n));
  }
  toArray(): T[] {
    return this.items.slice();
  }
}

export class SignVerifier {
  private readonly classify: ClassifyFn;
  private readonly glossToIdx: Record<string, number>;
  readonly opts: VerifierOptions;
  readonly windowsPerSpan: number;
  private readonly holdFrames: number;

  private readonly kptsBuf: RingBuffer<Float32Array>; // each (49*2)
  private readonly visBuf: RingBuffer<Float32Array>; // each (49)
  private readonly presentBuf: RingBuffer<boolean>;
  private readonly gatePass: RingBuffer<boolean>;
  private readonly probsBuf: RingBuffer<Float32Array | null>;

  private frameCount = 0;
  private holdFramesLeft = 0;

  constructor(
    classify: ClassifyFn,
    glossToIdx: Record<string, number>,
    options: Partial<VerifierOptions> = {},
  ) {
    const opts = { ...DEFAULT_VERIFIER_OPTIONS, ...options };
    if (opts.windowLen < 2) throw new Error('windowLen must be >= 2');
    if (opts.stride < 1) throw new Error('stride must be >= 1');
    this.classify = classify;
    this.glossToIdx = { ...glossToIdx };
    this.opts = opts;

    // How many classifier windows fall inside the persistence span.
    this.windowsPerSpan = Math.max(
      1,
      Math.round((opts.spanSec * opts.fps) / opts.stride),
    );

    // Rolling raw buffers, +2 for lag2 deltas at the window head.
    const buf = opts.windowLen + 2;
    this.kptsBuf = new RingBuffer(buf);
    this.visBuf = new RingBuffer(buf);
    this.presentBuf = new RingBuffer(buf);
    this.gatePass = new RingBuffer(this.windowsPerSpan);
    this.probsBuf = new RingBuffer(this.windowsPerSpan);

    this.holdFrames = Math.max(1, Math.round(opts.holdSec * opts.fps));
  }

  /** Clear all buffers and votes (call when the target sign changes). */
  reset(): void {
    this.kptsBuf.clear();
    this.visBuf.clear();
    this.presentBuf.clear();
    this.gatePass.clear();
    this.probsBuf.clear();
    this.frameCount = 0;
    this.holdFramesLeft = 0;
  }

  /**
   * Append one frame of keypoints; classify every `stride` frames.
   *
   * @param keypoints flat (49*2) pixel coords in the source frame's space
   * @param present   true if a hand was detected this frame
   *
   * Visibility is derived from the keypoints (NaN/zero row => not visible) so
   * callers only pass coords + a presence flag. Async because the injected
   * classifier (ORT) is async; the Python reference is sync but the
   * vote/hysteresis semantics are identical.
   */
  async pushFrame(keypoints: Float32Array | number[], present: boolean): Promise<void> {
    const kpts = new Float32Array(NUM_KEYPOINTS * 2);
    // Copy + NaN-scrub (np.nan_to_num) so NaNs never poison the feature math.
    for (let i = 0; i < NUM_KEYPOINTS * 2; i++) {
      const v = keypoints[i];
      kpts[i] = Number.isFinite(v) ? v : 0;
    }
    const vis = this.deriveVisibility(keypoints, present);

    this.kptsBuf.push(kpts);
    this.visBuf.push(vis);
    this.presentBuf.push(present);
    this.frameCount += 1;
    if (this.holdFramesLeft > 0) this.holdFramesLeft -= 1;

    if (
      this.kptsBuf.length >= this.opts.windowLen &&
      this.frameCount % this.opts.stride === 0
    ) {
      await this.evaluateWindow();
    }
  }

  /** Visibility from raw coords: finite AND non-zero, masked by presence. */
  private deriveVisibility(kpts: Float32Array | number[], present: boolean): Float32Array {
    const vis = new Float32Array(NUM_KEYPOINTS);
    if (!present) return vis; // all zeros
    for (let i = 0; i < NUM_KEYPOINTS; i++) {
      const x = kpts[i * 2];
      const y = kpts[i * 2 + 1];
      const finite = Number.isFinite(x) && Number.isFinite(y);
      const nonzero = Math.abs(x) > 1e-6 || Math.abs(y) > 1e-6;
      vis[i] = finite && nonzero ? 1 : 0;
    }
    return vis;
  }

  /** Build the trailing window, gate it, classify, record the vote. */
  private async evaluateWindow(): Promise<void> {
    const wl = this.opts.windowLen;
    const kptsFrames = this.kptsBuf.tail(wl); // each (49*2)
    const visFrames = this.visBuf.tail(wl); // each (49)
    const present = this.presentBuf.tail(wl);

    const gatePass = this.motionPresenceGate(kptsFrames, visFrames, present);

    let probs: Float32Array | null = null;
    if (gatePass) {
      // Flatten the window into the (T*49*2) / (T*49) layout the feature
      // builder expects, then build features the same way training does.
      const T = wl;
      const kFlat = new Float32Array(T * NUM_KEYPOINTS * 2);
      const vFlat = new Float32Array(T * NUM_KEYPOINTS);
      for (let t = 0; t < T; t++) {
        kFlat.set(kptsFrames[t], t * NUM_KEYPOINTS * 2);
        vFlat.set(visFrames[t], t * NUM_KEYPOINTS);
      }
      const { feat, C } = buildPerFrameFeatures(
        kFlat,
        vFlat,
        T,
        this.opts.frameW,
        this.opts.frameH,
        this.opts,
      );
      probs = await this.classify(feat, T, C);
    }

    this.gatePass.push(gatePass);
    this.probsBuf.push(probs);
  }

  /**
   * True if the window shows enough motion AND hand presence. Motion = mean
   * per-frame keypoint velocity over keypoints visible in both adjacent frames,
   * measured on RAW pixel coords; presence = fraction of frames with a hand.
   */
  private motionPresenceGate(
    kptsFrames: Float32Array[],
    visFrames: Float32Array[],
    present: boolean[],
  ): boolean {
    const presenceFrac = present.length
      ? present.reduce((s, p) => s + (p ? 1 : 0), 0) / present.length
      : 0;
    if (presenceFrac < this.opts.presenceMin) return false;

    const speeds: number[] = [];
    for (let t = 1; t < kptsFrames.length; t++) {
      const v = visFrames[t];
      const vPrev = visFrames[t - 1];
      const cur = kptsFrames[t];
      const prev = kptsFrames[t - 1];
      let sum = 0;
      let count = 0;
      for (let i = 0; i < NUM_KEYPOINTS; i++) {
        if (v[i] > 0.5 && vPrev[i] > 0.5) {
          const dx = cur[i * 2] - prev[i * 2];
          const dy = cur[i * 2 + 1] - prev[i * 2 + 1];
          sum += Math.hypot(dx, dy);
          count++;
        }
      }
      if (count === 0) continue; // no keypoint visible in both frames
      speeds.push(sum / count);
    }
    const meanSpeed = speeds.length
      ? speeds.reduce((s, x) => s + x, 0) / speeds.length
      : 0;
    return meanSpeed >= this.opts.motionMinSpeed;
  }

  /**
   * Decide whether the user is producing `targetGloss` right now. Uses the
   * TARGET-class prob (not top-1) over gated windows so a consistent close #2
   * still verifies. Hysteresis holds the decision for `holdFrames` after a
   * raw pass.
   */
  verify(targetGloss: string): VerifyResult {
    if (!(targetGloss in this.glossToIdx)) {
      throw new Error(`unknown target gloss: ${JSON.stringify(targetGloss)}`);
    }
    const tidx = this.glossToIdx[targetGloss];

    const gate = this.gatePass.toArray();
    const nWindows = gate.length;
    const gatedOut = gate.reduce((s, g) => s + (g ? 0 : 1), 0);

    const confs: number[] = [];
    for (const p of this.probsBuf.toArray()) {
      if (p !== null) confs.push(p[tidx]);
    }
    const nGated = confs.length;

    let targetConfMean = 0;
    let passFraction = 0;
    let rawPass = false;
    if (nGated > 0) {
      targetConfMean = confs.reduce((s, c) => s + c, 0) / nGated;
      const nPass = confs.reduce((s, c) => s + (c >= this.opts.confThresh ? 1 : 0), 0);
      passFraction = nPass / nGated;
      rawPass = passFraction >= this.opts.voteFrac && nGated >= this.opts.minGatedWindows;
    }

    if (rawPass) this.holdFramesLeft = this.holdFrames;
    const verified = rawPass || this.holdFramesLeft > 0;

    return {
      verified,
      targetConfMean,
      passFraction,
      nWindows,
      gatedOut,
    };
  }

  /** Exposed for tests/diagnostics (mirrors the Python attribute). */
  get holdFramesLeftValue(): number {
    return this.holdFramesLeft;
  }
}
