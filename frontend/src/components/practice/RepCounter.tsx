interface RepCounterProps {
  current: number; // 0-indexed
  total: number;
}

/**
 * Foundry · Aurora rep counter for the practice title row.
 *
 * Eyebrow "REP" above a large mono numerator "X / 3" with a cyan→violet
 * gradient text fill on the digit, matching the design hero spec.
 */
export function RepCounter({ current, total }: RepCounterProps) {
  const cur = Math.min(current + 1, total);
  return (
    <div
      data-testid="rep-counter"
      className="flex flex-col items-end gap-1"
      aria-live="polite"
    >
      <span className="font-mono text-[0.72rem] uppercase tracking-[0.12em] text-fg-muted">
        Rep
      </span>
      <div className="flex items-baseline gap-2 font-display leading-none">
        <span className="gradient-text text-[2.4rem] font-extrabold tabular-nums">
          {cur}
        </span>
        <span className="font-mono text-[1.2rem] text-fg-muted">/ {total}</span>
      </div>
    </div>
  );
}
