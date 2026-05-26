/**
 * Renders the lessons catalog: a searchable, category-filterable list of lessons
 * fetched from the lessons API, each linking to its detail page. It falls back to a
 * fixed category list and an empty-state message when the backend is unreachable.
 */
import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { lessonsApi } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Eyebrow } from '@/components/ui/eyebrow';

const FALLBACK_CATEGORIES = [
  'All',
  'Greetings',
  'Numbers',
  'Family',
  'Feelings',
  'Food',
  'Time',
  'Places',
  'Verbs',
  'Question Words',
];

/**
 * Foundry · Aurora lessons catalog.
 *
 * Eyebrow "LESSONS" + display headline + lede.
 * Each lesson row is a single "field manual" card: ordinal mono number,
 * display lesson title, sign chips (`bg-bg-elev rounded-full mono`), and
 * a right-arrow that translates 4px right + colors to accent on hover.
 */
export default function LessonCatalogPage() {
  const lessonsQuery = useQuery({
    queryKey: ['lessons', 'list'],
    queryFn: () => lessonsApi.list(),
    retry: 0,
    refetchOnWindowFocus: false,
  });

  const [category, setCategory] = useState('All');
  const [search, setSearch] = useState('');

  const lessons = lessonsQuery.data?.lessons ?? [];

  const filtered = useMemo(() => {
    return lessons.filter((l) => {
      const matchesCategory = category === 'All' || l.category === category;
      const q = search.trim().toLowerCase();
      const matchesSearch =
        q.length === 0 ||
        l.title.toLowerCase().includes(q) ||
        l.category.toLowerCase().includes(q);
      return matchesCategory && matchesSearch;
    });
  }, [lessons, category, search]);

  const categories = useMemo(() => {
    const set = new Set(['All', ...lessons.map((l) => l.category)]);
    return Array.from(set.size > 1 ? set : new Set(FALLBACK_CATEGORIES));
  }, [lessons]);

  return (
    <main data-testid="page-lessons" className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-8 max-w-2xl">
        <Eyebrow>Lessons</Eyebrow>
        <h1 className="mt-3 font-display text-4xl font-extrabold leading-[1.02] tracking-tight text-fg md:text-5xl">
          Browse the catalog.
        </h1>
        <p className="mt-4 font-mono text-sm leading-relaxed text-fg-muted">
          Twelve lessons. Seventy-five signs. Take them in any order — we recommend
          starting with Greetings, but follow your curiosity.
        </p>
      </header>

      <div className="mb-8 flex flex-col gap-3">
        <Input
          placeholder="Search lessons or signs…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          data-testid="lesson-search"
          className="h-10 max-w-md bg-bg-paper focus-visible:border-accent focus-visible:ring-[3px] focus-visible:ring-accent/20"
        />
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Categories">
          {categories.map((cat) => (
            <button
              key={cat}
              type="button"
              data-testid={`category-filter-${cat.toLowerCase().replace(/\s+/g, '-')}`}
              onClick={() => setCategory(cat)}
              role="tab"
              aria-selected={category === cat}
              className={`rounded-full border px-3 py-1 font-mono text-xs transition-colors ${
                category === cat
                  ? 'border-fg bg-fg text-bg-paper'
                  : 'border-line/30 text-fg-muted hover:text-fg hover:border-line/60'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {lessonsQuery.isLoading && (
        <p className="font-mono text-sm text-fg-muted" data-testid="lessons-loading">
          Loading lessons…
        </p>
      )}

      {!lessonsQuery.isLoading && filtered.length === 0 && (
        <p data-testid="lessons-empty" className="font-mono text-sm text-fg-muted">
          {lessons.length === 0
            ? 'Backend not reachable. Lessons will appear once the API is online.'
            : 'No lessons match your filters.'}
        </p>
      )}

      <div className="flex flex-col gap-px overflow-hidden rounded-card border-y border-line/30 bg-line/10">
        {filtered.map((lesson) => {
          const slugTestId = `lesson-card-${lesson.slug}`;
          return (
            <Link
              key={lesson.slug}
              to={`/lessons/${lesson.slug}`}
              data-testid="lesson-card"
              data-lesson-slug={lesson.slug}
              className="group grid grid-cols-[60px_1fr_auto_32px] items-center gap-6 bg-bg px-4 py-5 transition-colors hover:bg-bg-paper md:grid-cols-[80px_1fr_auto_32px]"
            >
              <span
                data-testid={slugTestId}
                className="font-mono text-xs uppercase tracking-[0.04em] text-accent"
              >
                № {String(lesson.orderIndex || 0).padStart(2, '0')}
              </span>
              <div className="min-w-0">
                <Eyebrow>{lesson.category}</Eyebrow>
                <h3 className="mt-1 font-display text-xl font-bold leading-tight text-fg">
                  {lesson.title}
                </h3>
                <p className="mt-2 flex flex-wrap gap-1.5">
                  <span className="rounded-full bg-bg-elev px-3 py-1 font-mono text-[0.7rem] uppercase tracking-[0.04em] text-fg-subtle">
                    {lesson.signCount} signs
                  </span>
                  <span className="rounded-full bg-bg-elev px-3 py-1 font-mono text-[0.7rem] uppercase tracking-[0.04em] text-fg-subtle">
                    ~{lesson.signCount * 3} min
                  </span>
                </p>
              </div>
              <div className="hidden text-right font-mono text-xs leading-relaxed text-fg-subtle md:block">
                {lesson.signCount} signs
                <br />~{lesson.signCount * 3} min
              </div>
              <span className="text-lg text-fg-faint transition-[transform,color] duration-150 group-hover:translate-x-1 group-hover:text-accent">
                →
              </span>
            </Link>
          );
        })}
      </div>
    </main>
  );
}
