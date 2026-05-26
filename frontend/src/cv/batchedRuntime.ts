// GPU-batched Stage-1 cascade for capture-a-rep. Runs the heavy nets ONCE over
// the whole rep instead of once per frame:
//
//   Net1  stack all N frames -> ONE forward (N,3,256,256) -> per-frame remap.
//   Net2  PER-FRAME forward in 2-pass mode (kept per-frame on purpose: batching
//         its conv jitters box logits ~1e-6, and the 2-pass Net3 re-crop is
//         chaotically sensitive to that). 1-pass uses ONE batched forward.
//   Net3  gather every hand crop across all frames -> ONE batched pass-1; if the
//         2-pass toggle is on, gather pass-2 crops -> ONE batched pass-2.
//   Net4  unchanged single clip forward (done by the caller via classifyClip).
//
// Numerical equivalence holds because the models are in eval mode (BatchNorm
// uses running stats, so batch composition can't change a sample's output) and
// soft-argmax is per-sample. The only drift is float reordering (<0.33px).
//
// This module owns its OWN ORT sessions (built directly from the contract URLs)
// so we can feed batched (N,...) tensors. It REUSES the parity-tested pure
// helpers from ./pipeline/geom + ./pipeline/anchors verbatim.

import * as ort from 'onnxruntime-web/webgpu';

import {
  DEFAULT_PIPELINE_CONTRACT,
  NUM_KEYPOINTS,
  RIGHT_HAND_START,
  LEFT_HAND_START,
  type PipelineContract,
} from './ort/models';
import {
  type Affine,
  type Box,
  type RGBImage,
  cropHandAffine,
  expandBox,
  letterbox,
  softArgmax2d,
  unprojectKpts,
  uprightRotationDeg,
  warpAffineBilinear,
} from './pipeline/geom';
import {
  type PalmBox,
  assignHandSide,
  buildAnchors,
  chwNormInto,
  decodeNet2,
  decodeNet3Batch,
} from './batchedDecode';
import type { Net4Session } from './pipeline/stage2';

export type Backend = 'webgpu' | 'wasm';

export interface InitResult {
  backend: Backend;
  modelVersion: string;
  warmupLatencyMs: number;
  perNetWarmupMs: { net1: number; net2: number; net3: number; net4: number };
}

const MODEL_VERSION = 'v3-onnx-webgpu-batched' as const;
// MUST match the installed onnxruntime-web version exactly — the JS loader
// fetches its .wasm/.jsep binaries from this CDN dir, and a version skew fails
// session creation (which silently disabled the in-app CV / the Record button).
const ORT_VERSION = '1.26.0';
const DEFAULT_WASM_CDN =
  `https://cdn.jsdelivr.net/npm/onnxruntime-web@${ORT_VERSION}/dist/`;

let configured = false;
function configureOrtEnv(wasmCdnBase: string): void {
  if (configured) return;
  ort.env.wasm.wasmPaths = wasmCdnBase;
  ort.env.wasm.numThreads = 1;
  ort.env.wasm.proxy = false;
  configured = true;
}

// ---------------------------------------------------------------------------
// The batched runtime: owns the 4 ORT sessions + anchors + contract.
// ---------------------------------------------------------------------------
export class BatchedRuntime {
  readonly contract: PipelineContract;
  private readonly wasmCdnBase: string;
  private net1!: ort.InferenceSession;
  private net2!: ort.InferenceSession;
  private net3!: ort.InferenceSession;
  private net4!: ort.InferenceSession;
  private anchors!: Float32Array;
  private _backend: Backend = 'wasm';
  // Per-rep accumulator of bare .run() (inference + GPU readback) time per net,
  // reset at the top of processClip. Diagnoses GPU-compute vs JS-glue.
  readonly runMs = { net1: 0, net2: 0, net3: 0 };

  // await session.run resolves only once the output data is read back, so timing
  // around it captures real GPU compute + readback (not just dispatch).
  private async timedRun(
    net: ort.InferenceSession,
    feeds: Record<string, ort.Tensor>,
    key: 'net1' | 'net2' | 'net3',
  ): Promise<ort.InferenceSession.OnnxValueMapType> {
    const t = performance.now();
    const out = await net.run(feeds);
    this.runMs[key] += performance.now() - t;
    return out;
  }

