// Per-frame feature builder + window->model-input, ported with numerical
// parity from `src/stage2/data/sign_dataset.py` (`_normalise_frame`,
// `_build_per_frame_features`, `window_to_model_input`). The offline scorer
// (`predict_clip`) and the live demo both feed Net 4 through this one path, so
// any drift here desyncs the classifier from its training distribution.
//
// Input contract (from workstream B / `extract_keypoints.extract_one_clip`):
//   kpts: Float32Array length T*49*2, row-major frame-major: [t][kp][xy]
//   vis:  Float32Array length T*49,    [t][kp], 1 = present, 0 = missing
// produced per frame in image-pixel space, BEFORE normalisation.

// --- schema constants (mirror src/stage1/data/schema.py) ----------------- //
export const NUM_KEYPOINTS = 49;
const RIGHT_HAND_START = 0;
const LEFT_HAND_START = 21;
const NOSE = 42;
const CHIN = 43;
const FOREHEAD = 44;
const CHEST_CENTER = 45;
const LEFT_SHOULDER = 46;
const RIGHT_SHOULDER = 47;
const NECK = 48;
// FACE_INDICES + BODY_INDICES, in the Python concat order.
const FACE_BODY_INDICES = [NOSE, CHIN, FOREHEAD, CHEST_CENTER, LEFT_SHOULDER, RIGHT_SHOULDER, NECK];

export interface FeatureOpts {
  includeVisibility: boolean;
  includeLag1: boolean;
  includeLag2: boolean;
}

export const DEFAULT_FEATURE_OPTS: FeatureOpts = {
  includeVisibility: true,
  includeLag1: true,
  includeLag2: true,
};

/** Per-frame feature dim for the given flags. 343 with all enabled. */
export function featureDim(opts: FeatureOpts = DEFAULT_FEATURE_OPTS): number {
  let base = NUM_KEYPOINTS * 2; // coords (x, y)
  if (opts.includeVisibility) base += NUM_KEYPOINTS;
  if (opts.includeLag1) base += NUM_KEYPOINTS * 2;
  if (opts.includeLag2) base += NUM_KEYPOINTS * 2;
  return base;
}

/**
 * Per-part normalisation of one frame's (49, 2) keypoints.
 *
 * Faithful port of `_normalise_frame`: face/body keypoints anchored on their
 * centroid and divided by their bounding span (body-scale gross position); each
 * hand then re-normalised by its OWN span (wrist kept at its body-normalised
 * location, finger offsets divided by the hand span). Invisible keypoints are
 * zeroed so they contribute nothing through the lag deltas.
 *
 * @param kpts flat [49*2] (x, y) pixel coords for one frame
 * @param vis  flat [49] visibility for one frame
 * @param out  flat [49*2] destination (written in place)
 */
export function normaliseFrame(
  kpts: Float32Array | number[],
  vis: Float32Array | number[],
  W: number,
  H: number,
  out: Float32Array,
): void {
  // Centroid + span over visible face/body keypoints (fallback: all visible).
  let fbCount = 0;
  for (const i of FACE_BODY_INDICES) if (vis[i] > 0.5) fbCount++;

  // Gather the anchor point set (face/body if any visible, else all visible).
  let cx = 0;
  let cy = 0;
  let n = 0;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  const accumulate = (i: number) => {
    const x = kpts[i * 2];
    const y = kpts[i * 2 + 1];
    cx += x;
    cy += y;
    n++;
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
  };

  if (fbCount >= 1) {
    for (const i of FACE_BODY_INDICES) if (vis[i] > 0.5) accumulate(i);
  } else {
    for (let i = 0; i < NUM_KEYPOINTS; i++) if (vis[i] > 0.5) accumulate(i);
  }

  let centreX: number;
  let centreY: number;
  if (n >= 1) {
    centreX = cx / n;
    centreY = cy / n;
  } else {
    centreX = W * 0.5;
    centreY = H * 0.5;
  }

  let span: number;
  if (n >= 2) {
    const dx = maxX - minX;
    const dy = maxY - minY;
    span = Math.hypot(dx, dy);
  } else {
    span = Math.max(W, H) * 0.5;
  }
  if (span < 1e-3) span = Math.max(W, H) * 0.5;

  const denom = Math.max(span, 1.0);
  // out = (kpts - centre) / max(span, 1.0)
  for (let i = 0; i < NUM_KEYPOINTS; i++) {
    out[i * 2] = (kpts[i * 2] - centreX) / denom;
    out[i * 2 + 1] = (kpts[i * 2 + 1] - centreY) / denom;
  }

  // Per-hand scale recovery: keep wrist at its body-normalised location, divide
  // finger offsets by the hand's own span.
  for (const hStart of [RIGHT_HAND_START, LEFT_HAND_START]) {
    let hvis = 0;
    let hMinX = Infinity;
    let hMinY = Infinity;
    let hMaxX = -Infinity;
    let hMaxY = -Infinity;
    for (let j = 0; j < 21; j++) {
      const idx = hStart + j;
      if (vis[idx] > 0.5) {
        hvis++;
        const x = kpts[idx * 2];
        const y = kpts[idx * 2 + 1];
        if (x < hMinX) hMinX = x;
        if (y < hMinY) hMinY = y;
        if (x > hMaxX) hMaxX = x;
        if (y > hMaxY) hMaxY = y;
      }
    }
    if (hvis < 3) continue;
    const handSpan = Math.hypot(hMaxX - hMinX, hMaxY - hMinY);
    if (handSpan < 1e-3) continue;
    const wristX = kpts[hStart * 2]; // kp0 = wrist (frame coords)
    const wristY = kpts[hStart * 2 + 1];
    const bodyNormWristX = (wristX - centreX) / denom;
    const bodyNormWristY = (wristY - centreY) / denom;
    for (let j = 0; j < 21; j++) {
      const idx = hStart + j;
      out[idx * 2] = bodyNormWristX + (kpts[idx * 2] - wristX) / handSpan;
      out[idx * 2 + 1] = bodyNormWristY + (kpts[idx * 2 + 1] - wristY) / handSpan;
    }
  }

  // Zero-out invisibles (so they don't contribute through lag deltas).
  for (let i = 0; i < NUM_KEYPOINTS; i++) {
    if (!(vis[i] > 0.5)) {
      out[i * 2] = 0;
      out[i * 2 + 1] = 0;
    }
  }
}

