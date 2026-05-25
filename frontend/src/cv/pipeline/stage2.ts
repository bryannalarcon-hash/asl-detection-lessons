// Net 4 (sign classifier) forward + softmax + top-k, ported from
// `src/stage2/predict_clip.py` (the `predict` function's classify path). The
// ORT session is injected so this module never imports onnxruntime-web — it
// stays unit-testable against a mock and matches the Python contract:
//   logits = net4(features, key_padding_mask=mask); probs = softmax(logits[0]).
//
// IO names/shapes come from workstream A's `models.ts` export contract:
//   input  features: float32 (B, T, C)
//   input  mask:     bool    (B, T)   true = padded
//   output logits:   float32 (B, num_classes)

import {
  DEFAULT_FEATURE_OPTS,
  FeatureOpts,
  buildPerFrameFeatures,
  windowToModelInput,
} from './features';

/**
 * Minimal Net 4 session seam. The real ORT session (workstream A/D) adapts
 * onnxruntime-web's `InferenceSession.run` to this shape; tests inject a stub.
 * `mask` uses Uint8Array (1 = padded) — the adapter converts to the bool tensor
 * the ONNX graph expects.
 */
export interface Net4Session {
  /**
   * @param features flat (T*C) row-major feature buffer
   * @param mask     length-T key-padding mask (1 = padded)
   * @param T        number of time steps
   * @param C        feature dim per step
   * @returns flat logits, length = numClasses
   */
  run(features: Float32Array, mask: Uint8Array, T: number, C: number): Promise<Float32Array>;
}

/** Net 4 data config embedded in the checkpoint (see `load_net4`). */
export interface Net4DataConfig extends FeatureOpts {
  maxFrames: number;
}

export const DEFAULT_NET4_DATA_CONFIG: Net4DataConfig = {
  ...DEFAULT_FEATURE_OPTS,
  maxFrames: 64,
};

export interface TopKEntry {
  rank: number;
  gloss: string;
  prob: number;
}

export interface ClassifyResult {
  probs: Float32Array;
  topk: TopKEntry[];
  nFramesExtracted: number;
}

/** Numerically stable softmax over a flat logits vector. */
export function softmax(logits: Float32Array | number[]): Float32Array {
  const n = logits.length;
  const out = new Float32Array(n);
  let max = -Infinity;
  for (let i = 0; i < n; i++) if (logits[i] > max) max = logits[i];
  let sum = 0;
  for (let i = 0; i < n; i++) {
    const e = Math.exp(logits[i] - max);
    out[i] = e;
    sum += e;
  }
  const inv = sum > 0 ? 1 / sum : 0;
  for (let i = 0; i < n; i++) out[i] *= inv;
  return out;
}

/**
 * Top-k indices by descending probability. Mirrors `np.argsort(-probs)[:topk]`:
 * numpy's default argsort is a stable ascending sort, so the descending order
 * of `-probs` breaks ties by ascending index. We replicate that tie-break.
 */
export function topKIndices(probs: Float32Array, k: number): number[] {
  const idx = Array.from({ length: probs.length }, (_, i) => i);
  idx.sort((a, b) => {
    const d = probs[b] - probs[a];
    if (d !== 0) return d;
    return a - b; // stable tie-break: lower index first
  });
  return idx.slice(0, Math.min(k, probs.length));
}

/**
 * A `classify(window) -> probs` callable for the verifier, bound to a Net 4
 * session + gloss mapping. The window is a (T, C) flat buffer; this pads it to
 * the model length, runs the net, and returns the full softmax vector. Async
 * because ORT inference is async; the verifier port awaits it.
 */
export function makeClassify(
  session: Net4Session,
  cfg: Net4DataConfig = DEFAULT_NET4_DATA_CONFIG,
): (feat: Float32Array, T: number, C: number) => Promise<Float32Array> {
  return async (feat, T, C) => {
    const { feat: fixed, mask } = windowToModelInput(feat, T, C, cfg.maxFrames);
    const logits = await session.run(fixed, mask, cfg.maxFrames, C);
    return softmax(logits);
  };
}

/**
 * Full clip classification: keypoint buffer -> features -> Net 4 -> top-k.
 * Mirrors `predict_clip.predict`'s feature+classify tail.
 *
 * @param kpts  flat (T*49*2) keypoints (from workstream B)
 * @param vis   flat (T*49) visibility
 * @param T     frame count
 * @param idxToGloss class-index -> gloss list (from net4 gloss_to_idx)
 */
export async function classifyClip(
  session: Net4Session,
  kpts: Float32Array,
  vis: Float32Array,
  T: number,
  W: number,
  H: number,
  idxToGloss: string[],
  cfg: Net4DataConfig = DEFAULT_NET4_DATA_CONFIG,
  topk = 3,
): Promise<ClassifyResult> {
  const { feat, C } = buildPerFrameFeatures(kpts, vis, T, W, H, cfg);
  const { feat: fixed, mask } = windowToModelInput(feat, T, C, cfg.maxFrames);
  const logits = await session.run(fixed, mask, cfg.maxFrames, C);
  const probs = softmax(logits);
  const top = topKIndices(probs, topk);
  return {
    probs,
    nFramesExtracted: T,
    topk: top.map((j, i) => ({ rank: i + 1, gloss: idxToGloss[j], prob: probs[j] })),
  };
}

/** Invert a gloss->idx map into the idx-ordered gloss list. */
export function glossList(glossToIdx: Record<string, number>): string[] {
  const out: string[] = [];
  for (const [g, i] of Object.entries(glossToIdx)) out[i] = g;
  return out;
}