  constructor(contract: PipelineContract = DEFAULT_PIPELINE_CONTRACT, wasmCdnBase = DEFAULT_WASM_CDN) {
    this.contract = contract;
    this.wasmCdnBase = wasmCdnBase;
  }

  get backend(): Backend {
    return this._backend;
  }

  /** Net4 seam for stage2.ts classifyClip / makeClassify (single clip forward). */
  get net4SessionAdapter(): Net4Session {
    const spec = this.contract.net4;
    return {
      run: async (features: Float32Array, mask: Uint8Array, T: number, C: number) => {
        const featTensor = new ort.Tensor('float32', features, [1, T, C]);
        const maskData = new Float32Array(T);
        for (let i = 0; i < T; i++) maskData[i] = mask[i] ? 1 : 0;
        const maskTensor = new ort.Tensor('float32', maskData, [1, T]);
        const out = await this.net4.run({
          [spec.features.name]: featTensor,
          [spec.keyPaddingMask.name]: maskTensor,
        });
        return out[spec.logits.name].data as Float32Array;
      },
    };
  }

  async init(): Promise<InitResult> {
    configureOrtEnv(this.wasmCdnBase);
    const eps: Backend[] = ['webgpu', 'wasm'];
    const c = this.contract;
    [this.net1, this.net2, this.net3, this.net4] = await Promise.all([
      ort.InferenceSession.create(c.net1.url, { executionProviders: eps }),
      ort.InferenceSession.create(c.net2.url, { executionProviders: eps }),
      ort.InferenceSession.create(c.net3.url, { executionProviders: eps }),
      ort.InferenceSession.create(c.net4.url, { executionProviders: eps }),
    ]);
    this.anchors = buildAnchors(c.net2);

    const t0 = performance.now();
    const perNetWarmupMs = await this.warmup();
    const warmupLatencyMs = performance.now() - t0;

    const hasGpu =
      typeof navigator !== 'undefined' &&
      typeof (navigator as Navigator & { gpu?: unknown }).gpu !== 'undefined';
    this._backend = hasGpu ? 'webgpu' : 'wasm';

    return { backend: this._backend, modelVersion: MODEL_VERSION, warmupLatencyMs, perNetWarmupMs };
  }

  private async warmup(): Promise<InitResult['perNetWarmupMs']> {
    const c = this.contract;
    const t = async (fn: () => Promise<unknown>) => {
      const s = performance.now();
      await fn();
      return performance.now() - s;
    };
    // Warm each net at batch 1 (compiles shaders; dynamic batch recompiles
    // lazily on the first real batch but that's a one-time cost per rep size).
    const net1 = await t(() =>
      this.net1.run({
        [c.net1.input.name]: new ort.Tensor(
          'float32',
          new Float32Array(3 * c.net1.inputSize * c.net1.inputSize),
          [1, 3, c.net1.inputSize, c.net1.inputSize],
        ),
      }),
    );
    const net2 = await t(() =>
      this.net2.run({
        [c.net2.input.name]: new ort.Tensor(
          'float32',
          new Float32Array(3 * c.net2.inputSize * c.net2.inputSize),
          [1, 3, c.net2.inputSize, c.net2.inputSize],
        ),
      }),
    );
    const net3 = await t(() =>
      this.net3.run({
        [c.net3.input.name]: new ort.Tensor(
          'float32',
          new Float32Array(3 * c.net3.cropSize * c.net3.cropSize),
          [1, 3, c.net3.cropSize, c.net3.cropSize],
        ),
      }),
    );
    const net4 = await t(() => {
      const T = c.net4.maxFrames;
      const C = c.net4.inChannels;
      return this.net4.run({
        [c.net4.features.name]: new ort.Tensor('float32', new Float32Array(T * C), [1, T, C]),
        [c.net4.keyPaddingMask.name]: new ort.Tensor('float32', new Float32Array(T), [1, T]),
      });
    });
    return { net1, net2, net3, net4 };
  }

