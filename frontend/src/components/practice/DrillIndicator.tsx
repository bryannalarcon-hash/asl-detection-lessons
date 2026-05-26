/**
 * Three-stage pill tab row showing progress through a sign's drills (handshape,
 * movement, whole-sign). Each pill is styled as done, active, or upcoming based
 * on its position relative to the current drill, with a checkmark on completed stages.
 */
import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { DrillType } from '@/cv/types';

interface DrillIndicatorProps {
  current: DrillType;
  /** Drill types present for the current sign, in order. */
  drills: DrillType[];
}

const LABEL: Record<DrillType, string> = {
  handshape: 'Handshape',
  movement: 'Movement',
  sign: 'Whole sign',
};

/**
 * Foundry · Aurora 3-stage pill tabs for the practice drill progress.
 *
 * Visual model (per design/extracted/design_handoff_asl_pilot/README.md
 * §"Hero screen detail — Practice"):
 *  - Each stage is a pill card with `[01] [label] [tick]`.
 *  - Active pill: `--accent-bg` background + accent border + accent text.
 *  - Done pill: hairline border + ✓ in success-green + standard fg.
 *  - Upcoming pill: paper background, soft border, muted text.
 *  - Mobile (<600px): pills collapse to a single column.
 */
export function DrillIndicator({ current, drills }: DrillIndicatorProps) {
  const currentIdx = drills.indexOf(current);

  return (
    <div
      className="grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-3.5"
      data-testid="drill-indicator"
      role="list"
      aria-label="Drill progress"
    >
      {drills.map((drill, idx) => {
        const isCurrent = idx === currentIdx;
        const isPast = idx < currentIdx;
        const isFuture = idx > currentIdx;

        return (
          <div
            key={`${drill}-${idx}`}
            role="listitem"
            data-testid={`drill-tab-${drill}`}
            data-state={isPast ? 'done' : isCurrent ? 'active' : 'upcoming'}
            className={cn(
              'grid items-center gap-3 rounded-md border px-4 py-3 font-mono transition-colors duration-150',
              'grid-cols-[auto_1fr_auto]',
              isCurrent &&
                'border-accent bg-accent/12 text-accent shadow-[0_1px_0_rgba(255,255,255,0.04)_inset]',
              isPast &&
                'border-success/40 bg-bg-paper text-fg',
              isFuture &&
                'border-border bg-bg-paper text-fg-muted'
            )}
          >
            {/* Number — leading zero, mono, faint on upcoming */}
            <span
              data-testid={`drill-dot-${drill}`}
              data-active={isCurrent ? 'true' : undefined}
              data-state={isPast ? 'past' : isCurrent ? 'current' : 'future'}
              aria-current={isCurrent ? 'step' : undefined}
              className={cn(
                'font-mono text-[0.78rem] leading-none tracking-wider',
                isCurrent && 'text-accent',
                isPast && 'text-fg-muted',
                isFuture && 'text-fg-faint'
              )}
            >
              {String(idx + 1).padStart(2, '0')}
            </span>

            {/* Label */}
            <span
              className={cn(
                'truncate text-[0.96rem] font-medium leading-none',
                isCurrent && 'text-accent',
                isPast && 'text-fg',
                isFuture && 'text-fg-muted'
              )}
            >
              {LABEL[drill]}
            </span>

            {/* Right-side glyph: done ✓, upcoming/active blank slot */}
            <span className="flex h-4 w-4 items-center justify-center">
              {isPast ? (
                <Check className="h-4 w-4 text-success" strokeWidth={3} aria-hidden="true" />
              ) : null}
            </span>
          </div>
        );
      })}
    </div>
  );
}
