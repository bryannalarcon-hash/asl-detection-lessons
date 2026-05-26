// Cascade worker — runs the entire Net1->2->3->4 pipeline + SignVerifier OFF
// the main thread. ORT's WebGPU EP creates its GPU device in this worker
// context just fine; the heavy JS glue (soft-argmax, NMS over the anchor grid,
// the crop/warpAffine passes) and the GPU readback all happen here.
//
// CAPTURE-A-REP model: there is NO per-frame real-time path. The main thread
// records a short clip, then ships the WHOLE frame sequence in one `rep`
// message. We run the cascade over every frame to get a keypoint sequence,
// classify the clip (Net4 top-3), and push the sequence through a fresh
// SignVerifier for the target, replying with one `verdict`.
//
// PERF: the cascade is BATCHED across the rep's frames (see batchedRuntime.ts)
// — one Net1 forward over all N frames, per-frame Net2 (or batched in 1-pass),
// one (or two) Net3 forwards over all hand crops, one Net4 forward.

import {
  NUM_KEYPOINTS,
  DEFAULT_PIPELINE_CONTRACT,
  type PipelineContract,
} from './ort/models';
import {
  classifyClip,
  glossList,
  makeClassify,
  DEFAULT_NET4_DATA_CONFIG,
} from './pipeline/stage2';
import { SignVerifier } from './pipeline/verifier';
import { rgbaToRGB } from './evaluate.real';
import type { RGBImage } from './pipeline/geom';
import { BatchedRuntime } from './batchedRuntime';

// --- message protocol (shared with captureRep.ts via re-export) ---------- //

/** One-time worker boot. Carries the gloss map + verdict knobs. */
export interface InitMsg {
  type: 'init';
  glossToIdx: Record<string, number>;
  confThresh: number;
  voteFrac: number;
  twoPass: boolean;
  matchMode: 'top1' | 'top3';
  precision: 'fp32' | 'fp16';
  net1Stride: number;
}

/**
 * A captured rep: the entire frame sequence in one message. Frames are packed
 * back-to-back into a single RGBA buffer (frameCount * width * height * 4 bytes)
 * so we transfer ONE buffer (zero-copy). The worker slices it per frame, runs
 * the cascade, then classifies + verifies.
 */
export interface RepMsg {
  type: 'rep';
  reqId: number;
  pixels: ArrayBuffer;
  frameCount: number;
  width: number;
  height: number;
  target: string;
}

export type ToWorker = InitMsg | RepMsg;

/** Worker finished init: active EP + warm-up timings. */
export interface ReadyMsg {
  type: 'ready';
  backend: 'webgpu' | 'wasm';
  modelVersion: string;
  warmupLatencyMs: number;
}

/** The verdict for one captured rep. */
export interface VerdictMsg {
  type: 'verdict';
  reqId: number;
  target: string;
  pass: boolean;
  verifierPassed: boolean;
  isTop1: boolean;
  inTop3: boolean;
  topK: { gloss: string; prob: number }[];
  targetConf: number;
  cascadeMs: number;
  classifyMs: number;
  framesProcessed: number;
  handsFrames: number;
  // Per-net inference timing + verifier window detail — for the dev CV readout
  // (full parity with the PoC/demo diagnostics).
  net1Ms: number;
  net2Ms: number;
  net3Ms: number;
  glueMs: number;
  passFraction: number;
  nWindows: number;
  targetConfMean: number;
}

export interface ErrorMsg {
  type: 'error';
  reqId?: number;
  message: string;
}

export type FromWorker = ReadyMsg | VerdictMsg | ErrorMsg;

// --- worker-owned state -------------------------------------------------- //
let runtime: BatchedRuntime | null = null;
let classify: ReturnType<typeof makeClassify> | null = null;
let glossToIdx: Record<string, number> = {};
let idxToGloss: string[] = [];

let confThresh = 0.25;
let voteFrac = 0.8;
let twoPass = false; // 1-pass Net3 by default
let matchMode: 'top1' | 'top3' = 'top1';
let precision: 'fp32' | 'fp16' = 'fp32';
let net1Stride = 32;

// One rep at a time: ORT sessions are not re-entrant.
let busy = false;

function post(msg: FromWorker, transfer: Transferable[] = []): void {
  (self as unknown as Worker).postMessage(msg, transfer);
}

// fp16 models live under /models/fp16/; fp32 at /models/. Clone the contract
// and repoint the four model URLs for the fp16 path.
function contractFor(p: 'fp32' | 'fp16'): PipelineContract {
  if (p === 'fp32') return DEFAULT_PIPELINE_CONTRACT;
  const c = structuredClone(DEFAULT_PIPELINE_CONTRACT);
  c.net1.url = c.net1.url.replace('/models/', '/models/fp16/');
  c.net2.url = c.net2.url.replace('/models/', '/models/fp16/');
  c.net3.url = c.net3.url.replace('/models/', '/models/fp16/');
  c.net4.url = c.net4.url.replace('/models/', '/models/fp16/');
  return c;
}

