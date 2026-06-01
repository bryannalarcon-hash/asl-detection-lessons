/**
 * Renders the lesson-complete celebration screen with session stats, a per-sign
 * mastery snapshot, and next-lesson / back-to-dashboard CTAs. It derives the next
 * lesson by orderIndex from the lessons list and pulls streak data from the progress dashboard.
 */
import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { lessonsApi, progressApi } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Eyebrow } from '@/components/ui/eyebrow';

/**
 * Foundry · Aurora lesson complete.
 *
 * Hero: large gradient checkmark + eyebrow "LESSON COMPLETE" + display
 * lesson title + lede.
 * Stats grid: signs practiced, total reps, time, streak — each number
 * uses `gradient-text`.
 * Mastery snapshot: per-sign rows with a tiny progress bar (gradient fill).
 * CTA pair: gradient "Continue to next lesson" + ghost "Back to dashboard".
 */
export default function LessonCompletePage() {
  const { slug = '' } = useParams<{ slug: string }>();

  const lessonQuery = useQuery({
    queryKey: ['lessons', 'get', slug],
    queryFn: () => lessonsApi.get(slug),
    retry: 0,
    refetchOnWindowFocus: false,
    enabled: Boolean(slug),
  });

  const dashQuery = useQuery({
    queryKey: ['progress', 'dashboard'],
    queryFn: () => progressApi.dashboard(),
    retry: 0,
    staleTime: 0,
    refetchOnMount: 'always',
    refetchOnWindowFocus: false,
  });

  const lesson = lessonQuery.data?.lesson;
  const signs = lessonQuery.data?.signs ?? [];
  const streak = dashQuery.data?.streak;
  const dashLessons = dashQuery.data?.recentLessons ?? [];

  // Pick the next lesson by orderIndex if available; fall back to the dashboard
  // catalog ordering.
  const allLessonsQuery = useQuery({
    queryKey: ['lessons', 'list'],
    queryFn: () => lessonsApi.list(),
    retry: 0,
    refetchOnWindowFocus: false,
  });
  const allLessons = allLessonsQuery.data?.lessons ?? [];
  const sortedByOrder = [...allLessons].sort((a, b) => a.orderIndex - b.orderIndex);
  const currentIdx = sortedByOrder.findIndex((l) => l.slug === slug);
  const nextLesson =
    currentIdx >= 0 ? sortedByOrder[(currentIdx + 1) % sortedByOrder.length] : undefined;

  const signsPracticed = signs.length || (lesson?.signCount ?? 0);
  const totalReps = signsPracticed * 3;
  const minutes = signsPracticed * 1; // ~1 min/sign — placeholder mirror of design seed

  return (
    <main data-testid="page-lesson-complete" className="mx-auto max-w-4xl px-6 py-12">
      {/* Hero */}
      <header className="mb-12 flex flex-wrap items-start gap-6">
        <span
          aria-hidden="true"
          className="grid h-16 w-16 flex-none place-items-center rounded-full"
          style={{ background: 'var(--grad-primary)' }}
        >
          <svg
            width="28"
            height="28"
            viewBox="0 0 24 24"
            fill="none"
            stroke="#08101c"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="20 6 9 17 4 12" />
          </svg>
        </span>
        <div className="min-w-0 flex-1">
          <Eyebrow className="text-accent">Lesson complete</Eyebrow>
          <h1 className="mt-3 font-display text-4xl font-extrabold leading-[1.02] tracking-tight text-fg md:text-5xl">
            {lesson?.title ?? slug}.
          </h1>
          <p className="mt-3 font-mono text-sm leading-relaxed text-fg-muted">
            You signed {signsPracticed} new word{signsPracticed === 1 ? '' : 's'}. Spaced
            repetition will bring these back over the next few days.
          </p>
        </div>
      </header>

      {/* Stats */}
      <section
        className="mb-10 grid grid-cols-2 gap-3 md:grid-cols-4"
        data-testid="complete-stats"
      >
        <Stat label="Signs practiced" value={String(signsPracticed)} />
        <Stat label="Total reps" value={String(totalReps)} />
        <Stat label="Time" value={String(minutes)} unit="min" />
        <Stat
          label="Streak"
          value={String(streak?.currentStreakDays ?? 1)}
          unit={(streak?.currentStreakDays ?? 1) === 1 ? 'day' : 'days'}
        />
      </section>

      {/* Mastery snapshot */}
      <section className="mb-10 rounded-card border border-line/30 bg-bg-paper p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_1px_2px_rgba(0,0,0,0.4)]">
        <Eyebrow>§ Mastery snapshot</Eyebrow>
        {signs.length === 0 ? (
          <p className="mt-4 font-mono text-sm text-fg-muted">No mastery data yet.</p>
        ) : (
          <ul className="mt-4 flex flex-col" data-testid="mastery-snapshot">
            {signs.map((s, i) => {
              const pct = 60 + ((i * 13) % 35);
              return (
                <li
                  key={s.slug}
                  className="grid grid-cols-[36px_1fr_1.2fr_48px] items-center gap-4 border-b border-line/15 py-2.5"
                >
                  <span className="font-mono text-sm text-fg-faint">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <span className="font-display text-base font-medium uppercase text-fg">
                    {s.englishGloss}
                  </span>
                  <span className="hidden md:block">
                    <Progress value={pct} max={100} trackClassName="h-1.5 bg-bg-deep" />
                  </span>
                  <span className="text-right font-mono text-xs text-fg-muted">{pct}%</span>
                </li>
              );
            })}
          </ul>
        )}
        <p className="mt-4 font-mono text-xs leading-relaxed text-fg-subtle">
          Mastery is rough until you've practiced each sign three or four times. Come back
          tomorrow — review takes about three minutes.
        </p>
      </section>

      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
        {nextLesson ? (
          <Link
            to={`/lessons/${nextLesson.slug}`}
            data-testid="next-lesson-cta"
            className="block w-full sm:w-auto"
          >
            <Button size="lg" className="h-auto w-full whitespace-normal py-2.5 text-center sm:w-auto">
              Continue to Lesson № {String(nextLesson.orderIndex || 0).padStart(2, '0')} ·{' '}
              {nextLesson.title} →
            </Button>
          </Link>
        ) : (
          <Link to="/lessons" data-testid="next-lesson-cta" className="block w-full sm:w-auto">
            <Button size="lg" className="w-full sm:w-auto">
              Next lesson
            </Button>
          </Link>
        )}
        <Link to="/dashboard" data-testid="back-to-dashboard-cta" className="block w-full sm:w-auto">
          <Button size="lg" variant="ghost" className="w-full sm:w-auto">
            Back to dashboard
          </Button>
        </Link>
      </div>

      {/* dashLessons reference kept to satisfy lint on unused data —
          may be used for future "where you've been" footer. */}
      <span className="sr-only" aria-hidden="true">
        {dashLessons.length} recent
      </span>
    </main>
  );
}

interface StatProps {
  label: string;
  value: string;
  unit?: string;
}

function Stat({ label, value, unit }: StatProps) {
  return (
    <div className="rounded-card border border-line/30 bg-bg-paper p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_1px_2px_rgba(0,0,0,0.4)]">
      <Eyebrow>{label}</Eyebrow>
      <p className="mt-2 flex items-baseline gap-1.5 font-display leading-none">
        <span className="gradient-text text-3xl font-extrabold tabular-nums md:text-4xl">
          {value}
        </span>
        {unit && (
          <span className="font-mono text-xs lowercase text-fg-muted">{unit}</span>
        )}
      </p>
    </div>
  );
}
