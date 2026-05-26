/**
 * Right-aligned dashboard indicator that displays the current practice streak
 * as a large gradient day count. It also shows a pill noting how many streak
 * freezes remain.
 */
import type { StreakStateDto } from '@/lib/api';
import { Eyebrow } from '@/components/ui/eyebrow';

interface StreakIndicatorProps {
  streak: StreakStateDto;
}

/**
 * Foundry · Aurora streak indicator.
 *
 * Right-aligned column with eyebrow "STREAK" + a large gradient-text day
 * count + a small mono footnote noting how many freezes are available.
 * No frame; the gradient number is the focal point.
 */
export function StreakIndicator({ streak }: StreakIndicatorProps) {
  const days = streak.currentStreakDays;
  return (
    <div
      data-testid="streak-indicator"
      className="flex flex-col items-end text-right"
      aria-label={`Day ${days} streak`}
    >
      <Eyebrow>Streak</Eyebrow>
      <div className="mt-1 flex items-baseline gap-2 font-display leading-none">
        <span className="gradient-text text-5xl font-extrabold tabular-nums">
          {String(days).padStart(2, '0')}
        </span>
        <span className="font-mono text-xs lowercase tracking-wider text-fg-muted">
          {days === 1 ? 'day' : 'days'}
        </span>
      </div>
      <div
        data-testid="streak-freezes"
        className="mt-3 inline-flex items-center gap-2 rounded-full border border-line/40 bg-bg-paper px-2.5 py-1 font-mono text-[0.7rem] uppercase tracking-wider"
      >
        <span aria-hidden="true" className="text-accent-soft">
          ❄
        </span>
        <span className="text-fg">{streak.freezesRemaining}</span>
        <span className="text-fg-muted">
          freeze{streak.freezesRemaining === 1 ? '' : 's'}
        </span>
      </div>
    </div>
  );
}
