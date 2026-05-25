// Real CV — the WebGPU/ORT-backed implementation of the public CV contract
// (init / processFrame / evaluateRep / reset / dispose), wiring the ORT runtime
// (workstream D) into the ported Stage-1 cascade (B) + Stage-2 classify/verifier
// (C). This is the integration seam: the React app swaps evaluate.ts to point
// here once parity passes; the WebGPU PoC reuses the same modules directly.
//
// processFrame runs the Net1->2->3 cascade on the frame, pushes the 49-kpt
// vector into the SignVerifier, and returns the running box state. evaluateRep
// reads the verifier's current vote for the target gloss. The continuous
// gray/orange/green the demo shows maps onto processFrame state + the verifier.

import type {
  DetectionResult,
  DrillType,
  Frame,
  InitResult,
} from './types';
import {
  type Backend,
  OrtRuntime,
  type RuntimeConfig,
} from './ort/session';
import {
  type Stage1FrameResult,
  stage1ProcessFrame,
} from './pipeline/stage1';
import type { RGBImage } from './pipeline/geom';
import {
  DEFAULT_NET4_DATA_CONFIG,
  makeClassify,
  type Net4DataConfig,
} from './pipeline/stage2';
import {
  DEFAULT_VERIFIER_OPTIONS,
  SignVerifier,
  type VerifierOptions,
} from './pipeline/verifier';

export interface RealCvConfig extends RuntimeConfig {
  // gloss -> class index (from net4 gloss_to_idx.json). Required so the
  // verifier knows the target column.
  glossToIdx: Record<string, number>;
  verifier?: Partial<VerifierOptions>;
  net4Data?: Net4DataConfig;
  // Run the heavy cascade once per N frames; skipped frames reuse the last
  // overlay/keypoints. Mirrors the demo's process_every_n (default 3).
  processEveryN?: number;
}

export interface ProcessFrameExtras {
  // Latest 49-kpt overlay (image px) + visibility, for drawing. Null until the
  // first cascade frame lands.
  keypoints: Float32Array | null;
  visibility: Float32Array | null;
  handsPresent: number;
  // The verifier's live status for the current target (gray/orange/green).
  status: 'gray' | 'orange' | 'green';
  targetConfMean: number;
  passFraction: number;
}

let runtime: OrtRuntime | null = null;
let verifier: SignVerifier | null = null;
let classify: ReturnType<typeof makeClassify> | null = null;
let net4Cfg: Net4DataConfig = DEFAULT_NET4_DATA_CONFIG;
let verifierOpts: VerifierOptions = DEFAULT_VERIFIER_OPTIONS;
let glossToIdx: Record<string, number> = {};

let targetGloss: string | null = null;
let processEveryN = 3;
let frameIndex = 0;
let framesBuffered = 0;
let backend: Backend = 'wasm';
let modelVersion = 'uninitialised';

// Last cascade output (reused on skipped frames).
let lastFrame: Stage1FrameResult | null = null;
let lastStatus: ProcessFrameExtras['status'] = 'gray';
let lastConfMean = 0;
let lastPassFraction = 0;

export async function init(config: RealCvConfig): Promise<InitResult> {
  glossToIdx = config.glossToIdx;
  net4Cfg = config.net4Data ?? DEFAULT_NET4_DATA_CONFIG;
  verifierOpts = { ...DEFAULT_VERIFIER_OPTIONS, ...config.verifier };
  processEveryN = config.processEveryN ?? 3;

  runtime = new OrtRuntime(config);
  const info = await runtime.init();
  backend = info.backend;
  modelVersion = info.modelVersion;

  classify = makeClassify(runtime.net4SessionAdapter, net4Cfg);
  verifier = new SignVerifier(classify, glossToIdx, verifierOpts);

  return {
    modelVersion,
    backend,
    warmupLatencyMs: info.warmupLatencyMs,
  };
}

/** Set / change the verified target. Resets the rolling vote (per the demo). */
export function setTarget(gloss: string): void {
  targetGloss = gloss;
  verifier?.reset();
  lastStatus = 'gray';
  lastConfMean = 0;
  lastPassFraction = 0;
}

export function setProcessEveryN(n: number): void {
  processEveryN = Math.max(1, Math.round(n));
}

/** Live tuning of the verifier vote (matches the demo's conf/vote sliders). */
export function setVerifierParams(params: Partial<VerifierOptions>): void {
  verifierOpts = { ...verifierOpts, ...params };
  // The SignVerifier reads opts at construction; rebuild it preserving target.
  if (runtime && classify) {
    verifier = new SignVerifier(classify, glossToIdx, verifierOpts);
    lastStatus = 'gray';
  }
}

/**
 * Run one frame through the cascade + verifier. Returns the public box state
 * plus the overlay extras (keypoints + verifier status) for the PoC to draw.
 * Skips the heavy cascade on (frameIndex % processEveryN != 0), reusing the
 * last overlay so the video stays smooth (mirrors the demo's cadence).
 */
