/**
 * Hook owning the camera-permission lifecycle as a state machine (idle,
 * requesting, granted, denied, unsupported), managing getUserMedia and stream
 * teardown per consumer instance. It supports dev-only forced states with a
 * synthetic canvas stream and auto-recovers via the Permissions API after a reset.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { isDevToolsEnabled } from '@/lib/env';

/**
 * Why a request landed in `unsupported`. Drives per-cause messaging + retry:
 *
 * - `in-use`            camera held by another app/tab (NotReadableError /
 *                       AbortError) — retryable once the other user releases it
 * - `insecure-context`  page served over http:// — browsers hide the camera
 *                       API entirely outside secure contexts
 * - `no-device`         no camera attached (NotFoundError)
 * - `no-api`            mediaDevices missing despite a secure context
 * - `unknown`           anything else
 */
export type UnsupportedReason =
  | 'in-use'
  | 'insecure-context'
  | 'no-device'
  | 'no-api'
  | 'unknown';

/**
 * Terminal-ish states for the camera-permission state machine.
 *
 * - `idle`        not yet requested in this mount
 * - `requesting`  `getUserMedia` is in flight
 * - `granted`     stream is live (real or dev-forced fake stream)
 * - `denied`      user/browser refused (`NotAllowedError`)
 * - `unsupported` no API, no device, or any other unrecoverable error;
 *                 `reason` says which so the UI can offer a useful next step
 */
export type CameraState =
  | { kind: 'idle' }
  | { kind: 'requesting' }
  | { kind: 'granted'; stream: MediaStream }
  | { kind: 'denied' }
  | { kind: 'unsupported'; reason: UnsupportedReason };

interface UseCameraPermissionOptions {
  /** Override the default `{video:{640x480}, audio:false}` constraints. */
  constraints?: MediaStreamConstraints;
}

export interface UseCameraPermissionResult {
  state: CameraState;
  /** Kick off a real `getUserMedia` request. No-op if already granted/requesting. */
  request(): Promise<void>;
  /** Stop any active stream (real or fake) and return to `idle`. */
  stop(): void;
  /**
   * Dev-only override for testing each terminal UI state without browser
   * permission gestures. Gated by `isDevToolsEnabled()` — no-op + console.warn
   * when dev tools are off.
   */
  forceState(s: 'granted' | 'denied' | 'unsupported' | 'reset'): void;
}

const DEFAULT_CONSTRAINTS: MediaStreamConstraints = {
  video: { width: 640, height: 480 },
  audio: false,
};

/**
 * Build a synthetic `MediaStream` for dev-mode "Force allow" testing.
 * Draws an animated gradient + timestamp onto a hidden 640x480 canvas and
 * exposes `canvas.captureStream(30)`. Returns both the stream and a cleanup
 * function that cancels the rAF loop.
 *
 * Falls back to `null` if the browser doesn't support `captureStream` (very
 * old browsers / non-DOM test envs).
 */
