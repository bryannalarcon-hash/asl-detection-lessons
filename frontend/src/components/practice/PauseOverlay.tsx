import { Play, X as XIcon } from 'lucide-react';

interface PauseOverlayProps {
  onResume: () => void;
  onExit: () => void;
}

/**
 * Foundry · Aurora pause modal. Stops both camera + reference videos
 * underneath via the `paused` prop threaded through the parent. Resume
 * picks the practice loop back up where it was; Exit returns to the
 * lesson intro for this lesson.
 */
export function PauseOverlay({ onResume, onExit }: PauseOverlayProps) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Paused"
      data-testid="pause-overlay"
      className="fixed inset-0 z-50 flex items-center justify-center bg-bg-deep/80 backdrop-blur-sm animate-in fade-in duration-150"
    >
      <div className="mx-4 w-full max-w-md rounded-[12px] border border-border bg-bg-paper p-8 shadow-pop">
        <p className="font-mono text-[0.72rem] uppercase tracking-[0.12em] text-fg-muted">
          Paused
        </p>
        <h2 className="mt-2 font-display text-2xl font-bold tracking-tight">Take a breath.</h2>
        <p className="mt-2 text-sm text-fg-muted">Your progress is saved.</p>
        <div className="mt-6 flex flex-col gap-2">
          <button
            type="button"
            data-testid="pause-resume"
            onClick={onResume}
            className="btn-aurora-primary inline-flex w-full items-center justify-center gap-2 rounded-full px-4 py-3 text-sm transition-[filter] duration-150 ease-out hover:[filter:brightness(1.08)] active:translate-y-px focus-visible:outline-2 focus-visible:outline-accent-ring focus-visible:outline-offset-2"
          >
            <Play className="h-4 w-4" />
            Resume
          </button>
          <button
            type="button"
            data-testid="pause-exit"
            onClick={onExit}
            className="inline-flex w-full items-center justify-center gap-2 rounded-md border border-border bg-bg-elev px-4 py-3 text-sm font-medium text-fg-muted transition-colors hover:border-accent-soft hover:text-fg active:translate-y-px focus-visible:outline-2 focus-visible:outline-accent-ring focus-visible:outline-offset-2"
          >
            <XIcon className="h-4 w-4" />
            Exit lesson
          </button>
        </div>
      </div>
    </div>
  );
}
