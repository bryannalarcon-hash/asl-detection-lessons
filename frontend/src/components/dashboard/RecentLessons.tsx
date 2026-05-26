/**
 * Horizontally scrolling strip of recent-lesson cards, each linking to its
 * lesson and showing a mastered-of-total progress bar. It manages slide
 * controls and edge fades that appear based on the scroller's scroll position.
 */
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Progress } from '@/components/ui/progress';
import { Eyebrow } from '@/components/ui/eyebrow';
import { cn } from '@/lib/utils';
import type { RecentLessonDto } from '@/lib/api';

interface RecentLessonsProps {
  lessons: RecentLessonDto[];
}

const SCROLL_AMOUNT = 240; // ~ one card

/**
 * Foundry · Aurora recent-lessons strip. Each card uses `bg-bg-paper` with
 * a subtle gradient overlay (`--grad-card`), 1px line border, soft hover
 * lift. Slide controls + edge fades preserved from the original layout.
 */
export function RecentLessons({ lessons }: RecentLessonsProps) {
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const [canLeft, setCanLeft] = useState(false);
  const [canRight, setCanRight] = useState(false);

  // Re-evaluate scroll affordances on layout + scroll.
  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const update = () => {
      setCanLeft(el.scrollLeft > 4);
      setCanRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 4);
    };
    update();
    el.addEventListener('scroll', update, { passive: true });
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => {
      el.removeEventListener('scroll', update);
      ro.disconnect();
    };
  }, [lessons.length]);

  const slide = (dir: 1 | -1) => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollBy({ left: dir * SCROLL_AMOUNT, behavior: 'smooth' });
  };

  if (lessons.length === 0) {
    return (
      <p data-testid="recent-lessons-empty" className="font-mono text-sm text-fg-muted">
        No recent lessons yet. Pick one from the catalog to get started.
      </p>
    );
  }
  return (
    <div className="relative">
      {/* Slide-left */}
      <button
        type="button"
        onClick={() => slide(-1)}
        disabled={!canLeft}
        aria-label="Scroll recent lessons left"
        data-testid="recent-lessons-prev"
        className={cn(
          'absolute left-0 top-1/2 z-10 -translate-y-1/2 -translate-x-2 rounded-full border border-line/30 bg-bg-paper p-1.5 text-fg-muted shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] transition-opacity duration-150',
          'hover:bg-bg-elev hover:border-line/60 hover:text-fg active:translate-y-[calc(-50%+1px)]',
          'focus-visible:outline-2 focus-visible:outline-accent-ring focus-visible:outline-offset-2',
          canLeft ? 'opacity-100' : 'pointer-events-none opacity-0'
        )}
      >
        <ChevronLeft className="h-4 w-4" />
      </button>

      {/* Slide-right */}
      <button
        type="button"
        onClick={() => slide(1)}
        disabled={!canRight}
        aria-label="Scroll recent lessons right"
        data-testid="recent-lessons-next"
        className={cn(
          'absolute right-0 top-1/2 z-10 -translate-y-1/2 translate-x-2 rounded-full border border-line/30 bg-bg-paper p-1.5 text-fg-muted shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] transition-opacity duration-150',
          'hover:bg-bg-elev hover:border-line/60 hover:text-fg active:translate-y-[calc(-50%+1px)]',
          'focus-visible:outline-2 focus-visible:outline-accent-ring focus-visible:outline-offset-2',
          canRight ? 'opacity-100' : 'pointer-events-none opacity-0'
        )}
      >
        <ChevronRight className="h-4 w-4" />
      </button>

      {/* Edge fades */}
      <div
        aria-hidden="true"
        className={cn(
          'pointer-events-none absolute inset-y-0 left-0 z-[5] w-8 bg-gradient-to-r from-bg to-transparent transition-opacity',
          canLeft ? 'opacity-100' : 'opacity-0'
        )}
      />
      <div
        aria-hidden="true"
        className={cn(
          'pointer-events-none absolute inset-y-0 right-0 z-[5] w-8 bg-gradient-to-l from-bg to-transparent transition-opacity',
          canRight ? 'opacity-100' : 'opacity-0'
        )}
      />

      <div
        ref={scrollerRef}
        data-testid="recent-lessons"
        className="flex gap-4 overflow-x-auto scroll-smooth pb-2 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {lessons.map((lesson) => {
          const pct = lesson.signCount
            ? Math.round((lesson.masteredCount / lesson.signCount) * 100)
            : 0;
          return (
            <Link
              key={lesson.slug}
              to={`/lessons/${lesson.slug}`}
              data-testid="recent-lesson-card"
              className="group relative block min-w-[15rem] flex-shrink-0 overflow-hidden rounded-card border border-line/30 bg-bg-paper p-5 transition-[border-color,transform,box-shadow] duration-150 ease-out hover:-translate-y-px hover:border-line/60 hover:shadow-[0_8px_24px_rgba(0,0,0,0.35)] focus-visible:outline-2 focus-visible:outline-accent-ring focus-visible:outline-offset-2 motion-reduce:transition-none motion-reduce:hover:translate-y-0"
            >
              {/* Gradient overlay (cyan→violet at low alpha) */}
              <span
                aria-hidden="true"
                className="pointer-events-none absolute inset-0"
                style={{ background: 'var(--grad-card)' }}
              />
              <div className="relative space-y-3">
                <Eyebrow className="text-accent">{lesson.category}</Eyebrow>
                <h3 className="font-display text-base font-bold leading-tight text-fg">
                  {lesson.title}
                </h3>
                <p className="font-mono text-xs text-fg-muted">
                  {lesson.masteredCount} / {lesson.signCount} signs · {pct}%
                </p>
                <Progress
                  value={pct}
                  max={100}
                  aria-label={`${lesson.title} progress: ${lesson.masteredCount} of ${lesson.signCount} signs mastered`}
                />
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
