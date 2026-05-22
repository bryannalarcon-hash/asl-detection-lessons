import { useEffect, useRef, useState } from 'react';
import { Play, RotateCcw, Repeat, Square } from 'lucide-react';
import { MOCK_REFERENCE_VIDEO_URL, FALLBACK_VIDEO_URL } from '@/lib/constants';
import { cn } from '@/lib/utils';
import type { DrillType } from '@/cv/types';

interface ReferenceVideoProps {
  signSlug: string;
  englishGloss: string;
  /** Which drill is currently active — drives the segment the video pauses at. */
  drillType?: DrillType;
  /** Pause the underlying <video> — used by the pause modal. */
  paused?: boolean;
  /** Display credit string for the floating caption (e.g. "Maya R."). */
  signerCredit?: string;
  className?: string;
}

const DRILL_LABEL: Record<DrillType, string> = {
  handshape: 'Handshape',
  movement: 'Movement',
  sign: 'Whole sign',
};

/**
 * Foundry · Aurora reference cell.
 *
 * 4:3 rounded card with:
 *  - Top-left floating caption: "REFERENCE · {drill}" + mono "{credit} · {rate}".
 *  - Bottom-left floating playback pill: loop, 0.5×, 1×, replay, play/pause.
 *  - 3-pill segment timeline overlay so the user can see segment progress.
 *
 * v1: all signs share a single nyan cat clip (see constants.MOCK_REFERENCE_VIDEO_URL).
 * Plays the segment for the current drill:
 *   - handshape drill: 0 → 1/3 of duration
 *   - movement drill:  1/3 → 2/3
 *   - sign drill:      0 → 1 (full clip)
 *
 * When the segment ends:
 *   - auto-loop ON  → seek back to segment start and keep playing
 *   - auto-loop OFF → pause at segment end
 *
 * The Replay button always restarts the current segment from its start.
 */
