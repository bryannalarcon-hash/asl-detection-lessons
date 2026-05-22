import * as React from 'react';
import { cn } from '@/lib/utils';

// Foundry · Aurora brand mark — a stylized fanned-hand glyph inside a
// rounded-square frame. Source: design/extracted/design_handoff_asl_pilot/src/components.jsx
// (`function Brand`). Renders at 28×28 by default; size via `className`.
// Uses `currentColor` so it inherits the surrounding text color.
interface BrandMarkProps extends React.SVGAttributes<SVGSVGElement> {
  className?: string;
  title?: string;
}

export function BrandMark({
  className,
  title = 'ASL Pilot mark',
  ...rest
}: BrandMarkProps) {
  return (
    <svg
      data-testid="brand-mark"
      viewBox="0 0 32 32"
      width={28}
      height={28}
      fill="none"
      role="img"
      aria-label={title}
      className={cn('inline-block shrink-0', className)}
      {...rest}
    >
      <rect
        x="0.5"
        y="0.5"
        width="31"
        height="31"
        rx="3"
        stroke="currentColor"
        strokeOpacity="0.85"
      />
      <path
        d="M9 21V12.5a1.5 1.5 0 113 0V18m0 0V10.5a1.5 1.5 0 113 0V18m0 0V11.5a1.5 1.5 0 113 0V19m0 0v-5a1.5 1.5 0 113 0v6.5c0 3.5-2.5 6-6 6s-6-2.5-6-6V21"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
