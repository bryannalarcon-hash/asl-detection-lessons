import { isDevToolsEnabled } from '@/lib/env';
import { __devSetBoxState } from '@/cv/evaluate';

interface DevPanelProps {
  onSetGray: () => void;
  onSetOrange: () => void;
  onSetGreen: () => void;
  onSkipDrill: () => void;
  onAutoPassRep: () => void;
}

const BTN =
  'rounded-md border border-status-warn/60 bg-status-warn/5 px-3 py-1.5 text-xs font-mono uppercase tracking-wider text-status-warn transition-colors hover:bg-status-warn/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-status-warn focus-visible:ring-offset-2 focus-visible:ring-offset-bg';

export function DevPanel({
  onSetGray,
  onSetOrange,
  onSetGreen,
  onSkipDrill,
  onAutoPassRep,
}: DevPanelProps) {
  if (!isDevToolsEnabled()) return null;

  const handleGray = () => {
    __devSetBoxState('no-hands');
    onSetGray();
  };
  const handleOrange = () => {
    __devSetBoxState('hands-detected');
    onSetOrange();
  };
  const handleGreen = () => {
    // Per PRD: visual-only. Box turns green for ~600ms, mastery is NOT advanced.
    onSetGreen();
  };

  return (
    <aside
      data-testid="dev-panel"
      data-dev-override
      className="mt-8 rounded-card border border-status-warn/40 bg-bg-elevated/60 p-4"
      aria-label="Developer panel"
    >
      <p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-status-warn">
        Dev panel · mock CV
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          data-testid="dev-set-gray"
          data-dev-override
          onClick={handleGray}
          className={BTN}
        >
          Set gray
        </button>
        <button
          type="button"
          data-testid="dev-set-orange"
          data-dev-override
          onClick={handleOrange}
          className={BTN}
        >
          Set orange
        </button>
        <button
          type="button"
          data-testid="dev-set-green"
          data-dev-override
          onClick={handleGreen}
          className={BTN}
        >
          Set green
        </button>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button
          type="button"
          data-testid="dev-skip-drill"
          data-dev-override
          onClick={onSkipDrill}
          className={BTN}
        >
          Skip drill
        </button>
        <button
          type="button"
          data-testid="dev-auto-pass-rep"
          data-dev-override
          onClick={onAutoPassRep}
          className={BTN}
        >
          Auto-pass rep
        </button>
      </div>
    </aside>
  );
}