/**
 * Build the (T, C) per-frame feature tensor (row-major, flat Float32Array).
 *
 * Faithful port of `_build_per_frame_features`. Part order matches the Python
 * concat exactly: coords(98) | vis(49) | lag1(98) | lag2(98). Lag deltas are
 * computed on the NORMALISED coords (after invisibles zeroed), with lag1[0]=0
 * and lag2[0]=lag2[1]=0.
 *
 * @returns { feat, T, C } flat feature buffer, T frames, C dims/frame.
 */
export function buildPerFrameFeatures(
  kpts: Float32Array,
  vis: Float32Array,
  T: number,
  W: number,
  H: number,
  opts: FeatureOpts = DEFAULT_FEATURE_OPTS,
): { feat: Float32Array; T: number; C: number } {
  const C = featureDim(opts);
  const feat = new Float32Array(T * C);

  // Normalised coords per frame: (T, 49, 2) flattened to (T, 98).
  const norm = new Float32Array(T * NUM_KEYPOINTS * 2);
  const frameBuf = new Float32Array(NUM_KEYPOINTS * 2);
  const visFrame = new Float32Array(NUM_KEYPOINTS);
  for (let t = 0; t < T; t++) {
    const kBase = t * NUM_KEYPOINTS * 2;
    const vBase = t * NUM_KEYPOINTS;
    const kFrame = kpts.subarray(kBase, kBase + NUM_KEYPOINTS * 2);
    for (let i = 0; i < NUM_KEYPOINTS; i++) visFrame[i] = vis[vBase + i];
    normaliseFrame(kFrame, visFrame, W, H, frameBuf);
    norm.set(frameBuf, kBase);
  }

  const coordsLen = NUM_KEYPOINTS * 2; // 98
  for (let t = 0; t < T; t++) {
    let off = t * C;
    const nBase = t * coordsLen;
    // coords (98)
    for (let i = 0; i < coordsLen; i++) feat[off + i] = norm[nBase + i];
    off += coordsLen;
    // vis (49)
    if (opts.includeVisibility) {
      const vBase = t * NUM_KEYPOINTS;
      for (let i = 0; i < NUM_KEYPOINTS; i++) feat[off + i] = vis[vBase + i];
      off += NUM_KEYPOINTS;
    }
    // lag1 (98) = norm[t] - norm[t-1], zero at t=0
    if (opts.includeLag1) {
      if (t >= 1) {
        const pBase = (t - 1) * coordsLen;
        for (let i = 0; i < coordsLen; i++) feat[off + i] = norm[nBase + i] - norm[pBase + i];
      }
      off += coordsLen;
    }
    // lag2 (98) = norm[t] - norm[t-2], zero at t=0,1
    if (opts.includeLag2) {
      if (t >= 2) {
        const pBase = (t - 2) * coordsLen;
        for (let i = 0; i < coordsLen; i++) feat[off + i] = norm[nBase + i] - norm[pBase + i];
      }
      off += coordsLen;
    }
  }

  return { feat, T, C };
}

/**
 * Pad/subsample a (T, C) feature window to `maxFrames`. Port of
 * `window_to_model_input` (eval-time policy, deterministic): when shorter than
 * maxFrames, zero-pad at the tail; when longer, uniformly subsample to
 * maxFrames frames via `linspace(0, T-1, maxFrames)` floored to int (numpy
 * `.astype(int)` truncates toward zero; indices here are non-negative so this
 * is `Math.floor`). Returns the fixed feature buffer and a key-padding mask
 * where `true` marks padded steps (the contract SignClassifier.forward wants).
 */
export function windowToModelInput(
  feat: Float32Array,
  T: number,
  C: number,
  maxFrames: number,
): { feat: Float32Array; mask: Uint8Array } {
  const out = new Float32Array(maxFrames * C);
  const mask = new Uint8Array(maxFrames);
  mask.fill(1); // true = padded
  let validT: number;
  if (T >= maxFrames) {
    // idxs = linspace(0, T-1, maxFrames).astype(int)
    for (let k = 0; k < maxFrames; k++) {
      const pos = linspaceIndex(0, T - 1, maxFrames, k);
      const src = Math.trunc(pos); // numpy astype(int) truncates toward zero
      out.set(feat.subarray(src * C, src * C + C), k * C);
    }
    validT = maxFrames;
  } else {
    out.set(feat.subarray(0, T * C), 0);
    validT = T;
  }
  for (let i = 0; i < validT; i++) mask[i] = 0; // false = valid
  return { feat: out, mask };
}

/**
 * The k-th value of numpy `linspace(start, stop, num)`. numpy uses
 * `start + step*k` with `step = (stop-start)/(num-1)` and forces the last
 * element to exactly `stop`, which we replicate to avoid float drift at the
 * endpoint (matters because the result is then truncated to an index).
 */
function linspaceIndex(start: number, stop: number, num: number, k: number): number {
  if (num === 1) return start;
  if (k === num - 1) return stop;
  const step = (stop - start) / (num - 1);
  return start + step * k;
}
