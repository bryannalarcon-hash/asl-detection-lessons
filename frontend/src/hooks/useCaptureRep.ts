import { useCallback, useEffect, useRef, useState } from 'react';
import {
  initCaptureRep,
  evaluateClip,
  disposeCaptureRep,
  type RepVerdict,
} from '@/cv/captureRep';

// Capture tuning — ported from the validated playground capture loop.
const COUNTDOWN_SEC = 3;
const RECORD_MS = 5000; // ~5s capture window
const MAX_FRAMES = 64; // Net4's full trained window; sampling/culling targets this

// Motion-gated culling tuning (drop near-static runs before the cascade).
const MOTION_GRID = 24;
const CULL_MIN_FRAMES = 12;
const CULL_MAX_GAP = 6;

export type CapturePhase = 'idle' | 'countdown' | 'recording' | 'evaluating';

export interface UseCaptureRepResult {
  /** True once the worker has loaded the nets and warmed up. */
  ready: boolean;
  /** True if init failed (no WebGPU / model fetch failed) — caller degrades. */
  notReady: boolean;
  backend: 'webgpu' | 'wasm' | null;
  /** True while a countdown/record/evaluate cycle is in flight. */
  recording: boolean;
  phase: CapturePhase;
  /** Seconds left on the countdown (0 outside countdown). */
  countdown: number;
  lastVerdict: RepVerdict | null;
  /** Clear the last verdict (call on sign advance so a stale diagnosis can't
   * bleed into a new sign's hint). */
  resetVerdict(): void;
  /** True if `gloss` is a known model class (case-sensitive, already uppercased). */
  hasGloss(gloss: string): boolean;
  /**
   * Run a full rep: 3-2-1 countdown, ~5s capture from `videoEl`, cull+sample to
   * <=64 frames, then evaluate against `targetGloss`. Resolves with the verdict,
   * or null if not ready / capture produced no frames / evaluation threw.
   */
  recordAttempt(
    videoEl: HTMLVideoElement,
    targetGloss: string
  ): Promise<RepVerdict | null>;
}

/** Mean abs grayscale difference per sampled pixel (0..255) between two frames. */
function frameMotion(a: ImageData, b: ImageData): number {
  const W = a.width;
  const H = a.height;
  const sx = Math.max(1, Math.floor(W / MOTION_GRID));
  const sy = Math.max(1, Math.floor(H / MOTION_GRID));
  const da = a.data;
  const db = b.data;
  let sum = 0;
  let n = 0;
  for (let y = 0; y < H; y += sy) {
    for (let x = 0; x < W; x += sx) {
      const i = (y * W + x) * 4;
      const ga = da[i] + da[i + 1] + da[i + 2];
      const gb = db[i] + db[i + 1] + db[i + 2];
      sum += Math.abs(ga - gb);
      n++;
    }
  }
  return n ? sum / (n * 3) : 0;
}

/**
 * Keep above-average-motion frames (+ the first, + a forced frame every
 * CULL_MAX_GAP), then floor to CULL_MIN_FRAMES and cap to `max`. Collapsing
 * near-static runs trims cascade cost while keeping the informative frames,
 * unlike a blind uniform subsample.
 */
function cullStaticFrames(frames: ImageData[], max: number): ImageData[] {
  const n = frames.length;
  if (n <= CULL_MIN_FRAMES) return frames;

  let meanMotion = 0;
  const motion = new Float32Array(n);
  for (let i = 1; i < n; i++) {
    motion[i] = frameMotion(frames[i], frames[i - 1]);
    meanMotion += motion[i];
  }
  meanMotion /= n - 1;
  const thr = meanMotion * 0.5;

  const keep: number[] = [0];
  let last = 0;
  for (let i = 1; i < n; i++) {
    if (motion[i] >= thr || i - last >= CULL_MAX_GAP) {
      keep.push(i);
      last = i;
    }
  }

  let idx = keep;
  if (idx.length < CULL_MIN_FRAMES) {
    idx = [];
    const step = n / CULL_MIN_FRAMES;
    for (let i = 0; i < CULL_MIN_FRAMES; i++) idx.push(Math.floor(i * step));
  }
  if (idx.length > max) {
    const out: number[] = [];
    const step = idx.length / max;
    for (let i = 0; i < max; i++) out.push(idx[Math.floor(i * step)]);
    idx = out;
  }
  return idx.map((i) => frames[i]);
}

