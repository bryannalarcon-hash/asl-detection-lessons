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
      {streak.freezesRemaining > 0 && (
        <span className="mt-2 font-mono text-[0.7rem] text-fg-muted">
          {streak.freezesRemaining} freeze{streak.freezesRemaining === 1 ? '' : 's'}{' '}
          available
        </span>
      )}
    </div>
  );
}