  // --- Net1: ONE forward over all frames --------------------------------- //
  private async net1Batched(
    rgbs: RGBImage[],
    kFlat: Float32Array,
    vFlat: Float32Array,
    stride: number,
  ): Promise<void> {
    const c = this.contract.net1;
    const N = rgbs.length;
    const size = c.inputSize;
    const plane = 3 * size * size;

    // Net1 (face/body) is the cascade's 94% cost. Body pose is near-static
    // frame-to-frame, so at stride>1 we run Net1 only on every Nth frame and
    // HOLD the body/face slots from the nearest computed frame. Hands
    // (Net2/Net3) still run every frame.
    const sel: number[] = [];
    for (let f = 0; f < N; f += Math.max(1, stride)) sel.push(f);
    if (sel.length === 0 || sel[sel.length - 1] !== N - 1) sel.push(N - 1);
    const B = sel.length;

    const batch = new Float32Array(B * plane);
    const metas: { W: number; H: number; scale: number; dx: number; dy: number }[] = [];
    for (let b = 0; b < B; b++) {
      const lb = letterbox(rgbs[sel[b]], size);
      chwNormInto(lb.data, size, batch, b * plane);
      metas.push({ W: rgbs[sel[b]].width, H: rgbs[sel[b]].height, scale: lb.scale, dx: lb.dx, dy: lb.dy });
    }
    const out = await this.timedRun(this.net1, {
      [c.input.name]: new ort.Tensor('float32', batch, [B, 3, size, size]),
    }, 'net1');
    const hm = out[c.heatmaps.name];
    const [, K, Hm, Wm] = hm.dims as number[];
    const data = hm.data as Float32Array;
    const perFrame = K * Hm * Wm;
    const hw = Hm * Wm;
    const ratio = size / Wm;
    const slice = c.keypointSlice;
    const sIdx = slice ? slice[0] : 0;
    const eIdx = slice ? slice[1] : NUM_KEYPOINTS;
    const Kn = Math.min(K, eIdx - sIdx);

    for (let b = 0; b < B; b++) {
      const f = sel[b];
      const fb = b * perFrame;
      const coordsHm = softArgmax2d(data.subarray(fb, fb + perFrame), K, Hm, Wm);
      const m = metas[b];
      for (let j = 0; j < Kn; j++) {
        // peak = max over this channel's heatmap.
        let mx = -Infinity;
        const base = fb + j * hw;
        for (let i = 0; i < hw; i++) {
          const v = data[base + i];
          if (v > mx) mx = v;
        }
        const x = (coordsHm[j * 2] * ratio - m.dx) / m.scale;
        const y = (coordsHm[j * 2 + 1] * ratio - m.dy) / m.scale;
        if (x >= 0 && x < m.W && y >= 0 && y < m.H && mx > c.peakThreshold) {
          const gi = sIdx + j;
          kFlat[(f * NUM_KEYPOINTS + gi) * 2] = x;
          kFlat[(f * NUM_KEYPOINTS + gi) * 2 + 1] = y;
          vFlat[f * NUM_KEYPOINTS + gi] = 1.0;
        }
      }
    }

    // Hold body/face slots for the skipped frames from the nearest computed one.
    if (B < N) {
      const selSet = new Set(sel);
      for (let f = 0; f < N; f++) {
        if (selSet.has(f)) continue;
        let nf = sel[0];
        let bestD = Math.abs(f - nf);
        for (let s = 1; s < B; s++) {
          const d = Math.abs(f - sel[s]);
          if (d < bestD) {
            bestD = d;
            nf = sel[s];
          } else {
            break; // sel ascending: distance is convex, stop past the minimum
          }
        }
        for (let gi = sIdx; gi < sIdx + Kn; gi++) {
          kFlat[(f * NUM_KEYPOINTS + gi) * 2] = kFlat[(nf * NUM_KEYPOINTS + gi) * 2];
          kFlat[(f * NUM_KEYPOINTS + gi) * 2 + 1] = kFlat[(nf * NUM_KEYPOINTS + gi) * 2 + 1];
          vFlat[f * NUM_KEYPOINTS + gi] = vFlat[nf * NUM_KEYPOINTS + gi];
        }
      }
    }
  }

  // --- Net2: PER-FRAME forward (used in 2-pass mode for bit-identical boxes) //
  private async net2OneFrame(rgb: RGBImage): Promise<PalmBox[]> {
    const c = this.contract.net2;
    const size = c.inputSize;
    const lb = letterbox(rgb, size);
    const input = new Float32Array(3 * size * size);
    chwNormInto(lb.data, size, input, 0);
    const out = await this.timedRun(this.net2, {
      [c.input.name]: new ort.Tensor('float32', input, [1, 3, size, size]),
    }, 'net2');
    const cls = out[c.cls.name].data as Float32Array;
    const box = out[c.box.name].data as Float32Array;
    const N = (out[c.cls.name].dims as number[])[1];
    return decodeNet2(c, this.anchors, cls, box, N, lb);
  }

