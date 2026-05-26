import { cn } from '@/lib/utils';
import type { CapturePhase } from '@/hooks/useCaptureRep';

interface RecordAttemptRowProps {
  phase: CapturePhase;
  countdown: number;
  /** Disabled when CV not ready, mid-capture, or no video element yet. */
  disabled: boolean;
  /** Set after a failed attempt to nudge the learner. */
  showRetry: boolean;
  onRecord: () => void;
}

function labelForPhase(phase: CapturePhase, countdown: number): string {
  switch (phase) {
    case 'countdown':
      return `Get ready… ${countdown}`;
    case 'recording':
      return 'Recording…';
    case 'evaluating':
      return 'Evaluating…';
    default:
      return 'Record attempt';
  }
}

/**
 * In-browser CV affordance: records a ~3s clip and runs the on-device cascade
 * to verify the sign. Sits alongside SelfReportRow, which remains the manual
 * fallback. Only rendered when the capture hook is ready.
 */
export function RecordAttemptRow({
  phase,
  countdown,
  disabled,
  showRetry,
  onRecord,
}: RecordAttemptRowProps) {
  return (
    <div
      data-testid="record-attempt-row"
      className="flex w-full flex-wrap items-center justify-center gap-3"
    >
      <button
        type="button"
        data-testid="record-attempt"
        disabled={disabled}
        onClick={onRecord}
        className={cn(
          'inline-flex items-center justify-center gap-2 rounded-full border border-accent-soft bg-bg-elev px-6 py-2.5 text-sm font-medium text-fg',
          'transition-[background-color,border-color,color,transform] duration-150 ease-out',
          'hover:border-accent hover:bg-accent/10',
          'active:translate-y-px',
          'focus-visible:outline-2 focus-visible:outline-accent-ring focus-visible:outline-offset-2',
          'disabled:pointer-events-none disabled:opacity-40'
        )}
      >
        {labelForPhase(phase, countdown)}
      </button>
      {showRetry && phase === 'idle' && (
        <p
          data-testid="record-attempt-retry"
          className="font-mono text-[0.76rem] text-fg-subtle"
        >
          No match yet — try again.
        </p>
      )}
    </div>
  );
}
