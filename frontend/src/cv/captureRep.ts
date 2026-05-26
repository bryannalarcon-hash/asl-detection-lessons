// Public, app-facing capture-a-rep API. Owns a Web Worker that runs the entire
// batched Net1->2->3->4 cascade + SignVerifier off the main thread.
//
// Usage:
//   await initCaptureRep({ glossToIdx });
//   const verdict = await evaluateClip(frames, 'hello');
//   disposeCaptureRep();
//
// One rep is processed at a time (the worker's ORT sessions are not
// re-entrant), so a single in-flight promise maps the posted rep to its
// verdict; concurrent evaluateClip calls reject until the in-flight one
// resolves.

import type {
  FromWorker,
  InitMsg,
  RepMsg,
} from './captureWorker';

export interface CaptureRepConfig {
  glossToIdx: Record<string, number>;
  net1Stride?: number; // run Net1 every Nth frame, hold body/face slots (default 32)
  precision?: 'fp32' | 'fp16'; // which ONNX set to load (default 'fp32')
  confThresh?: number; // verifier per-window confidence gate (default 0.25)
  voteFrac?: number; // verifier window pass fraction (default 0.8)
  twoPass?: boolean; // Net3 2-pass self-orient toggle (default false)
}

export interface RepVerdict {
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
  // Per-net timing + verifier window detail (surfaced in the dev CV readout).
  net1Ms: number;
  net2Ms: number;
  net3Ms: number;
  glueMs: number;
  passFraction: number;
  nWindows: number;
  targetConfMean: number;
}

export interface InitCaptureRepResult {
  backend: 'webgpu' | 'wasm';
  modelVersion: string;
  warmupLatencyMs: number;
}

interface Pending<T> {
  resolve: (value: T) => void;
  reject: (reason: Error) => void;
}

let worker: Worker | null = null;
let initPending: Pending<InitCaptureRepResult> | null = null;
// Cached init promise so initCaptureRep is idempotent across concurrent / repeat
// calls (React StrictMode double-invokes effects in dev). Cleared on dispose.
let initPromise: Promise<InitCaptureRepResult> | null = null;
let repPending: Pending<RepVerdict> | null = null;
let repReqId = 0;
// The reqId of the rep currently awaiting a verdict. A verdict/error whose
// reqId doesn't match is stale (e.g. a late reply after a rejected/superseded
// rep) and must be ignored so we never resolve with another rep's result.
let inFlightReqId = 0;

function ensureWorker(): Worker {
  if (worker) return worker;
  const w = new Worker(new URL('./captureWorker.ts', import.meta.url), {
    type: 'module',
  });
  w.onmessage = (ev: MessageEvent<FromWorker>) => handleMessage(ev.data);
  w.onerror = (ev: ErrorEvent) => {
    const err = new Error(ev.message || 'capture worker error');
    initPending?.reject(err);
    repPending?.reject(err);
    initPending = null;
    repPending = null;
  };
  worker = w;
  return w;
}

function handleMessage(msg: FromWorker): void {
  switch (msg.type) {
    case 'ready':
      initPending?.resolve({
        backend: msg.backend,
        modelVersion: msg.modelVersion,
        warmupLatencyMs: msg.warmupLatencyMs,
      });
      initPending = null;
      break;
    case 'verdict':
      if (msg.reqId !== inFlightReqId) return;
      repPending?.resolve({
        pass: msg.pass,
        verifierPassed: msg.verifierPassed,
        isTop1: msg.isTop1,
        inTop3: msg.inTop3,
        topK: msg.topK,
        targetConf: msg.targetConf,
        cascadeMs: msg.cascadeMs,
        classifyMs: msg.classifyMs,
        framesProcessed: msg.framesProcessed,
        handsFrames: msg.handsFrames,
        net1Ms: msg.net1Ms,
        net2Ms: msg.net2Ms,
        net3Ms: msg.net3Ms,
        glueMs: msg.glueMs,
        passFraction: msg.passFraction,
        nWindows: msg.nWindows,
        targetConfMean: msg.targetConfMean,
      });
      repPending = null;
      break;
    case 'error': {
      const err = new Error(msg.message);
      // An error during init resolves the init promise; otherwise it's a rep.
      if (initPending) {
        initPending.reject(err);
        initPending = null;
      } else {
        // Ignore a stale rep error (mismatched reqId) so a late reply from a
        // superseded rep never settles the current in-flight promise.
        if (msg.reqId !== undefined && msg.reqId !== inFlightReqId) return;
        repPending?.reject(err);
        repPending = null;
      }
      break;
    }
  }
}