  // --- Net2: ONE batched forward over all frames (1-pass mode) ----------- //
  // Net2 is a per-frame conv with no cross-frame state, so batching is the same
  // math as N separate forwards (BatchNorm uses running stats in eval); it just
  // collapses N GPU dispatch + readback round-trips into one. Box logits can
  // reorder by ~1e-6 vs per-frame, which is why 2-pass (whose re-crop is
  // sensitive to it) still uses net2OneFrame; in 1-pass nothing re-crops so the
  // decoded boxes are unaffected.
  private async net2Batched(rgbs: RGBImage[]): Promise<PalmBox[][]> {
    const c = this.contract.net2;
    const size = c.inputSize;
    const N = rgbs.length;
    const plane = 3 * size * size;
    const batch = new Float32Array(N * plane);
    const lbs: { scale: number; dx: number; dy: number }[] = [];
    for (let f = 0; f < N; f++) {
      const lb = letterbox(rgbs[f], size);
      chwNormInto(lb.data, size, batch, f * plane);
      lbs.push({ scale: lb.scale, dx: lb.dx, dy: lb.dy });
    }
    const out = await this.timedRun(this.net2, {
      [c.input.name]: new ort.Tensor('float32', batch, [N, 3, size, size]),
    }, 'net2');
    const cls = out[c.cls.name].data as Float32Array;
    const box = out[c.box.name].data as Float32Array;
    const Na = (out[c.cls.name].dims as number[])[1];
    const result: PalmBox[][] = new Array(N);
    for (let f = 0; f < N; f++) {
      const clsRow = cls.subarray(f * Na, (f + 1) * Na);
      const boxRow = box.subarray(f * Na * 4, (f + 1) * Na * 4);
      result[f] = decodeNet2(c, this.anchors, clsRow, boxRow, Na, lbs[f]);
    }
    return result;
  }

  // --- Net3: batched pass(es) -------------------------------------------- //
  private async net3Forward(crops: Uint8Array[]): Promise<Float32Array[]> {
    const c = this.contract.net3;
    const B = crops.length;
    const plane = 3 * c.cropSize * c.cropSize;
    const batch = new Float32Array(B * plane);
    for (let b = 0; b < B; b++) chwNormInto(crops[b], c.cropSize, batch, b * plane);
    const out = await this.timedRun(this.net3, {
      [c.input.name]: new ort.Tensor('float32', batch, [B, 3, c.cropSize, c.cropSize]),
    }, 'net3');
    const t = out[c.output.name];
    return decodeNet3Batch(c, t.data as Float32Array, t.dims as number[], B);
  }