export async function processFrameRGB(
  rgb: RGBImage,
): Promise<{ state: DetectionResult['state']; framesBuffered: number; extras: ProcessFrameExtras }> {
  framesBuffered++;
  const runCascade = frameIndex % processEveryN === 0 || lastFrame === null;
  frameIndex++;

  if (runtime && runCascade) {
    const result = await stage1ProcessFrame(rgb, runtime.stage1Sessions, runtime.contract);
    lastFrame = result;

    if (verifier) {
      const present = result.handsPresent > 0;
      await verifier.pushFrame(result.keypoints, present);
      if (targetGloss && targetGloss in glossToIdx) {
        const v = verifier.verify(targetGloss);
        lastConfMean = v.targetConfMean;
        lastPassFraction = v.passFraction;
        lastStatus = !present ? 'gray' : v.verified ? 'green' : 'orange';
      } else {
        lastStatus = present ? 'orange' : 'gray';
      }
    }
  }

  const handsPresent = lastFrame?.handsPresent ?? 0;
  const state: DetectionResult['state'] =
    handsPresent === 0 ? 'no-hands' : lastStatus === 'green' ? 'target-met' : 'low-confidence';

  return {
    state,
    framesBuffered,
    extras: {
      keypoints: lastFrame?.keypoints ?? null,
      visibility: lastFrame?.visibility ?? null,
      handsPresent,
      status: lastStatus,
      targetConfMean: lastConfMean,
      passFraction: lastPassFraction,
    },
  };
}

/**
 * Public contract processFrame. Decodes the ImageBitmap to RGB and delegates to
 * processFrameRGB. The PoC drives processFrameRGB directly (it already has the
 * pixel buffer), so this exists for the React app's Frame-based callers.
 */
export async function processFrame(
  frame: Frame,
): Promise<{ state: DetectionResult['state']; framesBuffered: number }> {
  const rgb = imageBitmapToRGB(frame.imageData);
  const { state, framesBuffered: fb } = await processFrameRGB(rgb);
  return { state, framesBuffered: fb };
}

/**
 * Snapshot the current verification decision for the target into the contract's
 * DetectionResult. The verifier already maintains the rolling vote from
 * processFrame, so this is a cheap read (<200ms trivially).
 */
export async function evaluateRep(
  _drillType: DrillType,
  target: string,
): Promise<DetectionResult> {
  const t0 = typeof performance !== 'undefined' ? performance.now() : Date.now();
  if (!verifier || !(target in glossToIdx)) {
    return { state: 'no-hands', confidence: 0, latencyMs: 0, modelVersion };
  }
  if (target !== targetGloss) setTarget(target);
  const v = verifier.verify(target);
  const handsPresent = lastFrame?.handsPresent ?? 0;
  const state: DetectionResult['state'] =
    handsPresent === 0 ? 'no-hands' : v.verified ? 'target-met' : 'low-confidence';
  const latencyMs =
    (typeof performance !== 'undefined' ? performance.now() : Date.now()) - t0;
  return { state, confidence: v.targetConfMean, latencyMs, modelVersion };
}

export function resetRepBuffer(): void {
  verifier?.reset();
  lastFrame = null;
  lastStatus = 'gray';
  lastConfMean = 0;
  lastPassFraction = 0;
  framesBuffered = 0;
  frameIndex = 0;
}

export async function dispose(): Promise<void> {
  await runtime?.dispose();
  runtime = null;
  verifier = null;
  classify = null;
  lastFrame = null;
}

export function getBackend(): Backend {
  return backend;
}

// ---------------------------------------------------------------------------
// ImageBitmap -> RGBImage via an offscreen canvas. Browser-only; the PoC builds
// RGBImage directly from a <canvas> getImageData so it never hits this path.
// ---------------------------------------------------------------------------
function imageBitmapToRGB(bmp: ImageBitmap): RGBImage {
  const canvas =
    typeof OffscreenCanvas !== 'undefined'
      ? new OffscreenCanvas(bmp.width, bmp.height)
      : Object.assign(document.createElement('canvas'), {
          width: bmp.width,
          height: bmp.height,
        });
  const ctx = (canvas as HTMLCanvasElement | OffscreenCanvas).getContext('2d', {
    willReadFrequently: true,
  }) as CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;
  ctx.drawImage(bmp as unknown as CanvasImageSource, 0, 0);
  const img = ctx.getImageData(0, 0, bmp.width, bmp.height);
  return rgbaToRGB(img.data, bmp.width, bmp.height);
}

/** Drop the alpha channel: RGBA Uint8ClampedArray -> packed RGB. */
export function rgbaToRGB(
  rgba: Uint8ClampedArray,
  width: number,
  height: number,
): RGBImage {
  const out = new Uint8Array(width * height * 3);
  for (let i = 0, j = 0; i < rgba.length; i += 4, j += 3) {
    out[j] = rgba[i];
    out[j + 1] = rgba[i + 1];
    out[j + 2] = rgba[i + 2];
  }
  return { data: out, width, height };
}
