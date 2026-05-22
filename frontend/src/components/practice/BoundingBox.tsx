import { cn } from '@/lib/utils';
import type { ReactNode } from 'react';

export type BoxState = 'gray' | 'orange' | 'green';

interface BoundingBoxProps {
  state: BoxState;
  children?: ReactNode;
  className?: string;
}

/**
 * Bounding box overlay around the camera frame. Three colors per
 * ux-spec §"Bounding box semantics":
 *   - gray = no hands
 *   - orange = hands detected (recording)
 *   - green = target met (purely visual in v1; advance is from self-report)
 */
export function BoundingBox({ state, children, className }: BoundingBoxProps) {
  // Inset well by default (research: video is the brightest thing, panel recedes).
  // On detection, shift border to status color + a small ring — NOT a glow.
  const stateClass =
    state === 'green'
      ? 'border-status-ok ring-2 ring-status-ok/30 ring-offset-0'
      : state === 'orange'
        ? 'border-status-warn ring-2 ring-status-warn/30'
        : 'border-border';

  return (
    <div
      data-testid="bounding-box"
      data-state={state}
      className={cn(
        'relative h-full w-full overflow-hidden rounded-card border-2 bg-bg-deepest shadow-[inset_0_1px_2px_rgba(0,0,0,0.4)] transition-[border-color,box-shadow] duration-200 ease-out motion-reduce:transition-none',
        stateClass,
        className
      )}
    >
      {children}
    </div>
  );
}