  // ---------------------------------------------------------------------- //
  // Public: process the whole clip. Returns the (T,49) kpt/vis sequence plus
  // the per-frame hand-presence flags.
  // ---------------------------------------------------------------------- //
  async processClip(
    rgbs: RGBImage[],
    twoPass: boolean,
    net1Stride = 1,
  ): Promise<{
    kFlat: Float32Array;
    vFlat: Float32Array;
    present: boolean[];
    handsFrames: number;
    runMs: { net1: number; net2: number; net3: number };
  }> {
    const c = this.contract;
    const N = rgbs.length;
    this.runMs.net1 = 0;
    this.runMs.net2 = 0;
    this.runMs.net3 = 0;
    const kFlat = new Float32Array(N * NUM_KEYPOINTS * 2);
    const vFlat = new Float32Array(N * NUM_KEYPOINTS);

    // Net1: batched forward (strided), written into the body slots in place.
    await this.net1Batched(rgbs, kFlat, vFlat, net1Stride);

    // Snapshot Net1 body kpts/vis per frame for hand-side assignment.
    const bodyKpts: Float32Array[] = [];
    const bodyVis: Float32Array[] = [];
    for (let f = 0; f < N; f++) {
      bodyKpts.push(kFlat.subarray(f * NUM_KEYPOINTS * 2, (f + 1) * NUM_KEYPOINTS * 2).slice());
      bodyVis.push(vFlat.subarray(f * NUM_KEYPOINTS, (f + 1) * NUM_KEYPOINTS).slice());
    }

    // Net2: per-frame. Collect hand jobs across all frames.
    const jobs: {
      frame: number;
      side: 'right' | 'left';
      box: Box;
      M: Affine | null;
      coords1: Float32Array | null;
    }[] = [];
    // 1-pass: ONE batched Net2 forward. 2-pass: per-frame (bit-identical boxes
    // because its re-crop is sensitive to ~1e-6 batched-conv reordering).
    const batchedBoxes = twoPass ? null : await this.net2Batched(rgbs);
    for (let f = 0; f < N; f++) {
      const boxes = batchedBoxes ? batchedBoxes[f] : await this.net2OneFrame(rgbs[f]);
      if (boxes.length === 0) continue;
      const sides = assignHandSide(boxes, bodyKpts[f], bodyVis[f]);
      for (let bi = 0; bi < boxes.length; bi++) {
        const expanded = expandBox(boxes[bi].xyxy, rgbs[f].width, rgbs[f].height, c.net3.boxExpandFrac);
        if (!expanded) continue;
        const [x1, y1, x2, y2] = expanded;
        jobs.push({
          frame: f,
          side: sides[bi] as 'right' | 'left',
          box: { x: x1, y: y1, w: x2 - x1, h: y2 - y1 },
          M: null,
          coords1: null,
        });
      }
    }

    // Net3 pass-1: build every axis-aligned crop, forward once. (This ckpt has
    // no Net2 kpt head, so pass-1 rotation is always 0 — matches run_net3.)
    if (jobs.length > 0) {
      const crops1: Uint8Array[] = [];
      for (const job of jobs) {
        const M = cropHandAffine(job.box, c.net3.cropSize, 0.0);
        job.M = M;
        crops1.push(warpAffineBilinear(rgbs[job.frame], M, c.net3.cropSize));
      }
      const coords1 = await this.net3Forward(crops1);
      for (let i = 0; i < jobs.length; i++) jobs[i].coords1 = coords1[i];

      // Decide pass-2 jobs (only when the toggle is on).
      const finalResults: (Float32Array | null)[] = new Array(jobs.length).fill(null);
      const pass2: number[] = [];
      for (let i = 0; i < jobs.length; i++) {
        if (!twoPass) {
          finalResults[i] = unprojectKpts(jobs[i].coords1!, jobs[i].M!, c.net3.numKeypoints);
        } else {
          pass2.push(i);
        }
      }

      if (pass2.length > 0) {
        const crops2: Uint8Array[] = [];
        const M2s: Affine[] = [];
        for (const i of pass2) {
          const co = jobs[i].coords1!;
          const rot = uprightRotationDeg([co[0], co[1]], [co[9 * 2], co[9 * 2 + 1]]);
          const M2 = cropHandAffine(jobs[i].box, c.net3.cropSize, rot);
          M2s.push(M2);
          crops2.push(warpAffineBilinear(rgbs[jobs[i].frame], M2, c.net3.cropSize));
        }
        const coords2 = await this.net3Forward(crops2);
        for (let p = 0; p < pass2.length; p++) {
          finalResults[pass2[p]] = unprojectKpts(coords2[p], M2s[p], c.net3.numKeypoints);
        }
      }

      // Fill hand slots, mirroring the per-keypoint in-frame test.
      for (let i = 0; i < jobs.length; i++) {
        const res = finalResults[i];
        if (!res) continue;
        const f = jobs[i].frame;
        const slotStart = jobs[i].side === 'right' ? RIGHT_HAND_START : LEFT_HAND_START;
        for (let j = 0; j < c.net3.numKeypoints; j++) {
          const x = res[j * 2];
          const y = res[j * 2 + 1];
          if (x >= 0 && x < rgbs[f].width && y >= 0 && y < rgbs[f].height) {
            kFlat[(f * NUM_KEYPOINTS + slotStart + j) * 2] = x;
            kFlat[(f * NUM_KEYPOINTS + slotStart + j) * 2 + 1] = y;
            vFlat[f * NUM_KEYPOINTS + slotStart + j] = 1.0;
          }
        }
      }
    }

    // Per-frame hand presence = any hand slot visible.
    const present: boolean[] = new Array(N);
    let handsFrames = 0;
    for (let f = 0; f < N; f++) {
      let hands = false;
      for (let j = RIGHT_HAND_START; j < LEFT_HAND_START + 21; j++) {
        if (vFlat[f * NUM_KEYPOINTS + j] > 0.5) {
          hands = true;
          break;
        }
      }
      present[f] = hands;
      if (hands) handsFrames++;
    }
    return { kFlat, vFlat, present, handsFrames, runMs: { ...this.runMs } };
  }
}
