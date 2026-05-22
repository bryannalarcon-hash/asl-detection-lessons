import { useEffect, useRef, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { BoundingBox, type BoxState } from './BoundingBox';
import { CameraDevToolbox } from './CameraDevToolbox';
import { useCameraPermission } from '@/hooks/useCameraPermission';
import { cn } from '@/lib/utils';

interface CameraPanelProps {
  boxState: BoxState;
  mirror?: boolean;
  /** When true, suspend the camera stream — used by the pause modal. */
  paused?: boolean;
  /** Live match score 0–1 from the CV layer. Drives the "±N% match" overlay. */
  matchScore?: number;
  /** Optional caption override; defaults to "live · on-device" / "paused". */
  captionMeta?: string;
  /** Optional floating overlay node (e.g. additional pills). */
  overlay?: ReactNode;
  className?: string;
}

/**
 * Foundry · Aurora camera cell.
 *
 * 4:3 rounded card with:
 *  - Top-left floating caption: eyebrow "YOUR CAMERA" + mono detail ("live · on-device").
 *  - Top-right floating pill: match score + pulsing live dot.
 *  - The BoundingBox covers the media area; permission states render inline
 *    (idle/requesting/denied/unsupported).
 *
 * Owns its own `useCameraPermission` instance and exposes the camera dev
 * toolbox via a floating overlay (preserves all four force-state buttons).
 */
export function CameraPanel({
  boxState,
  mirror = true,
  paused = false,
  matchScore,
  captionMeta,
  overlay,
  className,
}: CameraPanelProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const { state, request, stop, forceState } = useCameraPermission();

  // Auto-request once on mount when we have no opinion yet.
  useEffect(() => {
    if (state.kind === 'idle') {
      void request();
    }
    return () => {
      stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Wire the granted stream to the <video> element whenever it changes.
  useEffect(() => {
    if (state.kind !== 'granted') return;
    const v = videoRef.current;
    if (!v) return;
    if (v.srcObject !== state.stream) {
      v.srcObject = state.stream;
    }
    v.play().catch(() => undefined);
  }, [state]);

  // Pause/resume: disable tracks instead of stopping so we don't re-prompt
  // permission on resume.
  useEffect(() => {
    if (state.kind !== 'granted') return;
    state.stream.getVideoTracks().forEach((t) => {
      t.enabled = !paused;
    });
    const v = videoRef.current;
    if (!v) return;
    if (paused) v.pause();
    else v.play().catch(() => undefined);
  }, [paused, state]);

  const metaLine = captionMeta ?? (paused ? 'paused' : 'live · on-device');
  const matchPct = typeof matchScore === 'number'
    ? Math.round(Math.min(Math.max(matchScore, 0), 1) * 100)
    : null;

  return (
    <div
      data-testid="camera-panel"
      data-camera-state={state.kind}
      className={cn(
        'relative aspect-[4/3] w-full overflow-hidden rounded-[12px] border border-border bg-bg-deep',
        'shadow-[0_1px_0_rgba(255,255,255,0.04)_inset,0_1px_2px_rgba(0,0,0,0.4)]',
        className
      )}
    >
      <BoundingBox state={boxState} className="absolute inset-0">
        {state.kind === 'idle' || state.kind === 'requesting' ? (
          <div
            data-testid="camera-requesting"
            className="flex h-full w-full items-center justify-center bg-bg-deep p-6 text-center text-sm text-fg-muted"
          >
            <p>Requesting camera access…</p>
          </div>
        ) : state.kind === 'denied' ? (
          <div
            data-testid="camera-denied-inline"
            className="flex h-full w-full items-center justify-center bg-bg-deep p-6 text-center text-sm text-fg-muted"
          >
            <div className="space-y-2">
              <p>Camera access is blocked.</p>
              <div className="flex flex-wrap items-center justify-center gap-3">
                <button
                  type="button"
                  data-testid="camera-rerequest"
                  onClick={() => void request()}
                  className="inline-flex items-center justify-center rounded border border-accent/60 bg-accent/10 px-3 py-1 text-xs font-medium text-accent transition-colors hover:bg-accent/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1 focus-visible:ring-offset-bg"
                >
                  Re-request
                </button>
                <Link
                  to="/errors/camera-denied"
                  className="text-accent hover:underline"
                >
                  How to re-enable
                </Link>
              </div>
            </div>
          </div>
        ) : state.kind === 'unsupported' ? (
          <div
            data-testid="camera-unsupported"
            className="flex h-full w-full items-center justify-center bg-bg-deep p-6 text-center text-sm text-fg-muted"
          >
            <p className="max-w-sm">
              Camera not available on this device or browser. Try Chrome or Safari on a
              computer with a built-in or USB camera.
            </p>
          </div>
        ) : (
          <video
            ref={videoRef}
            autoPlay
            muted
            playsInline
            data-testid="camera-video"
            className={cn(
              'h-full w-full object-cover',
              mirror && '-scale-x-100' /* mirror display only */
            )}
          />
        )}
      </BoundingBox>

      {/* Top-left floating caption */}
      <div className="pointer-events-none absolute left-3 top-3 flex flex-col gap-0.5 rounded-md bg-bg-deep/65 px-2.5 py-1.5 backdrop-blur-md">
        <span className="font-mono text-[0.68rem] uppercase tracking-[0.14em] text-fg">
          Your camera
        </span>
        <span className="font-mono text-[0.7rem] text-fg-muted">
          {metaLine}
        </span>
      </div>

      {/* Top-right floating pill: match score + live dot */}
      {matchPct !== null && !paused && state.kind === 'granted' && (
        <div
          data-testid="camera-match-pill"
          className="pointer-events-none absolute right-3.5 top-3.5 flex items-center gap-2 rounded-full bg-bg-deep/70 px-3 py-1.5 text-[0.78rem] text-fg backdrop-blur-md"
        >
          <span className="font-mono">±{matchPct}% match</span>
          <span
            aria-hidden="true"
            className="inline-block h-2 w-2 rounded-full bg-success shadow-[0_0_0_4px_rgba(52,211,153,0.25)] motion-safe:animate-pulse"
          />
        </div>
      )}

      {/* Floating dev camera toolbox (top-right when no overlay competes) */}
      <div className="pointer-events-auto absolute bottom-3 right-3 z-10">
        <CameraDevToolbox forceState={forceState} />
      </div>

      {overlay && (
        <div className="pointer-events-auto absolute inset-0 z-20">{overlay}</div>
      )}
    </div>
  );
}