/** Promise-based delay. */
function wait(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

/**
 * Capture ~RECORD_MS of raw RGBA frames from `videoEl` via an offscreen canvas.
 * Buffers at display rate (rAF) — no inference here, just pixel grabs.
 */
async function captureFrames(videoEl: HTMLVideoElement): Promise<ImageData[]> {
  const W = videoEl.videoWidth || 640;
  const H = videoEl.videoHeight || 480;
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  if (!ctx) return [];

  const frames: ImageData[] = [];
  const startMs = performance.now();
  return new Promise<ImageData[]>((resolve) => {
    const tick = () => {
      ctx.drawImage(videoEl, 0, 0, W, H);
      frames.push(ctx.getImageData(0, 0, W, H));
      if (performance.now() - startMs >= RECORD_MS) {
        resolve(frames);
        return;
      }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

/**
 * Hook owning the in-browser capture-a-rep lifecycle: fetches gloss_to_idx,
 * initializes the CV worker once, and drives countdown/record/evaluate cycles.
 * Degrades gracefully (notReady) when WebGPU is missing or the model fetch
 * fails, so the practice flow keeps working on its self-report fallback.
 */
export function useCaptureRep(): UseCaptureRepResult {
  const [ready, setReady] = useState(false);
  const [notReady, setNotReady] = useState(false);
  const [backend, setBackend] = useState<'webgpu' | 'wasm' | null>(null);
  const [phase, setPhase] = useState<CapturePhase>('idle');
  const [countdown, setCountdown] = useState(0);
  const [lastVerdict, setLastVerdict] = useState<RepVerdict | null>(null);

  // Guard against overlapping recordAttempt calls (worker is single-flight).
  const busyRef = useRef(false);
  const disposedRef = useRef(false);
  // Known model classes, for skipping CV on out-of-vocabulary signs.
  const glossSetRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    disposedRef.current = false;
    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch('/models/gloss_to_idx.json');
        if (!resp.ok) throw new Error(`gloss_to_idx fetch ${resp.status}`);
        const data = (await resp.json()) as {
          gloss_to_idx: Record<string, number>;
        };
        const glossToIdx = data.gloss_to_idx;
        const result = await initCaptureRep({ glossToIdx });
        if (cancelled) return;
        glossSetRef.current = new Set(Object.keys(glossToIdx));
        setBackend(result.backend);
        setReady(true);
      } catch (err) {
        if (cancelled) return;
        // eslint-disable-next-line no-console
        console.warn('[useCaptureRep] init failed; falling back to self-report:', err);
        setNotReady(true);
      }
    })();
    return () => {
      cancelled = true;
      disposedRef.current = true;
      disposeCaptureRep();
    };
  }, []);

  const recordAttempt = useCallback(
    async (
      videoEl: HTMLVideoElement,
      targetGloss: string
    ): Promise<RepVerdict | null> => {
      if (!ready || busyRef.current) return null;
      busyRef.current = true;
      try {
        // 3-2-1 countdown.
        setPhase('countdown');
        for (let s = COUNTDOWN_SEC; s > 0; s--) {
          setCountdown(s);
          await wait(1000);
          if (disposedRef.current) return null;
        }
        setCountdown(0);

        // ~5s record.
        setPhase('recording');
        const raw = await captureFrames(videoEl);
        if (disposedRef.current) return null;

        const frames = cullStaticFrames(raw, MAX_FRAMES);
        if (frames.length === 0) {
          return null;
        }

        // Evaluate.
        setPhase('evaluating');
        const verdict = await evaluateClip(frames, targetGloss);
        if (disposedRef.current) return null;
        setLastVerdict(verdict);
        return verdict;
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn('[useCaptureRep] recordAttempt failed:', err);
        return null;
      } finally {
        busyRef.current = false;
        if (!disposedRef.current) {
          setPhase('idle');
          setCountdown(0);
        }
      }
    },
    [ready]
  );

  const hasGloss = useCallback((gloss: string) => glossSetRef.current.has(gloss), []);

  const resetVerdict = useCallback(() => setLastVerdict(null), []);

  return {
    ready,
    notReady,
    backend,
    recording: phase !== 'idle',
    phase,
    countdown,
    lastVerdict,
    resetVerdict,
    hasGloss,
    recordAttempt,
  };
}
