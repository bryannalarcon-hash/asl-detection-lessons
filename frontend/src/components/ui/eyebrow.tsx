import * as React from 'react';
import { cn } from '@/lib/utils';

// Foundry · Aurora eyebrow — small mono uppercase label used above headlines
// (e.g. "NOW SIGNING", "YOUR CAMERA", "REFERENCE · HANDSHAPE", "REP",
// "ACTIVITY", "MASTERY", "A SUPERBUILDERS PROJECT"). The visual treatment
// (font, size, tracking, color) is owned by the `.eyebrow` utility class
// authored alongside the design tokens.
export function Eyebrow({
  children,
  className,
  ...rest
}: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      data-testid="eyebrow"
      className={cn('eyebrow inline-block', className)}
      {...rest}
    >
      {children}
    </span>
  );
}
