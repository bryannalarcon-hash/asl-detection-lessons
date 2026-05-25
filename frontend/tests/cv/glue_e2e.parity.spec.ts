// Glue parity + E2E parity against the Python predict_clip reference.
//
// Glue (catches the easy-to-break feature math): feed the fixture's per-frame
// 49-kpt sequence through the TS feature builder + window pad/subsample and
// assert the (T,343) feature tensor + the (64,343) windowed tensor + the
// padding mask match the Python reference within tol.
//
// E2E (gates the merge): feed the windowed features through the real net4.onnx
// (ORT) -> softmax -> top-3, and assert the top-3 gloss ORDER + probs match
// predict_clip's output for the same clip.

import { describe, expect, it } from 'vitest';
import {
  buildPerFrameFeatures,
  windowToModelInput,
  type FeatureOpts,
} from '../../src/cv/pipeline/features';
import { softmax, topKIndices, glossList } from '../../src/cv/pipeline/stage2';
import { f32, getSession, loadFixture, maxAbsDiff, worstElement } from './_harness';
import * as ort from 'onnxruntime-node';

const FEAT_TOL = 1e-3;
const PROB_TOL = 1e-3;

interface PipelineFixture {
  clip: string;
  width: number;
  height: number;
  n_frames: number;
  keypoints: { shape: number[]; data: number[] };
  visibility: { shape: number[]; data: number[] };
  features: { shape: number[]; data: number[] };
  features_windowed: { shape: number[]; data: number[] };
  key_padding_mask: { shape: number[]; data: number[] };
  topk: { rank: number; gloss: string; prob: number }[];
  data_cfg: {
    max_frames: number;
    include_visibility: boolean;
    include_lag1: boolean;
    include_lag2: boolean;
  };
}

function optsFromCfg(cfg: PipelineFixture['data_cfg']): FeatureOpts {
  return {
    includeVisibility: cfg.include_visibility,
    includeLag1: cfg.include_lag1,
    includeLag2: cfg.include_lag2,
  };
}

// Run net4.onnx directly (float32 features + float32 mask, per the real export).
async function runNet4(feat: Float32Array, mask: Uint8Array, T: number, C: number): Promise<Float32Array> {
  const session = await getSession('net4.onnx');
  const maskF = Float32Array.from(mask, (v) => (v ? 1 : 0));
  const feeds = {
    features: new ort.Tensor('float32', feat, [1, T, C]),
    key_padding_mask: new ort.Tensor('float32', maskF, [1, T]),
  };
  const out = await session.run(feeds);
  return out.logits.data as Float32Array;
}

describe.each(['mom', 'red'])('clip %s', (tag) => {
  const fx = loadFixture<PipelineFixture>(`pipeline_${tag}.json`);
  const T = fx.n_frames;
  const W = fx.width;
  const H = fx.height;
  const opts = optsFromCfg(fx.data_cfg);
  const kpts = f32(fx.keypoints); // (T*49*2)
  const vis = f32(fx.visibility); // (T*49)

  it('glue: per-frame features (T,343) match Python _build_per_frame_features', () => {
    const { feat, C } = buildPerFrameFeatures(kpts, vis, T, W, H, opts);
    const ref = f32(fx.features);
    expect(C).toBe(fx.features.shape[1]);
    expect(feat.length).toBe(ref.length);
    const diff = maxAbsDiff(feat, ref);
    console.log(`[${tag}] features (T=${T},C=${C}) maxAbsDiff = ${diff.toExponential(3)}`);
    if (diff > FEAT_TOL) console.log('  worst:', worstElement(feat, ref));
    expect(diff).toBeLessThan(FEAT_TOL);
  });

  it('glue: windowed features (64,343) + mask match window_to_model_input', () => {
    const { feat, C } = buildPerFrameFeatures(kpts, vis, T, W, H, opts);
    const { feat: win, mask } = windowToModelInput(feat, T, C, fx.data_cfg.max_frames);
    const refWin = f32(fx.features_windowed);
    const refMask = fx.key_padding_mask.data; // 1.0 = padded
    const dWin = maxAbsDiff(win, refWin);
    // mask parity: TS uses 1 = padded (Uint8); Python stores 1.0 = padded.
    let maskMismatch = 0;
    for (let i = 0; i < mask.length; i++) if ((mask[i] ? 1 : 0) !== (refMask[i] > 0.5 ? 1 : 0)) maskMismatch++;
    console.log(`[${tag}] windowed maxAbsDiff = ${dWin.toExponential(3)}  mask mismatches = ${maskMismatch}`);
    if (dWin > FEAT_TOL) console.log('  worst:', worstElement(win, refWin));
    expect(dWin).toBeLessThan(FEAT_TOL);
    expect(maskMismatch).toBe(0);
  });

  it('e2e: TS pipeline top-3 glosses (order) + probs match predict_clip', async () => {
    const { feat, C } = buildPerFrameFeatures(kpts, vis, T, W, H, opts);
    const { feat: win, mask } = windowToModelInput(feat, T, C, fx.data_cfg.max_frames);
    const logits = await runNet4(win, mask, fx.data_cfg.max_frames, C);
    const probs = softmax(logits);

    const glossToIdx = loadFixture<any>('gloss_to_idx.json').gloss_to_idx as Record<string, number>;
    const idxToGloss = glossList(glossToIdx);
    const top = topKIndices(probs, 3);
    const tsTop = top.map((j, i) => ({ rank: i + 1, gloss: idxToGloss[j], prob: probs[j] }));

    const refTop = fx.topk;
    console.log(`[${tag}] TS  top3:`, tsTop.map((e) => `${e.gloss}=${e.prob.toFixed(4)}`).join(', '));
    console.log(`[${tag}] ref top3:`, refTop.map((e) => `${e.gloss}=${e.prob.toFixed(4)}`).join(', '));

    // ORDER must match.
    expect(tsTop.map((e) => e.gloss)).toEqual(refTop.map((e) => e.gloss));
    // Probs within tol.
    for (let i = 0; i < 3; i++) {
      const d = Math.abs(tsTop[i].prob - refTop[i].prob);
      expect(d, `prob diff rank ${i + 1} (${refTop[i].gloss}) = ${d}`).toBeLessThan(PROB_TOL);
    }
  });
});