// Build the ORT runtime for the current precision and announce ready.
async function buildRuntime(): Promise<void> {
  runtime = new BatchedRuntime(contractFor(precision));
  const info = await runtime.init();
  classify = makeClassify(runtime.net4SessionAdapter, DEFAULT_NET4_DATA_CONFIG);
  post({
    type: 'ready',
    backend: info.backend,
    modelVersion: `${info.modelVersion} [${precision}]`,
    warmupLatencyMs: info.warmupLatencyMs,
  });
}

// --- init ---------------------------------------------------------------- //
async function handleInit(msg: InitMsg): Promise<void> {
  glossToIdx = msg.glossToIdx;
  idxToGloss = glossList(glossToIdx);
  confThresh = msg.confThresh;
  voteFrac = msg.voteFrac;
  twoPass = msg.twoPass;
  matchMode = msg.matchMode;
  precision = msg.precision;
  net1Stride = msg.net1Stride;
  await buildRuntime();
}

// --- evaluate one captured rep ------------------------------------------- //
async function handleRep(msg: RepMsg): Promise<void> {
  // Not-yet-ready MUST post an error (with reqId) — a bare return would leave
  // the main thread's pending promise unsettled and recordAttempt would hang.
  if (!runtime || !classify) {
    post({ type: 'error', reqId: msg.reqId, message: 'engine not ready' });
    return;
  }
  if (busy) return;
  busy = true;
  const W = msg.width;
  const H = msg.height;
  const T = msg.frameCount;
  const target = msg.target;
  const frameBytes = W * H * 4;
  const all = new Uint8ClampedArray(msg.pixels);

  try {
    // Slice the packed buffer into per-frame RGB images (alpha dropped).
    const rgbs: RGBImage[] = new Array(T);
    for (let t = 0; t < T; t++) {
      const slice = all.subarray(t * frameBytes, (t + 1) * frameBytes);
      rgbs[t] = rgbaToRGB(slice, W, H);
    }

    // Cascade, BATCHED.
    const tCas0 = performance.now();
    const { kFlat, vFlat, present, handsFrames, runMs } = await runtime.processClip(
      rgbs,
      twoPass,
      net1Stride,
    );
    const cascadeMs = performance.now() - tCas0;
    const glueMs = Math.max(0, cascadeMs - (runMs.net1 + runMs.net2 + runMs.net3));

    // Net4 clip classification -> top-3 + full softmax (for target conf).
    const tCls0 = performance.now();
    const clip = await classifyClip(
      runtime.net4SessionAdapter,
      kFlat,
      vFlat,
      T,
      W,
      H,
      idxToGloss,
      DEFAULT_NET4_DATA_CONFIG,
      5,
    );
    const classifyMs = performance.now() - tCls0;
    const topK = clip.topk.map((e) => ({ gloss: e.gloss, prob: e.prob }));
    const tidx = target in glossToIdx ? glossToIdx[target] : -1;
    const targetConf = tidx >= 0 ? clip.probs[tidx] : 0;

    // Push the WHOLE sequence through a fresh verifier, then read the verdict.
    const verifier = new SignVerifier(classify, glossToIdx, { confThresh, voteFrac });
    for (let t = 0; t < T; t++) {
      const frameKpts = kFlat.subarray(t * NUM_KEYPOINTS * 2, (t + 1) * NUM_KEYPOINTS * 2);
      await verifier.pushFrame(frameKpts, present[t]);
    }

    let verifierPassed = false;
    let passFraction = 0;
    let nWindows = 0;
    let targetConfMean = 0;
    if (tidx >= 0) {
      const v = verifier.verify(target);
      verifierPassed = v.verified;
      passFraction = v.passFraction;
      nWindows = v.nWindows;
      targetConfMean = v.targetConfMean;
    }

    const isTop1 = topK.length > 0 && topK[0].gloss === target;
    // Acceptance stays top-3 even though we now return/show the top-5.
    const inTop3 = topK.slice(0, 3).some((e) => e.gloss === target);
    const matched = matchMode === 'top3' ? inTop3 : isTop1;
    const pass = verifierPassed || matched;

    post({
      type: 'verdict',
      reqId: msg.reqId,
      target,
      pass,
      verifierPassed,
      isTop1,
      inTop3,
      topK,
      targetConf,
      framesProcessed: T,
      handsFrames,
      cascadeMs,
      classifyMs,
      net1Ms: runMs.net1,
      net2Ms: runMs.net2,
      net3Ms: runMs.net3,
      glueMs,
      passFraction,
      nWindows,
      targetConfMean,
    });
  } catch (err) {
    post({ type: 'error', reqId: msg.reqId, message: (err as Error).message });
  } finally {
    busy = false;
  }
}

// --- message pump -------------------------------------------------------- //
self.onmessage = (ev: MessageEvent<ToWorker>) => {
  const msg = ev.data;
  switch (msg.type) {
    case 'init':
      void handleInit(msg).catch((err) =>
        post({ type: 'error', message: (err as Error).message }),
      );
      break;
    case 'rep':
      void handleRep(msg);
      break;
  }
};