export function ReferenceVideo({
  signSlug,
  englishGloss,
  drillType = 'handshape',
  paused: pausedProp = false,
  signerCredit = 'Maya R.',
  className,
}: ReferenceVideoProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [src, setSrc] = useState(MOCK_REFERENCE_VIDEO_URL);
  const [slowMo, setSlowMo] = useState(false);
  const [autoLoop, setAutoLoop] = useState(true);
  const [duration, setDuration] = useState(0);
  const [paused, setPaused] = useState(true);
  // Re-render hook so the progress bar overlay updates smoothly.
  const [currentTime, setCurrentTime] = useState(0);

  const segment = segmentForDrill(drillType);
  const segStart = duration * segment.start;
  const segEnd = duration * segment.end;

  // Reset to segment start when drill changes
  useEffect(() => {
    const v = videoRef.current;
    if (!v || duration === 0) return;
    v.currentTime = segStart;
    v.play().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drillType, duration]);

  useEffect(() => {
    if (videoRef.current) videoRef.current.playbackRate = slowMo ? 0.5 : 1;
  }, [slowMo, src]);

  // Pause/resume when the parent toggles `pausedProp` (pause modal).
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    if (pausedProp) {
      v.pause();
    } else {
      v.play().catch(() => undefined);
    }
  }, [pausedProp]);

  const handleTimeUpdate = () => {
    const v = videoRef.current;
    if (!v) return;
    setCurrentTime(v.currentTime);
    if (v.currentTime >= segEnd && !v.paused) {
      if (autoLoop) {
        v.currentTime = segStart;
      } else {
        v.pause();
        setPaused(true);
      }
    }
  };

  const handleLoadedMetadata = () => {
    const v = videoRef.current;
    if (!v) return;
    setDuration(v.duration);
    v.currentTime = v.duration * segment.start;
    v.play().catch(() => undefined);
  };

  const togglePlay = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) {
      if (v.currentTime >= segEnd) v.currentTime = segStart;
      v.play().catch(() => undefined);
    } else {
      v.pause();
    }
  };

  const handleError = () => {
    if (src !== FALLBACK_VIDEO_URL) setSrc(FALLBACK_VIDEO_URL);
  };

  const progress = duration > 0 ? currentTime / duration : 0;
  const rateLabel = slowMo ? '0.5×' : '1×';

  return (
    <div
      data-testid="reference-panel"
      data-drill={drillType}
      className={cn(
        'relative aspect-[4/3] w-full overflow-hidden rounded-[12px] border border-border bg-bg-deep',
        'shadow-[0_1px_0_rgba(255,255,255,0.04)_inset,0_1px_2px_rgba(0,0,0,0.4)]',
        className
      )}
    >
      <video
        ref={videoRef}
        key={src}
        src={src}
        autoPlay
        muted
        playsInline
        onError={handleError}
        onLoadedMetadata={handleLoadedMetadata}
        onTimeUpdate={handleTimeUpdate}
        onPlay={() => setPaused(false)}
        onPause={() => setPaused(true)}
        data-testid="reference-video"
        className="h-full w-full object-cover"
      />

      {/* Top-left floating caption */}
      <div className="pointer-events-none absolute left-3 top-3 flex flex-col gap-0.5 rounded-md bg-bg-deep/65 px-2.5 py-1.5 backdrop-blur-md">
        <span className="font-mono text-[0.68rem] uppercase tracking-[0.14em] text-fg">
          Reference · {DRILL_LABEL[drillType]}
        </span>
        <span className="font-mono text-[0.7rem] text-fg-muted">
          {signerCredit} · {rateLabel}
        </span>
      </div>

      {/* Bottom-left floating playback pill */}
      <div
        data-testid="reference-controls"
        className="pointer-events-auto absolute bottom-3.5 left-3.5 flex items-center gap-1 rounded-full bg-bg-deep/70 p-1 backdrop-blur-md"
      >
        <button
          type="button"
          data-testid="reference-play"
          onClick={togglePlay}
          aria-label={paused ? 'Play reference' : 'Pause reference'}
          className="inline-flex h-7 w-7 items-center justify-center rounded-full text-fg-muted transition-colors hover:bg-bg-elev hover:text-fg"
        >
          {paused ? <Play className="h-3.5 w-3.5" /> : <Square className="h-3.5 w-3.5" />}
        </button>
        <button
          type="button"
          data-testid="reference-autoloop-toggle"
          data-state={autoLoop ? 'on' : 'off'}
          onClick={() => setAutoLoop((v) => !v)}
          aria-pressed={autoLoop}
          aria-label="Auto-loop segment"
          className={cn(
            'inline-flex h-7 w-7 items-center justify-center rounded-full transition-colors',
            autoLoop
              ? 'bg-accent/15 text-accent hover:bg-accent/25'
              : 'text-fg-muted hover:bg-bg-elev hover:text-fg'
          )}
        >
          <Repeat className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          data-testid="reference-replay"
          onClick={() => {
            const v = videoRef.current;
            if (!v) return;
            v.currentTime = segStart;
            v.play().catch(() => undefined);
          }}
          aria-label="Replay current segment"
          className="inline-flex h-7 w-7 items-center justify-center rounded-full text-fg-muted transition-colors hover:bg-bg-elev hover:text-fg"
        >
          <RotateCcw className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          data-testid="reference-slowmo-toggle"
          onClick={() => setSlowMo((v) => !v)}
          aria-pressed={slowMo}
          className={cn(
            'inline-flex h-7 items-center justify-center rounded-full px-2.5 font-mono text-[0.7rem] uppercase tracking-wider transition-colors',
            slowMo
              ? 'bg-accent/15 text-accent hover:bg-accent/25'
              : 'text-fg-muted hover:bg-bg-elev hover:text-fg'
          )}
        >
          0.5×
        </button>
        <button
          type="button"
          data-testid="reference-fullrate-toggle"
          onClick={() => setSlowMo(false)}
          aria-pressed={!slowMo}
          className={cn(
            'inline-flex h-7 items-center justify-center rounded-full px-2.5 font-mono text-[0.7rem] uppercase tracking-wider transition-colors',
            !slowMo
              ? 'bg-accent/15 text-accent hover:bg-accent/25'
              : 'text-fg-muted hover:bg-bg-elev hover:text-fg'
          )}
        >
          1×
        </button>
      </div>

      {/* Segment timeline overlay (bottom strip) */}
      <div className="pointer-events-none absolute inset-x-3.5 bottom-1.5 flex h-1 gap-1">
        {SEGMENTS.map((s) => {
          const isActive = segment.label === s.label;
          const fillFraction = clamp((progress - s.start) / (s.end - s.start), 0, 1);
          return (
            <div
              key={s.label}
              className={cn(
                'relative flex-1 overflow-hidden rounded-full border',
                isActive
                  ? 'border-accent/80 bg-bg-deep/80'
                  : 'border-border bg-bg-deep/40'
              )}
              style={{ flex: s.end - s.start }}
              aria-label={`${s.label} segment${isActive ? ' (active)' : ''}`}
            >
              <div
                className={cn(
                  'h-full transition-all',
                  isActive ? 'bg-accent' : 'bg-fg-faint'
                )}
                style={{ width: `${fillFraction * 100}%` }}
              />
            </div>
          );
        })}
      </div>

      <span className="sr-only" data-testid="reference-sign-slug">
        {signSlug} · {englishGloss}
      </span>
    </div>
  );
}

interface Segment {
  label: string;
  start: number;
  end: number;
}

const SEGMENTS: Segment[] = [
  { label: 'Handshape', start: 0, end: 1 / 3 },
  { label: 'Movement', start: 1 / 3, end: 2 / 3 },
  { label: 'Sign', start: 0, end: 1 },
];

function segmentForDrill(drill: DrillType): Segment {
  switch (drill) {
    case 'handshape':
      return SEGMENTS[0];
    case 'movement':
      return SEGMENTS[1];
    case 'sign':
    default:
      return SEGMENTS[2];
  }
}

function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}
