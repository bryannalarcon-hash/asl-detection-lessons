/**
 * Renders the dev-only Lesson Config editor for overriding which signs a lesson
 * contains and each stage's clip trim and rep count, persisting overlays to localStorage.
 * The whole page is gated by isDevToolsEnabled so it is dead-code-eliminated from prod bundles.
 */
import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Navigate } from 'react-router-dom';
import { isDevToolsEnabled } from '@/lib/env';
import { lessonsApi } from '@/lib/api';
import {
  type LessonConfig,
  type SignConfig,
  configFromSigns,
  defaultSignConfig,
  readLessonConfig,
  writeLessonConfig,
  clearLessonConfig,
} from '@/lib/lesson-config';
import { FALLBACK_LESSON_SLUG, FALLBACK_SIGNS } from '@/lib/fallback-lesson';
import { SignTrimmer } from '@/components/dev/SignTrimmer';

/**
 * [Dev: Lesson Config] editor.
 *
 * Dev-only surface to override, per lesson: which signs it contains (and how
 * many), and per sign per stage (handshape / movement / whole-sign) the clip
 * trim [start, end] + rep count. Each sign shows a video preview so the dev can
 * see exactly what trim each stage will play.
 *
 * Gated by `isDevToolsEnabled()` so the entire page is dropped from prod
 * bundles (VITE_DEV_TOOLS=0 collapses the guard and DCE removes the body + this
 * module's imports).
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

  // Sign slugs available for the per-sign dropdowns. Falls back to the offline
  // signs so the editor stays usable when the backend can't resolve the lesson.
  const signOptions = useMemo(() => {
    const fromBackend = detailQuery.data?.signs.map((s) => s.slug) ?? [];
    return fromBackend.length > 0 ? fromBackend : FALLBACK_SIGNS.map((s) => s.slug);
  }, [detailQuery.data]);

  const [config, setConfig] = useState<LessonConfig | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  // Load the saved overlay (or seed defaults from the lesson's signs) when the
  // lesson selection or its detail changes.
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

  const signs = config?.signs ?? [];

  const fallbackSign = () => signOptions[0] ?? 'hello';

  const setSigns = (next: SignConfig[]) => {
    if (!config) return;
    setConfig({ ...config, signs: next });
  };

  const updateSign = (idx: number, next: SignConfig) => {
    setSigns(signs.map((s, i) => (i === idx ? next : s)));
  };

  const setSignCount = (count: number) => {
    const target = Math.max(0, Math.trunc(count));
    if (target === signs.length) return;
    if (target < signs.length) {
      setSigns(signs.slice(0, target));
      return;
    }
    const added = Array.from({ length: target - signs.length }, () =>
      defaultSignConfig(fallbackSign())
    );
    setSigns([...signs, ...added]);
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
      className="mx-auto max-w-4xl px-6 py-10"
    >
      <p className="mb-1 font-mono text-[0.7rem] uppercase tracking-[0.14em] text-status-warn">
        [Dev: Lesson Config]
      </p>
      <h1 className="font-display mb-2 text-2xl font-extrabold tracking-tight text-fg">
        Lesson Config editor
      </h1>
      <p className="mb-6 max-w-2xl font-mono text-[0.8rem] leading-relaxed text-fg-muted">
        Dev-only. Per lesson: which signs (and how many), and per sign per stage
        (handshape / movement / whole-sign) the clip trim + reps. Preview each
        stage to see its trim. Persisted to localStorage and read by the practice
        flow. Hidden + dead-code-eliminated when VITE_DEV_TOOLS=0.
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
              # Signs
            </span>
            <input
              type="number"
              min={0}
              data-testid="dev-lesson-config-sign-count"
              value={signs.length}
              onChange={(e) => setSignCount(Number(e.target.value))}
              className="w-20 rounded-md border border-border bg-bg-paper px-2 py-1 font-mono text-sm text-fg"
            />
          </label>

          <ul className="flex flex-col gap-3">
            {signs.map((sign, idx) => (
              <SignTrimmer
                key={idx}
                index={idx}
                value={sign}
                signOptions={signOptions}
                onChange={(next) => updateSign(idx, next)}
                onRemove={() => setSigns(signs.filter((_, i) => i !== idx))}
              />
            ))}
          </ul>

          <div className="mt-4 flex items-center gap-3">
            <button
              type="button"
              data-testid="dev-lesson-config-add-sign"
              onClick={() => setSignCount(signs.length + 1)}
              className="rounded-md border border-status-warn/60 bg-status-warn/10 px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-status-warn hover:bg-status-warn/20"
            >
              [Dev: Add sign]
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
