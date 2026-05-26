/**
 * Themed progress bar built on the base-ui progress primitive, rendering a
 * deep-well track with a cyan-to-violet gradient fill indicator. It accepts
 * value and max plus optional class overrides for the root, track, and indicator.
 */
import * as React from 'react';
import { Progress as ProgressPrimitive } from '@base-ui/react/progress';
import { cn } from '@/lib/utils';

export interface ProgressProps
  extends Omit<React.ComponentProps<typeof ProgressPrimitive.Root>, 'value'> {
  value?: number | null;
  max?: number;
  className?: string;
  trackClassName?: string;
  indicatorClassName?: string;
}

export function Progress({
  value = 0,
  max = 100,
  className,
  trackClassName,
  indicatorClassName,
  ...props
}: ProgressProps) {
  return (
    <ProgressPrimitive.Root
      value={value}
      max={max}
      data-slot="progress"
      className={cn('w-full', className)}
      {...props}
    >
      <ProgressPrimitive.Track
        className={cn(
          'relative h-2 w-full overflow-hidden rounded-full border border-border bg-bg-deepest shadow-[inset_0_1px_2px_rgba(0,0,0,0.4)]',
          trackClassName
        )}
      >
        <ProgressPrimitive.Indicator
          className={cn(
            'h-full bg-gradient-to-r from-accent to-accent-hover shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] transition-[width] duration-300 ease-out',
            indicatorClassName
          )}
        />
      </ProgressPrimitive.Track>
    </ProgressPrimitive.Root>
  );
}
