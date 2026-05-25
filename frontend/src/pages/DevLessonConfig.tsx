import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Navigate } from 'react-router-dom';
import { isDevToolsEnabled } from '@/lib/env';
import { lessonsApi } from '@/lib/api';
import {
  type DrillConfig,
  type LessonConfig,
  configFromSigns,
  defaultDrillForSign,
  readLessonConfig,
  writeLessonConfig,
  clearLessonConfig,
} from '@/lib/lesson-config';
import { FALLBACK_LESSON_SLUG, FALLBACK_SIGNS } from '@/lib/fallback-lesson';

/**
 * [Dev: Lesson Config] editor.
 *
 * Dev-only surface to override, per lesson:
 *   - drill count (add/remove drills),
 *   - per drill: which sign + reps + reference-clip segment [startSec, endSec],
 *
 * The overlay is persisted to localStorage (keyed by lesson slug) and read by
 * the practice flow. Gated by `isDevToolsEnabled()` so the entire page is
 * dropped from prod bundles (VITE_DEV_TOOLS=0 collapses the guard and DCE
 * removes the body + this module's imports).
 */
export default function DevLessonConfigPage() {
  if (!isDevToolsEnabled()) {
    return <Navigate to="/dashboard" replace />;
  }
  return <DevLessonConfigInner />;
}

