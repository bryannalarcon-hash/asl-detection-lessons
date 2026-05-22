import { useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { progressApi, type HeatmapCell, type DayDetailDto } from '@/lib/api';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';

interface HeatmapProps {
  /** Server payload (date + rep count). Optional — falls back to a 75-day empty grid. */
  cells?: HeatmapCell[];
}

type Intensity = 0 | 1 | 2 | 3 | 4;

const DAYS_OF_WEEK = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] as const;

function bucketize(reps: number): Intensity {
  if (reps <= 0) return 0;
  if (reps <= 9) return 1;
  if (reps <= 19) return 2;
  if (reps <= 29) return 3;
  return 4;
}

function buildEmpty(days = 75): HeatmapCell[] {
  const out: HeatmapCell[] = [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    out.push({ date: d.toISOString().slice(0, 10), drillCount: 0, intensity: 0 });
  }
  return out;
}

// Five tiers: 0 = empty deep-well; 1-3 = calibrated GitHub greens (keeps the
// "more practice = greener" intuition); 4 = the Aurora cyan→violet gradient
// (signals "you crushed it"). The README explicitly calls for tier-4 to use
// `var(--grad-primary)` and the cyan ring stays as the today marker.
const INTENSITY_CLASS: Record<Intensity, string> = {
  0: 'bg-bg-deep intensity-0',
  1: 'bg-[#0e4429] intensity-1 ring-1 ring-inset ring-white/[0.03]',
  2: 'bg-[#006d32] intensity-2 ring-1 ring-inset ring-white/[0.04]',
  3: 'bg-[#26a641] intensity-3 ring-1 ring-inset ring-white/[0.05]',
  4: 'intensity-4 ring-1 ring-inset ring-white/[0.07] bg-grad-primary',
};

/**
 * GitHub-style contribution grid.
 *
 * - 7 rows (Sun → Sat), columns are weeks.
 * - Time flows left → right; today is the right-most column.
 * - Cells outside the 75-day window are rendered as transparent spacers so
 *   the week columns line up cleanly.
 * - Click a cell to open the day's summary (lessons touched, outcomes).
 * - 5 intensity tiers (calibrated for 30+ reps = highest).
 * - Day-of-week labels along the left edge; month labels along the top.
 */
