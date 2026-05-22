import { isDevToolsEnabled } from '@/lib/env';
import type { UseCameraPermissionResult } from '@/hooks/useCameraPermission';

interface CameraDevToolboxProps {
  /** Force-state fn pulled from a `useCameraPermission()` instance owned by the parent. */
  forceState: UseCameraPermissionResult['forceState'];
  className?: string;
}

interface DevButton {
  label: string;
  testId: string;
  arg: 'granted' | 'denied' | 'unsupported' | 'reset';
}

const BUTTONS: DevButton[] = [
  { label: '[Dev: Force allow]', testId: 'dev-camera-force-allow', arg: 'granted' },
  { label: '[Dev: Force deny]', testId: 'dev-camera-force-deny', arg: 'denied' },
  {
    label: '[Dev: Force unsupported]',
    testId: 'dev-camera-force-unsupported',
    arg: 'unsupported',
  },
  { label: '[Dev: Reset]', testId: 'dev-camera-force-reset', arg: 'reset' },
];

/**
 * Dev-only toolbox for forcing each camera-permission state.
 * Renders nothing when `isDevToolsEnabled()` returns false.
 */
export function CameraDevToolbox({ forceState, className }: CameraDevToolboxProps) {
  if (!isDevToolsEnabled()) return null;

  return (
    <div
      data-testid="dev-camera-toolbox"
      data-dev-override
      className={[
        'flex flex-wrap items-center gap-2 rounded-md border border-status-warn/40 bg-status-warn/5 px-2 py-1.5',
        className ?? '',
      ]
        .join(' ')
        .trim()}
    >
      {BUTTONS.map((b) => (
        <button
          key={b.testId}
          type="button"
          data-testid={b.testId}
          data-dev-override
          onClick={() => forceState(b.arg)}
          className="inline-flex items-center justify-center rounded border border-status-warn/60 bg-status-warn/10 px-2 py-1 text-xs font-medium text-status-warn transition-colors hover:bg-status-warn/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-status-warn focus-visible:ring-offset-1 focus-visible:ring-offset-bg"
        >
          {b.label}
        </button>
      ))}
    </div>
  );
}
