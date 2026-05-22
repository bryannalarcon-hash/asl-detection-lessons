import { progressApi } from '@/lib/api';
import type { DrillType } from '@/cv/types';
import { cn } from '@/lib/utils';

interface SelfReportRowProps {
  signId: string;
  drillType: DrillType;
  onPass: () => void;
  onSkip: () => void;
  source?: 'self-report' | 'dev';
  disabled?: boolean;
  /** Label override for the primary Continue button (e.g. "Next rep (2 of 3) →"). */
  continueLabel?: string;
  /** Label override for the secondary skip button. */
  skipLabel?: string;
}

/**
 * Foundry · Aurora CTA row: ghost "Skip this sign →" on the left, primary
 * gradient "Continue →" on the right. The user advances either by clicking
 * Continue OR by the CV detecting success (bounding box turns green) —
 * see Practice.tsx auto-advance effect.
 *
 * The buttons preserve their original testids (`self-report-got-it`,
 * `self-report-skip`) and the FAIL/SKIP machine event wiring.
 */
export function SelfReportRow({
  signId,
  drillType,
  onPass,
  onSkip,
  source = 'self-report',
  disabled,
  continueLabel = 'Continue →',
  skipLabel = 'Skip this sign →',
}: SelfReportRowProps) {
  const submit = (outcome: 'pass' | 'skip', cb: () => void) => {
    void progressApi
      .rep({ signId, drillType, outcome, source, hintRequested: false })
      .catch(() => undefined);
    cb();
  };

  return (
    <div
      data-testid="self-report-row"
      className="flex w-full flex-wrap items-center justify-between gap-3"
      role="group"
      aria-label="Continue or skip"
    >
      <button
        type="button"
        data-testid="self-report-skip"
        disabled={disabled}
        onClick={() => submit('skip', onSkip)}
        className={cn(
          'inline-flex items-center justify-center gap-2 rounded-md border border-border bg-transparent px-4 py-2.5 text-sm font-medium text-fg-muted',
          'transition-[background-color,border-color,color,transform] duration-150 ease-out',
          'hover:border-accent-soft hover:bg-bg-elev hover:text-fg',
          'active:translate-y-px',
          'focus-visible:outline-2 focus-visible:outline-accent-ring focus-visible:outline-offset-2',
          'disabled:pointer-events-none disabled:opacity-40'
        )}
      >
        {skipLabel}
      </button>
      <button
        type="button"
        data-testid="self-report-got-it"
        disabled={disabled}
        onClick={() => submit('pass', onPass)}
        className={cn(
          'btn-aurora-primary inline-flex items-center justify-center gap-2 rounded-full px-6 py-3 text-sm',
          'transition-[filter,transform] duration-150 ease-out',
          'hover:[filter:brightness(1.08)]',
          'active:translate-y-px',
          'focus-visible:outline-2 focus-visible:outline-accent-ring focus-visible:outline-offset-2',
          'disabled:pointer-events-none disabled:opacity-40'
        )}
      >
        {continueLabel}
      </button>
    </div>
  );
}
