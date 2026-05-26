import { isDevToolsEnabled } from '@/lib/env';
import type { RepVerdict } from '@/cv/captureRep';

// Dev-only diagnostic overlay mirroring the PoC/demo readout: execution
// provider, engine status, the last rep's top-3 + confidences, verifier vote,
// hand-detection fraction, and per-net timing. Toggleable from the dev panel.
// Stripped from prod builds (DCE on isDevToolsEnabled()).

const CV_READOUT_KEY = 'asl-pilot.dev.cvReadout';

/** Persisted dev preference: show the CV readout. Defaults ON. */
export function readCvReadoutPref(): boolean {
  try {
    return window.localStorage.getItem(CV_READOUT_KEY) !== '0';
  } catch {
    return true;
  }
}

export function writeCvReadoutPref(on: boolean): void {
  try {
    window.localStorage.setItem(CV_READOUT_KEY, on ? '1' : '0');
  } catch {
    // localStorage full/disabled — non-fatal.
  }
}

interface CvReadoutProps {
  verdict: RepVerdict | null;
  backend: 'webgpu' | 'wasm' | null;
  ready: boolean;
  notReady: boolean;
  target: string;
}

const pct = (n: number) => `${(n * 100).toFixed(0)}%`;

export function CvReadout({ verdict, backend, ready, notReady, target }: CvReadoutProps) {
  if (!isDevToolsEnabled()) return null;

  const engine = notReady ? 'unavailable → self-report' : ready ? 'ready' : 'loading…';
  const handsFrac = verdict
    ? verdict.handsFrames / Math.max(1, verdict.framesProcessed)
    : 0;
  const rank = !verdict
    ? '—'
    : verdict.isTop1
      ? 'top-1'
      : verdict.inTop3
        ? 'top-3'
        : 'not top-3';

  return (
    <aside
      data-testid="cv-readout"
      data-dev-override
      className="mt-4 rounded-card border border-accent/40 bg-bg-elevated/60 p-4 font-mono text-[11px] leading-relaxed text-fg-muted"
      aria-label="Developer CV readout"
    >
      <p className="mb-2 text-[10px] uppercase tracking-wider text-accent">
        [Dev: CV readout]
      </p>
      <div>
        EP <span className="text-fg">{backend ?? '—'}</span> · engine{' '}
        <span className="text-fg">{engine}</span> · target{' '}
        <span className="text-fg">{target || '—'}</span>
      </div>

      {!verdict ? (
        <p className="mt-1">No rep recorded yet — hit Record attempt.</p>
      ) : (
        <>
          <div className="mt-1">
            verdict{' '}
            <span className={verdict.pass ? 'text-status-ok' : 'text-status-err'}>
              {verdict.pass ? 'PASS' : 'FAIL'}
            </span>{' '}
            · verifier {verdict.verifierPassed ? 'pass' : 'no'} · target {rank}
          </div>
          <div>
            target conf <span className="text-fg">{pct(verdict.targetConf)}</span>{' '}
            (window mean {pct(verdict.targetConfMean)}) · verifier{' '}
            {pct(verdict.passFraction)} of {verdict.nWindows} windows
          </div>
          <div>
            hands{' '}
            <span className="text-fg">
              {verdict.handsFrames}/{verdict.framesProcessed}
            </span>{' '}
            frames ({pct(handsFrac)} detected)
          </div>
          <div>
            cascade {verdict.cascadeMs.toFixed(0)}ms (n1 {verdict.net1Ms.toFixed(0)} n2{' '}
            {verdict.net2Ms.toFixed(0)} n3 {verdict.net3Ms.toFixed(0)} glue{' '}
            {verdict.glueMs.toFixed(0)}) · net4 {verdict.classifyMs.toFixed(0)}ms
          </div>
          <table className="mt-1.5 w-full max-w-[220px]">
            <tbody>
              {verdict.topK.map((e, i) => (
                <tr key={e.gloss}>
                  <td className="py-0.5 text-fg">
                    {i + 1}. {e.gloss}
                    {e.gloss === target && ' ←'}
                  </td>
                  <td className="py-0.5 text-right tabular-nums">{pct(e.prob)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </aside>
  );
}
