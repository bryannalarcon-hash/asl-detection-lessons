/**
 * Themed toggle switch wrapping the base-ui switch primitive with accent
 * checked-state coloring and a sliding thumb. It applies the app's focus-ring
 * and disabled styling and merges any supplied className.
 */
import * as React from 'react';
import { Switch as SwitchPrimitive } from '@base-ui/react/switch';
import { cn } from '@/lib/utils';

export type SwitchProps = React.ComponentProps<typeof SwitchPrimitive.Root>;

export function Switch({ className, ...props }: SwitchProps) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        'peer inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent shadow-sm transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-bg',
        'disabled:cursor-not-allowed disabled:opacity-50',
        'data-[checked]:bg-accent data-[unchecked]:bg-bg-elevated',
        className
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        className={cn(
          'pointer-events-none block h-4 w-4 rounded-full bg-fg shadow-lg ring-0 transition-transform',
          'data-[checked]:translate-x-4 data-[unchecked]:translate-x-0'
        )}
      />
    </SwitchPrimitive.Root>
  );
}