export function Heatmap({ cells }: HeatmapProps) {
  const grid = useMemo<HeatmapCell[]>(() => {
    if (cells && cells.length > 0) {
      if (cells.length >= 75) return cells.slice(-75);
      const empty = buildEmpty(75 - cells.length);
      return [...empty, ...cells];
    }
    return buildEmpty(75);
  }, [cells]);

  // Map every cell into a (week, dow) coordinate so we can render a 7-row grid.
  const layout = useMemo(() => buildWeekLayout(grid), [grid]);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [openCell, setOpenCell] = useState<HeatmapCell | null>(null);

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        {/* Day-of-week labels (Mon / Wed / Fri sparse, GitHub-style) */}
        <div
          className="grid flex-none gap-[3px] pt-5 font-mono text-[9px] uppercase tracking-wider text-fg-muted"
          style={{ gridTemplateRows: 'repeat(7, minmax(0, 1fr))' }}
          aria-hidden="true"
        >
          {DAYS_OF_WEEK.map((label, idx) => (
            <span
              key={label}
              className="flex h-[14px] items-center"
              style={{ visibility: idx % 2 === 1 ? 'visible' : 'hidden' }}
            >
              {label}
            </span>
          ))}
        </div>

        <div className="min-w-0 flex-1">
          {/* Month labels above the columns */}
          <div
            className="grid h-4 gap-[3px] font-mono text-[10px] uppercase tracking-wider text-fg-muted"
            style={{ gridTemplateColumns: `repeat(${layout.cols}, minmax(0, 1fr))` }}
            aria-hidden="true"
          >
            {Array.from({ length: layout.cols }).map((_, c) => {
              const mark = layout.monthMarkers.find((m) => m.col === c);
              return (
                <div key={`mark-${c}`} className="flex items-end justify-start whitespace-nowrap">
                  {mark ? mark.label : ''}
                </div>
              );
            })}
          </div>

          {/* The grid itself. We use a generic `group` role rather than ARIA
              grid semantics because the layout is positional via grid-area —
              there are no row elements to satisfy WCAG's grid-structure rule. */}
          <div
            ref={containerRef}
            data-testid="heatmap"
            role="group"
            aria-label="Practice activity, last 75 days"
            className="grid gap-[3px]"
            style={{ gridTemplateColumns: `repeat(${layout.cols}, minmax(0, 1fr))` }}
          >
            {/* Render column-major: 7 rows × N columns. Each grid cell is positioned
                by its (col, row) absolutely via `style.gridArea`. */}
            {layout.cells.map((entry, idx) => {
              if (!entry) return null;
              const { cell, col, row } = entry;
              const intensity = (cell.intensity ?? bucketize(cell.drillCount)) as Intensity;
              const isToday = cell.date === layout.todayIso;
              const labelDate = new Date(cell.date + 'T00:00:00').toLocaleDateString(
                undefined,
                {
                  weekday: 'short',
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                }
              );
              const staggerMs = col * 8 + row * 2;
              return (
                <button
                  key={`${cell.date}-${idx}`}
                  type="button"
                  aria-current={isToday ? 'date' : undefined}
                  tabIndex={isToday ? 0 : -1}
                  data-testid="heatmap-cell"
                  data-cell-index={idx}
                  data-intensity={intensity}
                  data-date={cell.date}
                  data-today={isToday ? 'true' : undefined}
                  aria-label={`${labelDate}, ${cell.drillCount} reps${isToday ? ' (today)' : ''}`}
                  onClick={() => setOpenCell(cell)}
                  style={{
                    gridColumn: col + 1,
                    gridRow: row + 1,
                    animationDelay: `${staggerMs}ms`,
                  }}
                  className={cn(
                    'aspect-square w-full rounded-[3px] transition-[border-color,box-shadow] duration-150',
                    'motion-safe:animate-in motion-safe:fade-in',
                    'focus:outline-none',
                    'hover:ring-[1.5px] hover:ring-accent-cyan/90 hover:z-10 relative',
                    'focus-visible:ring-[1.5px] focus-visible:ring-accent-cyan focus-visible:z-10',
                    INTENSITY_CLASS[intensity],
                    isToday &&
                      'ring-[1.5px] ring-accent-cyan-bright z-10 shadow-[0_0_8px_-2px_hsl(var(--accent-cyan-bright)/0.6)]'
                  )}
                />
              );
            })}
          </div>

          {/* Legend: less ←→ more, matches GitHub. */}
          <div className="mt-3 flex items-center justify-between font-mono text-[10px] uppercase tracking-wider text-fg-muted">
            <span className="flex items-center gap-2">
              <span className="inline-block h-2 w-2 rounded-full bg-accent-cyan shadow-[0_0_6px_-1px_hsl(var(--accent-cyan)/0.7)]" />
              <span className="text-accent-cyan/80">today</span>
              <span className="text-fg-subtle">·</span>
              <span>click for detail</span>
            </span>
            <div className="flex items-center gap-1.5">
              <span>Less</span>
              {([0, 1, 2, 3, 4] as Intensity[]).map((lvl) => (
                <span
                  key={lvl}
                  className={cn(
                    'h-3 w-3 rounded-[3px]',
                    INTENSITY_CLASS[lvl]
                  )}
                />
              ))}
              <span>More</span>
            </div>
          </div>
        </div>
      </div>

      <Dialog open={Boolean(openCell)} onOpenChange={(open) => !open && setOpenCell(null)}>
        <DialogContent>{openCell && <DayDetail cell={openCell} />}</DialogContent>
      </Dialog>
    </div>
  );
}

interface LayoutEntry {
  cell: HeatmapCell;
  col: number;
  row: number;
}

interface Layout {
  cells: (LayoutEntry | null)[];
  cols: number;
  monthMarkers: { col: number; label: string }[];
  todayIso: string;
}

/**
 * Maps each cell into its (column, row) in a GitHub-style week grid.
 *
 *   row = day-of-week (0 = Sun ... 6 = Sat)
 *   col = number of weeks ago (0 = current week, N-1 = oldest)
 *
 * The first cell of the window typically sits mid-column on the left
 * (e.g. on a Wednesday). We don't render leading/trailing empty cells —
 * the grid track gap stays consistent regardless.
 */
function buildWeekLayout(cells: HeatmapCell[]): Layout {
  if (cells.length === 0) {
    return { cells: [], cols: 0, monthMarkers: [], todayIso: '' };
  }
  // Reference today as the last cell.
  const last = new Date(cells[cells.length - 1].date + 'T00:00:00');
  last.setHours(0, 0, 0, 0);

  // Anchor the right column on the Saturday of the current week so today
  // lands within the rightmost column.
  const lastDow = last.getDay(); // 0 = Sun
  const rightmostSat = new Date(last);
  rightmostSat.setDate(last.getDate() + (6 - lastDow));

  const entries: LayoutEntry[] = cells.map((cell) => {
    const d = new Date(cell.date + 'T00:00:00');
    d.setHours(0, 0, 0, 0);
    const diffDays = Math.round((rightmostSat.getTime() - d.getTime()) / (1000 * 60 * 60 * 24));
    const col = Math.floor(diffDays / 7);
    const row = d.getDay();
    return { cell, col, row };
  });

  // Re-index columns so that col=0 is leftmost (oldest).
  const maxCol = Math.max(...entries.map((e) => e.col));
  const normalized = entries.map((e) => ({ ...e, col: maxCol - e.col }));
  const cols = maxCol + 1;

  // Month markers: for each column, find the earliest in-window date and emit
  // the month name if it differs from the previous column's month.
  const monthByCol = new Map<number, string>();
  for (const e of normalized) {
    const month = new Date(e.cell.date + 'T00:00:00').toLocaleString(undefined, {
      month: 'short',
    });
    if (!monthByCol.has(e.col)) monthByCol.set(e.col, month);
  }
  const monthMarkers: { col: number; label: string }[] = [];
  let lastMonth = '';
  for (let c = 0; c < cols; c++) {
    const m = monthByCol.get(c);
    if (m && m !== lastMonth) {
      monthMarkers.push({ col: c, label: m });
      lastMonth = m;
    }
  }

  const todayIso = (() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d.toISOString().slice(0, 10);
  })();

  return {
    cells: normalized,
    cols,
    monthMarkers,
    todayIso,
  };
}

