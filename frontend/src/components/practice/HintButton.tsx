import { useEffect, useRef, useState } from 'react';
import { HelpCircle } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import type { HintParameter } from '@/data/sign-hints';
import { ReferenceVideo } from './ReferenceVideo';

interface HintButtonProps {
  signSlug: string;
  englishGloss: string;
  /** Failures + drill-skips on the current sign. Drives the visual urgency:
   *  0 = quiet, 1 = normal, ≥2 = accent-pulse + sibling caption.
   *  At ≥3 the dialog auto-opens once per sign. */
  failCount?: number;
  /** Word-tied cue shown on an unprompted open (no failed attempt to diagnose). */
  defaultHint?: string;
  /** Targeted cue from the last failed recorded attempt; overrides the default. */
  attemptHint?: { parameter: HintParameter; hint: string } | null;
  /** Monotonic counter; each fresh failed verdict bumps it to auto-open the
   *  dialog once for that attempt. */
  openSignal?: number;
}

const FALLBACK_HINT = 'Try again — focus on the handshape, then trace the movement slowly.';
const AUTO_OPEN_THRESHOLD = 3;

const PARAMETER_LABELS: Record<HintParameter, string> = {
  handshape: 'handshape',
  movement: 'movement',
  location: 'location',
  'palm-orientation': 'palm orientation',
  timing: 'timing',
  framing: 'framing',
};

export function HintButton({
  signSlug,
  englishGloss,
  failCount = 0,
  defaultHint,
  attemptHint = null,
  openSignal = 0,
}: HintButtonProps) {
  const [open, setOpen] = useState(false);
  // Track whether we've auto-opened for this sign so we don't re-trigger
  // every render once the user dismisses the dialog.
  const autoOpenedForSign = useRef<string | null>(null);
  // Track the last openSignal we acted on so a fresh failed verdict opens the
  // dialog exactly once, not on every subsequent render.
  const lastOpenSignal = useRef(openSignal);

  useEffect(() => {
    if (failCount >= AUTO_OPEN_THRESHOLD && autoOpenedForSign.current !== signSlug) {
      autoOpenedForSign.current = signSlug;
      setOpen(true);
    }
    if (failCount === 0) {
      // Reset memo when the sign resets (new sign or back-sign clears the count).
      autoOpenedForSign.current = null;
    }
  }, [failCount, signSlug]);

  useEffect(() => {
    if (openSignal > 0 && openSignal !== lastOpenSignal.current) {
      lastOpenSignal.current = openSignal;
      setOpen(true);
    }
  }, [openSignal]);

  const urgent = failCount >= 2;
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <div className="inline-flex flex-col items-start gap-1">
        <DialogTrigger
          data-testid="hint-button"
          data-fail-count={failCount}
          className={cn(
            'inline-flex h-8 items-center gap-2 rounded-md border px-3 font-mono text-[0.78rem] transition-[background-color,border-color,color,box-shadow] duration-150 ease-out focus-visible:outline-2 focus-visible:outline-accent-ring focus-visible:outline-offset-2',
            urgent
              ? 'animate-pulse border-accent/60 bg-accent/10 text-accent shadow-[0_0_18px_-6px_hsl(var(--accent)/0.6)] hover:bg-accent/20'
              : 'border-transparent bg-transparent text-fg-muted hover:border-border hover:bg-bg-paper hover:text-fg',
          )}
        >
          <HelpCircle className="h-4 w-4" />
          {urgent ? 'Stuck? Open hint' : 'Show a hint'}
        </DialogTrigger>
        {urgent && (
          <span
            data-testid="hint-urgent-caption"
            className="font-mono text-[0.65rem] uppercase tracking-[0.08em] text-fg-muted"
          >
            {failCount} miss{failCount === 1 ? '' : 'es'} this sign — try the hint
          </span>
        )}
      </div>
      <DialogContent className="max-h-[85vh] w-[min(640px,92vw)] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Hint · {englishGloss}</DialogTitle>
          {attemptHint ? (
            <DialogDescription data-testid="hint-attempt">
              <span className="mb-1 block font-mono text-[0.65rem] uppercase tracking-[0.08em] text-accent">
                Focus: {PARAMETER_LABELS[attemptHint.parameter]}
              </span>
              {attemptHint.hint}
            </DialogDescription>
          ) : (
            <DialogDescription data-testid="hint-default">
              {defaultHint ?? FALLBACK_HINT}
            </DialogDescription>
          )}
        </DialogHeader>
        <div className="mt-4 aspect-video w-full">
          <ReferenceVideo signSlug={signSlug} englishGloss={englishGloss} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
