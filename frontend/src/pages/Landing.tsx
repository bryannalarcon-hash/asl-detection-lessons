/**
 * Renders the public landing page: a marketing hero pitching camera-based ASL
 * practice, value-prop highlights, sign-in/sign-up CTAs, and a footer of legal links.
 * It is the unauthenticated entry point to the app.
 */
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Eyebrow } from '@/components/ui/eyebrow';

/**
 * Foundry · Aurora landing screen.
 *
 * Centered hero with two corner glows (cyan from top-right, violet from
 * bottom-left), an eyebrow stripe, a huge display headline, a mono lede,
 * a bordered bullet list (the "specimen page" pattern from the design
 * handoff), and the dual gradient/outlined CTA pair.
 *
 * Layering: glow divs are `absolute · pointer-events-none · z-0`; the
 * hero content sits at `relative · z-1` so it stays on top.
 */
export default function LandingPage() {
  return (
    <main data-testid="page-landing" className="flex min-h-screen flex-col bg-bg text-fg">
      <section className="relative isolate overflow-hidden">
        {/* Corner glow A — cyan, top-right */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-32 -top-32 z-0 h-[34rem] w-[34rem]"
          style={{ background: 'var(--grad-glow-a)' }}
        />
        {/* Corner glow B — violet, bottom-left */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-40 -left-32 z-0 h-[36rem] w-[36rem]"
          style={{ background: 'var(--grad-glow-b)' }}
        />

        <div className="relative z-10 mx-auto flex max-w-4xl flex-col items-start gap-8 px-6 py-24 md:py-32">
          <Eyebrow>A Superbuilders project · Made in Austin, TX</Eyebrow>

          <h1 className="font-display text-hero font-extrabold uppercase leading-[0.95] tracking-tight text-fg">
            Practice <span className="gradient-text">ASL</span> with your camera.
          </h1>

          <p className="max-w-2xl font-mono text-base leading-relaxed text-fg-muted md:text-lg">
            Seventy-five foundational signs. A camera-aware practice loop. Reference video
            from Deaf instructors. Self-paced, private, and yours to repeat as often as it
            takes.
          </p>

          <ul className="grid w-full max-w-2xl gap-px border-y border-line/30 bg-line/10 text-sm md:grid-cols-3">
            <li className="bg-bg/40 px-4 py-3 font-mono text-fg-muted">
              <span className="block text-[0.7rem] uppercase tracking-[0.18em] text-fg-subtle">
                Private
              </span>
              <span className="mt-1 block text-fg">Video stays on your device.</span>
            </li>
            <li className="bg-bg/40 px-4 py-3 font-mono text-fg-muted">
              <span className="block text-[0.7rem] uppercase tracking-[0.18em] text-fg-subtle">
                Self-paced
              </span>
              <span className="mt-1 block text-fg">Practice on your own schedule.</span>
            </li>
            <li className="bg-bg/40 px-4 py-3 font-mono text-fg-muted">
              <span className="block text-[0.7rem] uppercase tracking-[0.18em] text-fg-subtle">
                Original
              </span>
              <span className="mt-1 block text-fg">From-scratch model, trained by us.</span>
            </li>
          </ul>

          <div className="flex flex-wrap gap-3">
            <Link to="/signin" data-testid="cta-sign-in">
              <Button size="lg">Sign in</Button>
            </Link>
            <Link to="/signup" data-testid="cta-sign-up">
              <Button size="lg" variant="outline">
                Create an account
              </Button>
            </Link>
          </div>

          <p className="max-w-2xl font-mono text-xs leading-relaxed text-fg-subtle">
            <span className="text-accent">¹</span> This is vocabulary practice, not full
            ASL. For grammar, conversation, and fluency, study with a Deaf instructor.
          </p>
        </div>
      </section>

      <footer className="mt-auto border-t border-line/30 bg-bg-deep/40">
        <div className="mx-auto flex max-w-4xl flex-wrap gap-6 px-6 py-6 font-mono text-xs uppercase tracking-[0.18em] text-fg-subtle">
          <Link to="/privacy" className="hover:text-fg">
            Privacy
          </Link>
          <Link to="/about" className="hover:text-fg">
            About
          </Link>
          <Link to="/help" className="hover:text-fg">
            Help
          </Link>
        </div>
      </footer>
    </main>
  );
}