function DevLessonConfigInner() {
  const lessonsQuery = useQuery({
    queryKey: ['lessons', 'list'],
    queryFn: () => lessonsApi.list(),
    retry: 0,
    refetchOnWindowFocus: false,
  });
  // When the backend is unreachable, offer the offline fallback lesson so the
  // editor always has something to configure (mirrors Practice.tsx's fallback).
  const lessons =
    lessonsQuery.data && lessonsQuery.data.lessons.length > 0
      ? lessonsQuery.data.lessons.map((l) => ({ slug: l.slug, title: l.title }))
      : [{ slug: FALLBACK_LESSON_SLUG, title: 'Fallback lesson (offline)' }];

  const [slug, setSlug] = useState('');

  // Default to the first lesson once the list resolves.
  useEffect(() => {
    if (!slug && lessons.length > 0) setSlug(lessons[0].slug);
  }, [lessons, slug]);

  const detailQuery = useQuery({
    queryKey: ['lessons', 'get', slug],
    queryFn: () => lessonsApi.get(slug),
    retry: 0,
    refetchOnWindowFocus: false,
    enabled: Boolean(slug),
  });

  // Sign slugs available for the per-drill dropdowns. Falls back to the offline
  // signs so the editor stays usable when the backend can't resolve the lesson.
  const signOptions = useMemo(() => {
    const fromBackend = detailQuery.data?.signs.map((s) => s.slug) ?? [];
    return fromBackend.length > 0 ? fromBackend : FALLBACK_SIGNS.map((s) => s.slug);
  }, [detailQuery.data]);

  const [config, setConfig] = useState<LessonConfig | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  // Load the saved overlay (or seed defaults from the lesson's signs) when the
  // lesson selection or its detail changes. Seeds from the offline fallback
  // signs when the backend can't resolve the lesson detail.
  useEffect(() => {
    if (!slug) {
      setConfig(null);
      return;
    }
    const saved = readLessonConfig(slug);
    if (saved) {
      setConfig(saved);
      return;
    }
    const seedSigns =
      detailQuery.data && detailQuery.data.signs.length > 0
        ? detailQuery.data.signs
        : detailQuery.isError || !detailQuery.isFetching
          ? FALLBACK_SIGNS
          : null;
    if (seedSigns) setConfig(configFromSigns(slug, seedSigns));
  }, [slug, detailQuery.data, detailQuery.isError, detailQuery.isFetching]);

  const drills = config?.drills ?? [];

  const fallbackSign = () => signOptions[0] ?? 'hello';

  const setDrills = (next: DrillConfig[]) => {
    if (!config) return;
    setConfig({ ...config, drills: next });
  };

  const updateDrill = (idx: number, patch: Partial<DrillConfig>) => {
    setDrills(drills.map((d, i) => (i === idx ? { ...d, ...patch } : d)));
  };

  const setDrillCount = (count: number) => {
    const target = Math.max(0, Math.trunc(count));
    if (target === drills.length) return;
    if (target < drills.length) {
      setDrills(drills.slice(0, target));
      return;
    }
    const added = Array.from({ length: target - drills.length }, () =>
      defaultDrillForSign(fallbackSign())
    );
    setDrills([...drills, ...added]);
  };

  const save = () => {
    if (!config) return;
    writeLessonConfig(config);
    setSavedAt(Date.now());
  };

  const revert = () => {
    if (!slug) return;
    clearLessonConfig(slug);
    const seedSigns =
      detailQuery.data && detailQuery.data.signs.length > 0
        ? detailQuery.data.signs
        : FALLBACK_SIGNS;
    setConfig(configFromSigns(slug, seedSigns));
    setSavedAt(null);
  };

  return (
    <main
      data-testid="page-dev-lesson-config"
      data-dev-override
      className="mx-auto max-w-3xl px-6 py-10"
    >
      <p className="mb-1 font-mono text-[0.7rem] uppercase tracking-[0.14em] text-status-warn">
        [Dev: Lesson Config]
      </p>
      <h1 className="font-display mb-2 text-2xl font-extrabold tracking-tight text-fg">
        Lesson Config editor
      </h1>
      <p className="mb-6 max-w-xl font-mono text-[0.8rem] leading-relaxed text-fg-muted">
        Dev-only. Overrides drills, reps, signs, and reference-clip segments for
        a lesson. Persisted to localStorage and read by the practice flow.
        Hidden + dead-code-eliminated when VITE_DEV_TOOLS=0.
      </p>

      <label className="mb-6 block">
        <span className="mb-1 block font-mono text-[0.72rem] uppercase tracking-wider text-fg-muted">
          Lesson
        </span>
        <select
          data-testid="dev-lesson-config-lesson-select"
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          className="w-full rounded-md border border-border bg-bg-paper px-3 py-2 font-mono text-sm text-fg"
        >
          {lessons.length === 0 && <option value="">No lessons loaded</option>}
          {lessons.map((l) => (
            <option key={l.slug} value={l.slug}>
              {l.title} ({l.slug})
            </option>
          ))}
        </select>
      </label>

      {config && (
        <>
          <label className="mb-4 flex items-center gap-3">
            <span className="font-mono text-[0.72rem] uppercase tracking-wider text-fg-muted">
              # Drills
            </span>
            <input
              type="number"
              min={0}
              data-testid="dev-lesson-config-drill-count"
              value={drills.length}
              onChange={(e) => setDrillCount(Number(e.target.value))}
              className="w-20 rounded-md border border-border bg-bg-paper px-2 py-1 font-mono text-sm text-fg"
            />
          </label>

          <ul className="flex flex-col gap-3">
            {drills.map((drill, idx) => (
              <li
                key={idx}
                data-testid="dev-lesson-config-drill"
                className="rounded-md border border-status-warn/40 bg-status-warn/5 p-3"
              >
                <div className="mb-2 flex items-center justify-between">
                  <span className="font-mono text-[0.7rem] uppercase tracking-wider text-fg-muted">
                    Drill {String(idx + 1).padStart(2, '0')}
                  </span>
                  <button
                    type="button"
                    data-testid="dev-lesson-config-remove-drill"
                    onClick={() => setDrills(drills.filter((_, i) => i !== idx))}
                    className="font-mono text-[0.7rem] text-status-warn hover:underline"
                  >
                    Remove
                  </button>
                </div>

                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <label className="col-span-2 flex flex-col gap-1 sm:col-span-1">
                    <span className="font-mono text-[0.65rem] uppercase tracking-wider text-fg-subtle">
                      Sign
                    </span>
                    <select
                      data-testid="dev-lesson-config-sign"
                      value={drill.sign}
                      onChange={(e) =>
                        updateDrill(idx, {
                          sign: e.target.value,
                          videoSrc: defaultDrillForSign(e.target.value).videoSrc,
                        })
                      }
                      className="rounded border border-border bg-bg-paper px-2 py-1 font-mono text-sm text-fg"
                    >
                      {!signOptions.includes(drill.sign) && (
                        <option value={drill.sign}>{drill.sign}</option>
                      )}
                      {signOptions.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="flex flex-col gap-1">
                    <span className="font-mono text-[0.65rem] uppercase tracking-wider text-fg-subtle">
                      Reps
                    </span>
                    <input
                      type="number"
                      min={1}
                      data-testid="dev-lesson-config-reps"
                      value={drill.reps}
                      onChange={(e) =>
                        updateDrill(idx, { reps: Number(e.target.value) })
                      }
                      className="rounded border border-border bg-bg-paper px-2 py-1 font-mono text-sm text-fg"
                    />
                  </label>

                  <label className="flex flex-col gap-1">
                    <span className="font-mono text-[0.65rem] uppercase tracking-wider text-fg-subtle">
                      Start (s)
                    </span>
                    <input
                      type="number"
                      min={0}
                      step={0.1}
                      data-testid="dev-lesson-config-start"
                      value={drill.segment.startSec}
                      onChange={(e) =>
                        updateDrill(idx, {
                          segment: {
                            ...drill.segment,
                            startSec: Number(e.target.value),
                          },
                        })
                      }
                      className="rounded border border-border bg-bg-paper px-2 py-1 font-mono text-sm text-fg"
                    />
                  </label>

                  <label className="flex flex-col gap-1">
                    <span className="font-mono text-[0.65rem] uppercase tracking-wider text-fg-subtle">
                      End (s)
                    </span>
                    <input
                      type="number"
                      min={0}
                      step={0.1}
                      data-testid="dev-lesson-config-end"
                      value={drill.segment.endSec}
                      onChange={(e) =>
                        updateDrill(idx, {
                          segment: {
                            ...drill.segment,
                            endSec: Number(e.target.value),
                          },
                        })
                      }
                      className="rounded border border-border bg-bg-paper px-2 py-1 font-mono text-sm text-fg"
                    />
                  </label>
                </div>

                <p className="mt-2 font-mono text-[0.65rem] text-fg-subtle">
                  clip: {drill.videoSrc} · segment 0s = full clip
                </p>
              </li>
            ))}
          </ul>

          <div className="mt-4 flex items-center gap-3">
            <button
              type="button"
              data-testid="dev-lesson-config-add-drill"
              onClick={() => setDrillCount(drills.length + 1)}
              className="rounded-md border border-status-warn/60 bg-status-warn/10 px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-status-warn hover:bg-status-warn/20"
            >
              [Dev: Add drill]
            </button>
            <button
              type="button"
              data-testid="dev-lesson-config-save"
              onClick={save}
              className="rounded-md border border-accent/60 bg-accent/10 px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-accent hover:bg-accent/20"
            >
              [Dev: Save]
            </button>
            <button
              type="button"
              data-testid="dev-lesson-config-revert"
              onClick={revert}
              className="rounded-md border border-border px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-fg-muted hover:bg-bg-elev hover:text-fg"
            >
              [Dev: Revert to defaults]
            </button>
            {savedAt && (
              <span
                data-testid="dev-lesson-config-saved"
                className="font-mono text-[0.7rem] text-accent"
              >
                Saved
              </span>
            )}
          </div>
        </>
      )}
    </main>
  );
}