function buildFakeStream(): { stream: MediaStream; cleanup: () => void } | null {
  if (typeof document === 'undefined') return null;
  const canvas = document.createElement('canvas');
  canvas.width = 640;
  canvas.height = 480;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  // captureStream is on HTMLCanvasElement but not in every lib.dom version
  const capture = (canvas as HTMLCanvasElement & {
    captureStream?: (fps?: number) => MediaStream;
  }).captureStream;
  if (typeof capture !== 'function') return null;

  let rafId: number | null = null;
  let stopped = false;

  const draw = (t: number) => {
    if (stopped) return;
    const hue = (t / 30) % 360;
    const grad = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
    grad.addColorStop(0, `hsl(${hue}, 70%, 18%)`);
    grad.addColorStop(1, `hsl(${(hue + 60) % 360}, 60%, 35%)`);
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Moving dot so the change is obvious even on dim displays.
    const cx = canvas.width / 2 + Math.cos(t / 600) * 180;
    const cy = canvas.height / 2 + Math.sin(t / 800) * 120;
    ctx.fillStyle = 'rgba(255,255,255,0.85)';
    ctx.beginPath();
    ctx.arc(cx, cy, 18, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = 'rgba(255,255,255,0.95)';
    ctx.font = '20px system-ui, sans-serif';
    ctx.fillText('[Dev: fake camera stream]', 24, 36);
    ctx.font = '14px ui-monospace, monospace';
    ctx.fillText(new Date().toISOString(), 24, 60);

    rafId = requestAnimationFrame(draw);
  };
  rafId = requestAnimationFrame(draw);

  const stream = capture.call(canvas, 30);
  const cleanup = () => {
    stopped = true;
    if (rafId != null) cancelAnimationFrame(rafId);
    rafId = null;
    stream.getTracks().forEach((t) => t.stop());
  };
  return { stream, cleanup };
}

/**
 * Hook owning the camera permission lifecycle. One instance per consumer; the
 * hook never reaches into global state. All streams (real or fake) are cleaned
 * up on unmount.
 */
export function useCameraPermission(
  opts: UseCameraPermissionOptions = {}
): UseCameraPermissionResult {
  const [state, setState] = useState<CameraState>({ kind: 'idle' });
  const streamRef = useRef<MediaStream | null>(null);
  const fakeCleanupRef = useRef<(() => void) | null>(null);
  const cancelledRef = useRef(false);
  const inFlightRef = useRef(false);
  const constraints = opts.constraints ?? DEFAULT_CONSTRAINTS;

  // Internal: tear down whatever stream we hold (real or fake). Idempotent.
  const teardownStream = useCallback(() => {
    if (fakeCleanupRef.current) {
      fakeCleanupRef.current();
      fakeCleanupRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }, []);

  const request = useCallback(async () => {
    if (inFlightRef.current) return;
    if (streamRef.current) return; // already granted
    inFlightRef.current = true;
    setState({ kind: 'requesting' });

    if (!navigator.mediaDevices?.getUserMedia) {
      inFlightRef.current = false;
      if (!cancelledRef.current) {
        // Browsers expose mediaDevices only in secure contexts, so a missing
        // API on plain http:// means the page needs HTTPS, not new hardware.
        const insecure =
          typeof window !== 'undefined' && window.isSecureContext === false;
        setState({
          kind: 'unsupported',
          reason: insecure ? 'insecure-context' : 'no-api',
        });
      }
      return;
    }

    try {
      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia(constraints);
      } catch (firstErr: unknown) {
        const firstName = (firstErr as { name?: string })?.name ?? '';
        // Sized constraints can overconstrain some cameras even though bare
        // `{video: true}` works — fall back before giving up.
        if (
          firstName === 'OverconstrainedError' ||
          firstName === 'ConstraintNotSatisfiedError'
        ) {
          stream = await navigator.mediaDevices.getUserMedia({
            video: true,
            audio: false,
          });
        } else {
          throw firstErr;
        }
      }
      if (cancelledRef.current) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      streamRef.current = stream;
      setState({ kind: 'granted', stream });
    } catch (err: unknown) {
      const name = (err as { name?: string })?.name ?? '';
      if (cancelledRef.current) return;
      if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
        setState({ kind: 'denied' });
      } else if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
        setState({ kind: 'unsupported', reason: 'no-device' });
      } else if (
        name === 'NotReadableError' ||
        name === 'TrackStartError' ||
        name === 'AbortError'
      ) {
        // The device exists but couldn't start — almost always another
        // app/tab holding the camera. Retryable once it's released.
        // eslint-disable-next-line no-console
        console.warn('[useCameraPermission] camera busy:', err);
        setState({ kind: 'unsupported', reason: 'in-use' });
      } else {
        // eslint-disable-next-line no-console
        console.warn('[useCameraPermission] getUserMedia failed:', err);
        setState({ kind: 'unsupported', reason: 'unknown' });
      }
    } finally {
      inFlightRef.current = false;
    }
  }, [constraints]);

  const stop = useCallback(() => {
    teardownStream();
    setState({ kind: 'idle' });
  }, [teardownStream]);

  const forceState = useCallback(
    (s: 'granted' | 'denied' | 'unsupported' | 'reset') => {
      if (!isDevToolsEnabled()) {
        // eslint-disable-next-line no-console
        console.warn(
          '[useCameraPermission] forceState() ignored: dev tools disabled.'
        );
        return;
      }
      // Always drop any existing stream before applying a new forced state, so
      // we don't leak the previous fake/real stream.
      teardownStream();

      if (s === 'reset') {
        setState({ kind: 'idle' });
        return;
      }
      if (s === 'denied') {
        setState({ kind: 'denied' });
        return;
      }
      if (s === 'unsupported') {
        setState({ kind: 'unsupported', reason: 'unknown' });
        return;
      }
      // 'granted' → synthesize a fake stream.
      const built = buildFakeStream();
      if (!built) {
        // eslint-disable-next-line no-console
        console.warn(
          '[useCameraPermission] forceState("granted") unavailable: canvas.captureStream not supported.'
        );
        setState({ kind: 'unsupported', reason: 'no-api' });
        return;
      }
      streamRef.current = built.stream;
      fakeCleanupRef.current = built.cleanup;
      setState({ kind: 'granted', stream: built.stream });
    },
    [teardownStream]
  );

  // Unmount cleanup. We deliberately do NOT clean up on `state` changes — the
  // stream lifecycle is owned explicitly by request/stop/forceState/unmount.
  useEffect(() => {
    cancelledRef.current = false;
    return () => {
      cancelledRef.current = true;
      teardownStream();
    };
  }, [teardownStream]);

  // Auto-recover after the user resets a previously-denied camera permission.
  // Browsers won't re-prompt a denied site, and the app would otherwise sit in
  // `denied` forever (no reload needed otherwise). Listen to the Permissions
  // API: when camera flips back to granted/prompt and we hold no stream, kick
  // off a fresh request so the camera comes back on its own. Feature-detected;
  // a no-op where the camera permission can't be queried.
  useEffect(() => {
    const perms = navigator.permissions;
    if (!perms?.query) return;
    let status: PermissionStatus | null = null;
    let active = true;
    perms
      .query({ name: 'camera' as PermissionName })
      .then((s) => {
        if (!active) return;
        status = s;
        s.onchange = () => {
          if ((s.state === 'granted' || s.state === 'prompt') && !streamRef.current) {
            void request();
          }
        };
      })
      .catch(() => undefined);
    return () => {
      active = false;
      if (status) status.onchange = null;
    };
  }, [request]);

  return { state, request, stop, forceState };
}
