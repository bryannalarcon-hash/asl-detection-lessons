import { useState, useEffect } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { lessonsApi } from '@/lib/api';
import { useAppSettings } from '@/lib/settings';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Eyebrow } from '@/components/ui/eyebrow';

/**
 * Foundry · Aurora lesson intro.
 *
 * Two-column layout: left = signs list (mono uppercase, with dot leaders /
 * bullet markers via a flex rule), right = sticky practice-settings card
 * with camera + reference toggles and a gradient "Start practice" CTA.
 *
 * Preserves the back-to-source navigation (location.state.from) and all
 * existing testids (`lesson-toggle-camera`, `lesson-toggle-reference`,
 * `lesson-start`, `lesson-back-to-catalog`, `lesson-sign-item`).
 */
export default function LessonIntroPage() {
  const { slug = '' } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const { settings } = useAppSettings();

  // Back-to-catalog should return to the page that brought the user here.
  // Dashboard's "Continue last lesson" link passes `state.from = '/dashboard'`.
  // Direct visits / catalog links fall through to /lessons.
  const fromState = (location.state as { from?: string } | null)?.from;
  const backTarget = fromState && fromState.startsWith('/') ? fromState : '/lessons';
  const backLabel = backTarget === '/dashboard' ? 'Back to dashboard' : 'Back to catalog';

  const lessonQuery = useQuery({
    queryKey: ['lessons', 'get', slug],
    queryFn: () => lessonsApi.get(slug),
    retry: 0,
    refetchOnWindowFocus: false,
    enabled: Boolean(slug),
  });

  const [cameraOn, setCameraOn] = useState(settings.cameraDefault);
  const [referenceOn, setReferenceOn] = useState(settings.referenceDefault);

  useEffect(() => {
    setCameraOn(settings.cameraDefault);
    setReferenceOn(settings.referenceDefault);
  }, [settings.cameraDefault, settings.referenceDefault]);

  const lesson = lessonQuery.data?.lesson;
  const signs = lessonQuery.data?.signs ?? [];

  const handleStart = () => {
    const params = new URLSearchParams({
      camera: cameraOn ? '1' : '0',
      reference: referenceOn ? '1' : '0',
    });
    navigate(`/lessons/${slug}/practice?${params.toString()}`);
  };

  return (
    <main data-testid="page-lesson-intro" className="mx-auto max-w-5xl px-6 py-10">
      <nav
        aria-label="Breadcrumb"
        className="mb-6 font-mono text-xs uppercase tracking-[0.12em] text-fg-muted"
      >
        <Link to="/lessons" className="hover:text-fg">
          Lessons
        </Link>{' '}
        <span className="text-fg-subtle">/</span>{' '}
        <span className="text-fg">{lesson?.title ?? slug}</span>
      </nav>

      <header className="mb-10">
        {lesson ? (
          <>
            <Eyebrow>Lesson № {String(lesson.orderIndex || 0).padStart(2, '0')}</Eyebrow>
            <h1 className="mt-3 font-display text-4xl font-extrabold leading-[1.02] tracking-tight text-fg md:text-5xl">
              {lesson.title}
            </h1>
            <p className="mt-4 max-w-2xl font-mono text-sm leading-relaxed text-fg-muted">
              <span className="text-fg">{lesson.signCount}</span> signs · ~
              {lesson.signCount * 3} min · 3 reps each.
            </p>
          </>
        ) : (
          <>
            <Eyebrow>Lesson</Eyebrow>
            <h1 className="mt-3 font-display text-4xl font-extrabold leading-[1.02] tracking-tight text-fg">
              {lessonQuery.isLoading ? 'Loading lesson…' : `Lesson: ${slug}`}
            </h1>
            {!lessonQuery.isLoading && (
              <p
                className="mt-4 font-mono text-sm text-fg-muted"
                data-testid="lesson-intro-fallback"
              >
                Backend not reachable. You can still start practice with placeholder signs.
              </p>
            )}
          </>
        )}
      </header>

      <div className="grid gap-10 md:grid-cols-[1fr_320px]">
        {/* Signs list */}
        <section>
          <Eyebrow>§ Signs you'll practice</Eyebrow>
          {signs.length === 0 ? (
            <p className="mt-4 font-mono text-sm text-fg-muted">No signs loaded yet.</p>
          ) : (
            <ul className="mt-4 flex flex-col">
              {signs.map((s, i) => (
                <li
                  key={s.slug}
                  data-testid="lesson-sign-item"
                  className="grid grid-cols-[36px_1fr_auto] items-center gap-4 border-b border-line/15 py-3"
                >
                  <span className="font-mono text-sm text-fg-faint">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <span className="flex items-center gap-3">
                    <span className="font-display text-base font-medium uppercase text-fg">
                      {s.englishGloss}
                    </span>
                    <span aria-hidden="true" className="h-px flex-1 bg-line/15" />
                  </span>
                  <span className="font-mono text-xs uppercase tracking-[0.04em] text-fg-subtle">
                    3 reps
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Practice settings sticky panel */}
        <aside className="md:sticky md:top-24 md:self-start">
          <div className="rounded-card border border-line/30 bg-bg-paper p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_1px_2px_rgba(0,0,0,0.4)]">
            <Eyebrow>Practice settings</Eyebrow>
            <div className="mt-4 space-y-4">
              <label
                htmlFor="camera-toggle"
                className="flex cursor-pointer items-center gap-3"
              >
                <Checkbox
                  id="camera-toggle"
                  checked={cameraOn}
                  onCheckedChange={(c) => setCameraOn(Boolean(c))}
                  data-testid="lesson-toggle-camera"
                />
                <Label htmlFor="camera-toggle" className="cursor-pointer font-mono text-sm">
                  Camera on
                </Label>
              </label>
              <label
                htmlFor="reference-toggle"
                className="flex cursor-pointer items-center gap-3"
              >
                <Checkbox
                  id="reference-toggle"
                  checked={referenceOn}
                  onCheckedChange={(c) => setReferenceOn(Boolean(c))}
                  data-testid="lesson-toggle-reference"
                />
                <Label
                  htmlFor="reference-toggle"
                  className="cursor-pointer font-mono text-sm"
                >
                  Show instructor reference video
                </Label>
              </label>

              <div className="border-t border-line/15 pt-4">
                <p className="font-mono text-xs leading-relaxed text-fg-subtle">
                  Hiding the reference tests recall. Turning off the camera switches to
                  self-report mode — you decide if your sign was correct.
                </p>
              </div>

              <Button
                size="lg"
                className="w-full"
                onClick={handleStart}
                data-testid="lesson-start"
              >
                Start practice →
              </Button>
              <Link
                to={backTarget}
                className="block text-center font-mono text-xs text-fg-muted hover:text-fg"
                data-testid="lesson-back-to-catalog"
              >
                ← {backLabel}
              </Link>
            </div>
          </div>

          <div className="mt-4 flex justify-between gap-3 px-1 font-mono text-xs">
            <span className="flex flex-col gap-1">
              <span className="text-[0.7rem] uppercase tracking-[0.12em] text-fg-muted">
                Time
              </span>
              <span className="text-fg">~{(lesson?.signCount ?? 6) * 3} min</span>
            </span>
            <span className="flex flex-col gap-1">
              <span className="text-[0.7rem] uppercase tracking-[0.12em] text-fg-muted">
                Signs
              </span>
              <span className="text-fg">{lesson?.signCount ?? signs.length}</span>
            </span>
            <span className="flex flex-col gap-1">
              <span className="text-[0.7rem] uppercase tracking-[0.12em] text-fg-muted">
                Reps each
              </span>
              <span className="text-fg">×3</span>
            </span>
          </div>
        </aside>
      </div>
    </main>
  );
}
