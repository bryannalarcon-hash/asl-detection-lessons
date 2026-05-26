/**
 * Course-progress card showing how many signs are in progress out of the total
 * as a gradient-filled progress bar. It surfaces the "X / 75" metric used by
 * the dashboard's overall course-progress badge.
 */
import { Progress } from '@/components/ui/progress';
import { Eyebrow } from '@/components/ui/eyebrow';
import { TOTAL_SIGNS } from '@/lib/constants';

interface MasteryBarProps {
  /** Touched signs (any non-zero mastery level). Per PRD this is the number
   *  the "X / 75" course-progress badge surfaces. */
  mastered: number;
  total?: number;
}

/**
 * Foundry · Aurora course-progress card. Track is the deep-well; the fill
 * uses the cyan→violet gradient owned by the Progress primitive. The
 * "X / 75 signs in progress" copy keeps the legacy testid for tests.
 */
export function MasteryBar({ mastered, total = TOTAL_SIGNS }: MasteryBarProps) {
  const pct = total > 0 ? (mastered / total) * 100 : 0;
  return (
    <div className="space-y-3" data-testid="mastery-progress-container">
      <div className="flex items-baseline justify-between">
        <Eyebrow>Course progress</Eyebrow>
        <span data-testid="mastery-progress" className="font-mono text-sm text-fg">
          <span className="text-fg">{mastered}</span>{' '}
          <span className="text-fg-muted">/ {total} signs in progress</span>
        </span>
      </div>
      <Progress
        value={pct}
        max={100}
        aria-label={`Course progress: ${mastered} of ${total} signs in progress`}
        trackClassName="h-3 bg-bg-deep"
      />
    </div>
  );
}