function DayDetail({ cell }: { cell: HeatmapCell }) {
  const d = new Date(cell.date + 'T00:00:00');
  const longDate = d.toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
  const intensity = (cell.intensity ?? bucketize(cell.drillCount)) as Intensity;
  const bucketLabel = ['No practice', '1–9 reps', '10–19 reps', '20–29 reps', '30+ reps'][
    intensity
  ];

  const dayQuery = useQuery({
    queryKey: ['progress', 'day', cell.date],
    queryFn: () => progressApi.day(cell.date),
    enabled: cell.drillCount > 0, // skip fetch for empty days
    refetchOnWindowFocus: false,
  });

  const lessons = dayQuery.data?.lessons ?? [];
  const outcomes = dayQuery.data?.outcomes;

  return (
    <div className="space-y-4">
      <DialogHeader>
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-fg-muted">
          Practice on
        </p>
        <DialogTitle className="font-display text-2xl uppercase tracking-wider">
          {longDate}
        </DialogTitle>
      </DialogHeader>

      <div className="grid grid-cols-2 gap-3 text-sm">
        <div className="rounded-card border border-border bg-bg p-4">
          <p className="font-mono text-[10px] uppercase tracking-wider text-fg-muted">Reps</p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-fg">{cell.drillCount}</p>
          {outcomes && cell.drillCount > 0 && (
            <p className="mt-1 font-mono text-[10px] text-fg-muted">
              {outcomes.pass} pass · {outcomes.fail} fail · {outcomes.skip} skip
            </p>
          )}
        </div>
        <div className="rounded-card border border-border bg-bg p-4">
          <p className="font-mono text-[10px] uppercase tracking-wider text-fg-muted">
            Intensity
          </p>
          <p className="mt-1 text-2xl font-bold text-fg">{bucketLabel}</p>
        </div>
      </div>

      {cell.drillCount > 0 && (
        <div className="space-y-2">
          <p className="font-mono text-[10px] uppercase tracking-wider text-fg-muted">
            Lessons touched
          </p>
          {dayQuery.isLoading && (
            <p className="text-xs text-fg-muted">Loading…</p>
          )}
          {dayQuery.isError && (
            <p className="text-xs text-status-warn">Couldn't load lessons.</p>
          )}
          {!dayQuery.isLoading && lessons.length === 0 && dayQuery.isSuccess && (
            <p className="text-xs text-fg-muted">No lesson detail available for this day.</p>
          )}
          <ul className="space-y-1">
            {lessons.map((l) => (
              <li key={l.slug}>
                <Link
                  to={`/lessons/${l.slug}`}
                  className="flex items-center justify-between gap-3 rounded-md border border-border bg-bg px-3 py-2 text-sm transition-colors hover:bg-bg-raised hover:border-border-strong"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-fg">{l.title}</span>
                    <span className="block font-mono text-[10px] uppercase tracking-wider text-fg-muted">
                      {l.category} · {l.reps} reps · {l.signs} signs
                    </span>
                  </span>
                  <ExternalLink className="h-3.5 w-3.5 flex-none text-fg-subtle" />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      {cell.drillCount === 0 && (
        <p className="text-xs text-fg-muted">No practice on this day.</p>
      )}
    </div>
  );
}

/** Convenience for the legend. */
export const HEATMAP_INTENSITY_BUCKETS = [
  { label: 'No practice', cls: INTENSITY_CLASS[0] },
  { label: '1–9 reps', cls: INTENSITY_CLASS[1] },
  { label: '10–19 reps', cls: INTENSITY_CLASS[2] },
  { label: '20–29 reps', cls: INTENSITY_CLASS[3] },
  { label: '30+ reps', cls: INTENSITY_CLASS[4] },
];

export type { HeatmapCell };
export const _internal = { buildEmpty, bucketize, buildWeekLayout };
