/**
 * Themed text input that forwards a ref and applies the app's border, surface,
 * and focus-ring styling. It defaults the input type to text and merges any
 * supplied className.
 */
import * as React from 'react';
import { cn } from '@/lib/utils';

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type = 'text', ...props }, ref) => {
    return (
      <input
        ref={ref}
        type={type}
        data-slot="input"
        className={cn(
          'flex h-9 w-full rounded-md border border-border bg-bg-elevated px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-fg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-0 disabled:cursor-not-allowed disabled:opacity-50',
          className
        )}
        {...props}
      />
    );
  }
);
Input.displayName = 'Input';
