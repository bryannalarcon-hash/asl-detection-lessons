/**
 * Non-blocking bottom-right toast announcing that a sign has been completed and
 * saved. It auto-dismisses after a few seconds and can also be closed manually.
 */
import { useEffect } from 'react';
import { Sparkles, X as XIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

interface SignCompleteToastProps {
  sign: string | null;
  onDismiss: () => void;
}

/**
 * Foundry · Aurora sign-complete toast.
 *
 * Bottom-right, non-blocking, auto-dismisses after 4s. Cyan-tinted border
 * matches the data-viz accent the dashboard uses.
 */
export function SignCompleteToast({ sign, onDismiss }: SignCompleteToastProps) {
  useEffect(() => {
    if (!sign) return;
    const t = window.setTimeout(onDismiss, 4_000);
    return () => window.clearTimeout(t);
  }, [sign, onDismiss]);

  return (
    <div
      aria-live="polite"
      aria-atomic="true"
      className="pointer-events-none fixed bottom-4 right-4 z-50 max-w-sm"
    >
      <div
        data-testid="sign-complete-toast"
        aria-hidden={!sign}
        className={cn(
          'pointer-events-auto flex w-full items-start gap-3 rounded-[12px] border border-accent-cyan/40 bg-bg-elevated/95 p-4',
          'shadow-[0_8px_24px_-8px_rgba(6,182,212,0.4),inset_0_1px_0_rgba(255,255,255,0.06)]',
          'backdrop-blur-sm transition-all duration-200 ease-out',
          sign ? 'translate-y-0 opacity-100' : 'pointer-events-none translate-y-2 opacity-0'
        )}
      >
        <div className="flex h-9 w-9 flex-none items-center justify-center rounded-full border border-accent-cyan/40 bg-gradient-to-b from-accent-cyan/25 to-accent-cyan/5 text-accent-cyan shadow-[inset_0_1px_0_rgba(255,255,255,0.1)]">
          <Sparkles className="h-4 w-4" />
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <p className="font-mono text-[10px] uppercase tracking-[0.15em] text-fg-muted">
            Sign saved to memory
          </p>
          <p className="truncate font-display text-base uppercase tracking-wider text-fg">
            {sign ?? '—'}
          </p>
        </div>
        <button
          type="button"
          data-testid="sign-complete-dismiss"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="flex-none rounded-md p-1 text-fg-muted transition-colors hover:bg-bg-raised hover:text-fg focus-visible:outline-2 focus-visible:outline-accent-ring focus-visible:outline-offset-2"
        >
          <XIcon className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