/**
 * Boot the worker, load the 4 ONNX nets for the chosen precision, warm up the
 * GPU shaders, and resolve once the backend + warm-up latency are known.
 */
export function initCaptureRep(cfg: CaptureRepConfig): Promise<InitCaptureRepResult> {
  // Idempotent: reuse an in-flight or completed init rather than erroring, so a
  // StrictMode double-mount (or any racing caller) doesn't trip "already in
  // flight" and silently disable the in-app CV.
  if (initPromise) return initPromise;
  const w = ensureWorker();
  const init: InitMsg = {
    type: 'init',
    glossToIdx: cfg.glossToIdx,
    net1Stride: cfg.net1Stride ?? 32,
    precision: cfg.precision ?? 'fp32',
    confThresh: cfg.confThresh ?? 0.25,
    voteFrac: cfg.voteFrac ?? 0.8,
    twoPass: cfg.twoPass ?? false,
    // Top-3 acceptance: a rep passes if the target is among the model's top 3
    // (78% top-1 vs 91% top-3, and wasm-EP keypoints are rougher) — fairer for
    // the learner. The verifier vote still gates alongside it.
    matchMode: 'top3',
  };
  initPromise = new Promise<InitCaptureRepResult>((resolve, reject) => {
    initPending = { resolve, reject };
    w.postMessage(init);
  });
  return initPromise;
}

/**
 * Warm the engine ahead of the practice screen: fetch the gloss map and kick
 * off the (idempotent) init so the worker + 4 ONNX nets are loaded and warmed
 * by the time the learner reaches a lesson. Safe to call repeatedly and from
 * multiple screens; errors are swallowed (Practice's useCaptureRep re-attempts
 * and degrades to self-report if CV truly can't load).
 */
export async function preloadCaptureRep(): Promise<void> {
  if (initPromise) return;
  try {
    const resp = await fetch('/models/gloss_to_idx.json');
    if (!resp.ok) return;
    const data = (await resp.json()) as { gloss_to_idx: Record<string, number> };
    await initCaptureRep({ glossToIdx: data.gloss_to_idx });
  } catch {
    // Swallow — the practice screen retries and falls back to self-report.
  }
}

/**
 * Pack the captured frames into one zero-copy RGBA buffer, ship them to the
 * worker, and await the verdict for `target`. Rejects if the worker is not
 * initialized, if a rep is already in flight, or if `frames` is empty / ragged.
 */
export function evaluateClip(frames: ImageData[], target: string): Promise<RepVerdict> {
  if (!worker) {
    return Promise.reject(new Error('evaluateClip called before initCaptureRep'));
  }
  if (repPending) {
    return Promise.reject(new Error('evaluateClip already in flight'));
  }
  if (frames.length === 0) {
    return Promise.reject(new Error('evaluateClip called with no frames'));
  }

  const width = frames[0].width;
  const height = frames[0].height;
  const frameBytes = width * height * 4;
  const T = frames.length;
  const packed = new Uint8ClampedArray(T * frameBytes);
  for (let t = 0; t < T; t++) {
    const f = frames[t];
    if (f.width !== width || f.height !== height) {
      return Promise.reject(new Error('evaluateClip frames must share dimensions'));
    }
    packed.set(f.data, t * frameBytes);
  }

  const reqId = ++repReqId;
  inFlightReqId = reqId;
  const msg: RepMsg = {
    type: 'rep',
    reqId,
    pixels: packed.buffer,
    frameCount: T,
    width,
    height,
    target,
  };
  return new Promise<RepVerdict>((resolve, reject) => {
    repPending = { resolve, reject };
    worker!.postMessage(msg, [packed.buffer]);
  });
}

/** Tear down the worker and reject any in-flight promises. */
export function disposeCaptureRep(): void {
  if (worker) {
    worker.terminate();
    worker = null;
  }
  const err = new Error('capture worker disposed');
  initPending?.reject(err);
  repPending?.reject(err);
  initPending = null;
  repPending = null;
  initPromise = null;
}
