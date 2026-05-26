import { useEffect, useRef } from 'react';
import { isDevToolsEnabled } from '@/lib/env';
import type { CaptureClip } from '@/hooks/useCaptureRep';

// Dev-only: replays the in-memory frames of the learner's most recent capture
// (the exact pixels the cascade saw) on a looping canvas, so you can see what
// the model was actually given. Mirrored to match the live camera preview.
// Stripped from prod via isDevToolsEnabled().

interface DevClipReplayProps {
  clip: CaptureClip | null;
  open: boolean;
  onClose: () => void;
}

const FRAME_MS = 60; // ~16fps loop playback

export function DevClipReplay({ clip, open, onClose }: DevClipReplayProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (!open || !clip || clip.frames.length === 0) return;
    const c = canvasRef.current;
    if (!c) return;
    c.width = clip.width;
    c.height = clip.height;
    const ctx = c.getContext('2d');
    if (!ctx) return;
    let i = 0;
    let raf = 0;
    let last = 0;
    const tick = (t: number) => {
      if (t - last >= FRAME_MS) {
        ctx.putImageData(clip.frames[i], 0, 0);
        i = (i + 1) % clip.frames.length;
        last = t;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [open, clip]);

  if (!isDevToolsEnabled() || !open || !clip) return null;

  return (
    <div
      role="dialog"
      aria-label="Dev capture replay"
      data-testid="dev-clip-replay"
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="rounded-card border border-status-warn/50 bg-bg-elevated p-4"
      >
        <p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-status-warn">
          [Dev] your capture · {clip.target} ·{' '}
          <span className={clip.passed ? 'text-status-ok' : 'text-status-err'}>
            {clip.passed ? 'PASS' : 'FAIL'}
          </span>{' '}
          · {clip.frames.length} frames
        </p>
        <canvas
          ref={canvasRef}
          className="max-h-[70vh] max-w-[80vw] -scale-x-100 rounded bg-black"
        />
        <div className="mt-2 text-right">
          <button
            type="button"
            data-testid="dev-clip-replay-close"
            onClick={onClose}
            className="rounded-md border border-status-warn/60 bg-status-warn/5 px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-status-warn transition-colors hover:bg-status-warn/10"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
