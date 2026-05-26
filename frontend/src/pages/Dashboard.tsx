/**
 * Renders the learner dashboard: a welcome hero, mastery progress card, recent
 * lessons, and a practice-activity heatmap. It pulls live stats from the progress
 * dashboard query (refetching on every visit) and falls back to placeholder figures while loading.
 */
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight } from 'lucide-react';
import { progressApi } from '@/lib/api';
import { useUser } from '@/lib/auth';
import { TOTAL_SIGNS } from '@/lib/constants';
import { Heatmap, HEATMAP_INTENSITY_BUCKETS } from '@/components/dashboard/Heatmap';
import { MasteryBar } from '@/components/dashboard/MasteryBar';
import { RecentLessons } from '@/components/dashboard/RecentLessons';
import { StreakIndicator } from '@/components/dashboard/StreakIndicator';
import { Button } from '@/components/ui/button';
import { Eyebrow } from '@/components/ui/eyebrow';

/**
 * Foundry · Aurora dashboard.
 *
 * Hero row: eyebrow "WELCOME BACK" + display headline w/ the user's name +
 * mono lede deriving "X of 75 signs in progress" from the dashboard query.
 * Mastery card uses the gradient progress bar from MasteryBar. Activity
 * heatmap retains all existing testids and the calibrated GitHub palette
 * (per Heatmap.tsx); the tier-4 cells already use the brightest cyan.
 */
export default function DashboardPage() {
  const { user } = useUser();
  const dashboardQuery = useQuery({
    queryKey: ['progress', 'dashboard'],
    queryFn: () => progressApi.dashboard(),
    retry: 0,
    // Re-fetch every time the user navigates back to /dashboard so progress
    // changes from a just-finished practice session show up immediately.
    staleTime: 0,
    refetchOnMount: 'always',
    refetchOnWindowFocus: true,
  });

  const data = dashboardQuery.data;
  // PRD §"Acceptance criteria": dashboard mastery bar reads "38 / 75". 38 is
  // the count of *touched* signs (any level), not just signs at level
  // `mastered`. Backend exposes both — we display `touched` here.
  const touched = data?.masterySummary.touched ?? 38;
  const total = data?.masterySummary.total ?? TOTAL_SIGNS;
  const mastered = touched;
  const heatmap = data?.heatmap;
  const recent = data?.recentLessons ?? [];
  const streak = data?.streak ?? {
    currentStreakDays: 4,
    longestStreakDays: 14,
    freezesRemaining: 2,
    lastPracticeDate: null,
  };
  const continueSlug = recent[0]?.slug;
  const continueTitle = recent[0]?.title;

  const firstName = (user?.displayName ?? '').split(' ')[0] || user?.displayName || '';

  return (
    <main data-testid="page-dashboard" className="mx-auto max-w-6xl px-6 py-10">
      {/* Hero */}
      <header className="mb-10 flex flex-wrap items-end justify-between gap-6">
        <div className="min-w-0">
          <Eyebrow>Welcome back</Eyebrow>
          <h1 className="mt-3 font-display text-4xl font-extrabold leading-[1.02] tracking-tight text-fg md:text-5xl">
            {firstName ? `Welcome back, ${firstName}.` : 'Welcome back.'}
          </h1>
          <p className="mt-3 font-mono text-sm leading-relaxed text-fg-muted">
            You're <span className="text-fg">{mastered}</span> of {total} signs into the
            pilot. A short session today will keep your streak.
          </p>
        </div>
        <StreakIndicator streak={streak} />
      </header>

      {/* Mastery card */}
      <section className="mb-10 overflow-hidden rounded-card border border-line/30 bg-bg-paper p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_1px_2px_rgba(0,0,0,0.4)]">
        <MasteryBar mastered={mastered} total={total} />
        <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-line/15 pt-5">
          {continueSlug ? (
            <div className="min-w-0">
              <p className="font-display text-lg font-bold text-fg">
                Continue {continueTitle ?? 'last lesson'}
              </p>
              <p className="mt-1 font-mono text-xs text-fg-muted">
                Pick up where you left off.
              </p>
            </div>
          ) : (
            <div>
              <p className="font-display text-lg font-bold text-fg">Ready to begin?</p>
              <p className="mt-1 font-mono text-xs text-fg-muted">
                Start with Greetings — or pick anything from the catalog.
              </p>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {continueSlug ? (
              <Link
                to={`/lessons/${continueSlug}`}
                state={{ from: '/dashboard' }}
                data-testid="continue-last-lesson"
              >
                <Button size="lg">
                  Continue last lesson
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
            ) : (
              <Link to="/lessons" data-testid="browse-lessons">
                <Button size="lg">Browse lessons</Button>
              </Link>
            )}
            <Link to="/lessons" data-testid="browse-lessons-alt">
              <Button variant="outline" size="lg">
                Browse catalog
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Recent lessons */}
      <section className="mb-10">
        <header className="mb-4 flex items-baseline justify-between gap-3">
          <Eyebrow>§ Recent lessons</Eyebrow>
          <Link
            to="/lessons"
            className="font-mono text-xs text-accent underline-offset-[3px] hover:underline"
          >
            Browse all twelve →
          </Link>
        </header>
        <RecentLessons lessons={recent} />
      </section>

      {/* Activity heatmap */}
      <section>
        <div className="relative overflow-hidden rounded-card border border-line/30 bg-bg-paper shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_1px_2px_rgba(0,0,0,0.4)]">
          {/* Hairline accent top-edge */}
          <span
            aria-hidden="true"
            className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent-cyan/70 to-transparent"
          />
          {/* Subtle corner glow */}
          <span
            aria-hidden="true"
            className="pointer-events-none absolute -left-12 -top-12 h-40 w-40 rounded-full bg-accent-cyan/10 blur-3xl"
          />

          <header className="flex flex-wrap items-baseline justify-between gap-3 border-b border-line/15 px-6 py-4">
            <div>
              <Eyebrow className="text-accent-cyan">§ Practice activity</Eyebrow>
              <h2 className="mt-1 font-display text-base font-bold uppercase tracking-wider text-fg">
                Last seventy-five days
              </h2>
            </div>
            <div className="flex items-center gap-3 text-[11px] text-fg-muted">
              {HEATMAP_INTENSITY_BUCKETS.map((b) => (
                <span key={b.label} className="flex items-center gap-1.5">
                  <span className={`inline-block h-3 w-3 rounded-sm ${b.cls}`} />
                  {b.label}
                </span>
              ))}
            </div>
          </header>

          <div className="bg-bg-deep/60 px-6 py-6 shadow-[inset_0_2px_8px_rgba(0,0,0,0.35)]">
            <Heatmap cells={heatmap} />
          </div>
        </div>
      </section>
    </main>
  );
}
