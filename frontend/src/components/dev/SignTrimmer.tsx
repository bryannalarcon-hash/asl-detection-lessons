import { useEffect, useRef, useState } from 'react';
import { MOCK_REFERENCE_VIDEO_URL } from '@/lib/constants';
import {
  type SignConfig,
  type StageConfig,
  type StageSegment,
  type StageType,
  STAGE_ORDER,
  STAGE_LABEL,
  videoSrcForSign,
} from '@/lib/lesson-config';

interface SignTrimmerProps {
  value: SignConfig;
  index: number;
  signOptions: string[];
  onChange: (next: SignConfig) => void;
  onRemove: () => void;
}

/**
 * Per-sign trim card for the dev Lesson Config editor.
 *
 * Embeds the sign's reference clip (falling back to the mock clip when the
 * per-sign clip is missing) plus a scrubber, and one row per stage
 * (handshape / movement / whole-sign). Each stage row sets its own trim
 * [start, end] and reps, can capture the current playhead into start/end, and
 * can Preview — which loops the clip within just that stage's range so the dev
 * can see exactly what the student will see during that stage.
 */
export function SignTrimmer({
  value,
  index,
  signOptions,
  onChange,
  onRemove,
}: SignTrimmerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [src, setSrc] = useState(value.videoSrc || videoSrcForSign(value.sign));
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [previewStage, setPreviewStage] = useState<StageType | null>(null);

  useEffect(() => {
    setSrc(value.videoSrc || videoSrcForSign(value.sign));
  }, [value.videoSrc, value.sign]);

  const range = previewRange(previewStage, value, duration);

  // Seek to the active preview range's start when preview changes.
  useEffect(() => {
    const v = videoRef.current;
    if (!v || !range) return;
    v.currentTime = range.start;
    v.play().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewStage, duration]);

  const handleTimeUpdate = () => {
    const v = videoRef.current;
    if (!v) return;
    setCurrentTime(v.currentTime);
    if (range && v.currentTime >= range.end && !v.paused) {
      v.currentTime = range.start; // loop within the previewed stage range
    }
  };

  const handleError = () => {
    if (src !== MOCK_REFERENCE_VIDEO_URL) setSrc(MOCK_REFERENCE_VIDEO_URL);
  };

  const setStage = (stage: StageType, patch: Partial<StageConfig>) => {
    onChange({
      ...value,
      stages: {
        ...value.stages,
        [stage]: { ...value.stages[stage], ...patch },
      },
    });
  };

  const setSeg = (stage: StageType, patch: Partial<StageSegment>) =>
    setStage(stage, { segment: { ...value.stages[stage].segment, ...patch } });

  const seek = (t: number) => {
    const v = videoRef.current;
    if (!v) return;
    setPreviewStage(null);
    v.currentTime = clamp(t, 0, duration || t);
    setCurrentTime(v.currentTime);
  };

  return (
    <li
      data-testid="dev-sign-config"
      className="rounded-md border border-status-warn/40 bg-status-warn/5 p-3"
    >
      <div className="mb-2 flex items-center justify-between">
        <span className="font-mono text-[0.7rem] uppercase tracking-wider text-fg-muted">
          Sign {String(index + 1).padStart(2, '0')}
        </span>
        <button
          type="button"
          data-testid="dev-sign-remove"
          onClick={onRemove}
          className="font-mono text-[0.7rem] text-status-warn hover:underline"
        >
          Remove
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-[1fr_1.1fr]">
        {/* Left: sign select + video preview + scrubber */}
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1">
            <span className="font-mono text-[0.65rem] uppercase tracking-wider text-fg-subtle">
              Sign
            </span>
            <select
              data-testid="dev-sign-select"
              value={value.sign}
              onChange={(e) =>
                onChange({
                  ...value,
                  sign: e.target.value,
                  videoSrc: videoSrcForSign(e.target.value),
                })
              }
              className="rounded border border-border bg-bg-paper px-2 py-1 font-mono text-sm text-fg"
            >
              {!signOptions.includes(value.sign) && (
                <option value={value.sign}>{value.sign}</option>
              )}
              {signOptions.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>

          <video
            ref={videoRef}
            key={src}
            src={src}
            muted
            playsInline
            onError={handleError}
            onLoadedMetadata={(e) => setDuration(e.currentTarget.duration || 0)}
            onTimeUpdate={handleTimeUpdate}
            data-testid="dev-sign-video"
            className="aspect-[4/3] w-full rounded border border-border bg-bg-deep object-cover"
          />

          <input
            type="range"
            min={0}
            max={duration || 0}
            step={0.05}
            value={Math.min(currentTime, duration || 0)}
            onChange={(e) => seek(Number(e.target.value))}
            data-testid="dev-sign-scrub"
            aria-label="Scrub reference clip"
            className="w-full accent-accent"
          />
          <p className="font-mono text-[0.65rem] text-fg-subtle">
            {currentTime.toFixed(2)}s / {duration.toFixed(2)}s · {value.videoSrc}
          </p>
        </div>

        {/* Right: per-stage trim + reps */}
        <ul className="flex flex-col gap-2">
          {STAGE_ORDER.map((stage) => {
            const cfg = value.stages[stage];
            return (
              <li
                key={stage}
                data-testid={`dev-stage-${stage}`}
                className="rounded border border-border bg-bg-paper/60 p-2"
              >
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="font-mono text-[0.66rem] uppercase tracking-wider text-fg">
                    {STAGE_LABEL[stage]}
                  </span>
                  <button
                    type="button"
                    data-testid={`dev-stage-preview-${stage}`}
                    data-state={previewStage === stage ? 'on' : 'off'}
                    onClick={() =>
                      setPreviewStage((p) => (p === stage ? null : stage))
                    }
                    className={
                      previewStage === stage
                        ? 'rounded bg-accent/20 px-2 py-0.5 font-mono text-[0.62rem] uppercase tracking-wider text-accent'
                        : 'rounded border border-border px-2 py-0.5 font-mono text-[0.62rem] uppercase tracking-wider text-fg-muted hover:text-fg'
                    }
                  >
                    {previewStage === stage ? 'Previewing' : 'Preview'}
                  </button>
                </div>

                <div className="grid grid-cols-3 gap-1.5">
                  <label className="flex flex-col gap-0.5">
                    <span className="font-mono text-[0.58rem] uppercase tracking-wider text-fg-subtle">
                      Start s
                    </span>
                    <input
                      type="number"
                      min={0}
                      step={0.05}
                      data-testid={`dev-stage-start-${stage}`}
                      value={cfg.segment.startSec}
                      onChange={(e) =>
                        setSeg(stage, { startSec: Number(e.target.value) })
                      }
                      className="rounded border border-border bg-bg-paper px-1.5 py-1 font-mono text-xs text-fg"
                    />
                  </label>
                  <label className="flex flex-col gap-0.5">
                    <span className="font-mono text-[0.58rem] uppercase tracking-wider text-fg-subtle">
                      End s
                    </span>
                    <input
                      type="number"
                      min={0}
                      step={0.05}
                      data-testid={`dev-stage-end-${stage}`}
                      value={cfg.segment.endSec}
                      onChange={(e) =>
                        setSeg(stage, { endSec: Number(e.target.value) })
                      }
                      className="rounded border border-border bg-bg-paper px-1.5 py-1 font-mono text-xs text-fg"
                    />
                  </label>
                  <label className="flex flex-col gap-0.5">
                    <span className="font-mono text-[0.58rem] uppercase tracking-wider text-fg-subtle">
                      Reps
                    </span>
                    <input
                      type="number"
                      min={1}
                      data-testid={`dev-stage-reps-${stage}`}
                      value={cfg.reps}
                      onChange={(e) =>
                        setStage(stage, { reps: Number(e.target.value) })
                      }
                      className="rounded border border-border bg-bg-paper px-1.5 py-1 font-mono text-xs text-fg"
                    />
                  </label>
                </div>

                <div className="mt-1.5 flex gap-1.5">
                  <button
                    type="button"
                    data-testid={`dev-stage-set-start-${stage}`}
                    onClick={() => setSeg(stage, { startSec: round2(currentTime) })}
                    className="rounded border border-border px-1.5 py-0.5 font-mono text-[0.6rem] text-fg-muted hover:text-fg"
                  >
                    Set start = now
                  </button>
                  <button
                    type="button"
                    data-testid={`dev-stage-set-end-${stage}`}
                    onClick={() => setSeg(stage, { endSec: round2(currentTime) })}
                    className="rounded border border-border px-1.5 py-0.5 font-mono text-[0.6rem] text-fg-muted hover:text-fg"
                  >
                    Set end = now
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </li>
  );
}

function previewRange(
  stage: StageType | null,
  value: SignConfig,
  duration: number
): { start: number; end: number } | null {
  if (!stage) return null;
  const seg = value.stages[stage].segment;
  const start = clamp(seg.startSec, 0, duration || seg.startSec);
  const end =
    seg.endSec > seg.startSec
      ? clamp(seg.endSec, start, duration || seg.endSec)
      : duration || start;
  return { start, end };
}

function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}

function round2(n: number) {
  return Math.round(n * 100) / 100;
}
