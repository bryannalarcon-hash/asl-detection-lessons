# Heatmap Polish — Research

## How GitHub does it today (with specifics)

GitHub's contribution graph is the reference point. In dark mode it uses a five-step palette wired to CSS variables of the form `--color-calendar-graph-day-Ln-bg`:

- Level 0 (no contributions): `#161b22`
- Level 1: `#0e4429`
- Level 2: `#006d32`
- Level 3: `#26a641`
- Level 4: `#39d353`

Each cell is an SVG `<rect>` with a 2px rounded corner, sized roughly 10×10px with 3px gaps, and a 1px inner stroke (`outline: 1px solid rgba(27, 31, 35, 0.06)` in light mode; in dark mode it's a near-transparent white). The stroke is what keeps zero-cells from disappearing into the page background — a critical detail for our `#252525` base.

The intensity thresholds are not fixed counts; GitHub recomputes quartiles per user over the trailing 365 days after stripping outliers, so the scale is personal and adaptive.

Hover behavior is restrained: GitHub does *not* scale or animate the cell. It paints a 2px outline using `--color-calendar-halloween-graph-day-L1-border` (or the dark-mode equivalent, a soft white), and a JS-driven tooltip pops above with `N contributions on <date>`. There is no first-paint stagger animation — cells render synchronously from server-rendered SVG.

The "today" cell is *not* visually distinguished. The current week sits at the right edge, which is the only positional cue.

## Notable variants (Vercel / Linear / Cal.com etc.)

**GitLab** uses the same 5-step square grid but with a flatter green-to-teal ramp and a darker zero state; hover is a 1px outline and a tooltip. Functionally identical to GitHub, slightly less contrast.

**GitLens (VS Code)** renders the graph inline in a sidebar; cells are 8×8px with no border, relying on darker zero cells against the editor chrome. Hover changes the cell's `cursor` and shows a tooltip — no visual transform.

**npm package activity graph** uses a smaller 12-week window with bars rather than a true heatmap; weak comparison.

**Vercel Analytics** doesn't ship a calendar heatmap; its time-series panels use line charts with hover crosshairs. The relevant pattern is its hover treatment: a 1px indigo guide line, value labels in a small floating chip with `backdrop-filter: blur(8px)`, and no cell scaling. Restraint over motion.

**Linear's cycle graph** (the burndown / scope view) uses subtle gradients on bar fills, a vertical "today" line in indigo, and a focused dot on hover. The "today" indicator is the strongest pattern worth borrowing — a single-pixel accent line rather than a full cell change.

**Cal.com booking density** (and `cal-heatmap`) uses a 7-row weekday grid with rounded squares; hover is a tooltip + 2px outline in the brand color. Empty future days are rendered with `opacity: 0.3` on the zero color — a clean way to distinguish "no data yet" from "zero reps".

Subjectively, none of these feels dramatically better than GitHub. The biggest wins come from (a) brighter top-end greens in dark mode (GitHub's `#39d353` is noticeably more vivid than our `#00ff00 @ full`), (b) a real "today" marker, and (c) tooltip polish.

## Hover, focus, animation patterns

Consensus across the references:

- **Don't scale cells on hover.** Our current `hover:scale-110` is the outlier; GitHub, GitLab, Linear, and Cal.com all keep cells stationary and use an outline or color shift instead. Scaling makes the grid feel jittery and breaks alignment.
- **Use a 1–2px outline** in the brand accent (`#4f46e5` for us) with a fast transition (120–150ms ease-out).
- **Tooltip on hover and focus**, not just `title`. Native `title` is slow (~700ms delay), unstyled, and unreliable on touch. A custom popover anchored to the cell using `position: fixed` + Radix Popover or Floating UI fits the Linear-minimal aesthetic.
- **First-paint animation**: a stagger looks good *once* but is annoying on every dashboard load. The right call is a single 200–300ms opacity fade on mount with a tiny stagger (5–10ms per column, left-to-right) only on the *first* mount per session, gated behind `prefers-reduced-motion`.

## Streak window emphasis

None of the major contribution graphs highlight streaks directly. Duolingo's streak calendar is the closest reference: continuous days get a connecting orange bar that overlays the cells. Translating that to a square grid:

- A connecting "underline" — a 2px line in `status-ok` running beneath the active streak cells.
- Or a slightly thicker top-and-bottom border on cells that are part of an active streak (≥3 consecutive non-zero days).
- Or a subtle inner glow (`box-shadow: inset 0 0 0 1px rgba(0,255,0,0.4)`) on streak cells.

Inner glow is the lowest-risk option — it reads at a glance without adding geometry that fights the grid.

## Today's cell

Strongest single change. GitHub doesn't do this; we should. Options:

- **Indigo 1.5px ring** (`outline: 1.5px solid #4f46e5; outline-offset: 1px`). Static, clear, matches our accent rules.
- **Pulsing dot** in the cell corner — too noisy for a Stripe-precise brand.
- **Filled indigo border** with the intensity color visible inside. Clean, very Linear.

Go with the static indigo ring. Pulsing animation is on-brand for Duolingo, off-brand for us.

## Recommendations for our heatmap

- **Empty days (no data / future)**: render at 40% opacity of the zero-intensity color (`bg-bg-elevated` at `opacity-40`) with no border. Distinguishes "haven't started" or "future" from "practiced zero today." Add `aria-label="No data"` instead of "0 reps."
- **Intensity 1/2/3 colors and treatment**: drop the raw `#00ff00` CRT-green at low opacity — it reads as gray-green and feels flat. Use a calibrated ramp instead: L0 `#252525`, L1 `#0e4429`, L2 `#15803d`, L3 `#22c55e`. These are GitHub-derived but shifted toward our brighter top. Add a 1px inner border `rgba(255,255,255,0.04)` on all cells to keep edges crisp on dark.
- **Hover**: remove `scale-110`. Replace with `outline: 1.5px solid #4f46e5; outline-offset: 1px` and a 120ms transition. Add a real popover (Radix) showing date, rep count, and accuracy if available. Keep `cursor: pointer` only if the cell is clickable to a detail view; otherwise `cursor: default`.
- **Today**: persistent 1.5px indigo ring (`#4f46e5`) on the current-day cell. No animation. Add `aria-current="date"`.
- **Streak**: when 3+ consecutive non-zero days exist, apply `box-shadow: inset 0 0 0 1px rgba(34,197,94,0.5)` to those cells. No connecting line — keep the grid geometry clean.
- **First-paint animation**: 200ms opacity fade from 0 → 1 with a 6ms-per-column stagger left-to-right, only on initial mount (use a ref flag), gated by `prefers-reduced-motion: reduce`. Don't replay on data updates.
- **Focus state**: keep current `focus-visible:ring-2 ring-ring`, but match the hover outline color (indigo) so keyboard and mouse paths feel unified.
- **Accessibility**: keep the `role="grid"` / `role="row"` / `role="gridcell"` structure already in place. Add `aria-describedby` pointing to a visually-hidden legend so screen readers announce intensity levels. Empty days announce as "No data" rather than "0 reps."

## Sources

- [Contribution graph color pallets — github/community Discussion #7078](https://github.com/orgs/community/discussions/7078)
- [Contribution graph colors shade — github/community Discussion #51010](https://github.com/orgs/community/discussions/51010)
- [Color coding of Contribution Graph — github/community Discussion #23261](https://github.com/orgs/community/discussions/23261)
- [williambelle/github-contribution-color-graph (CSS variable names)](https://github.com/williambelle/github-contribution-color-graph)
- [Linear — Insights](https://linear.app/insights) and [Cycle graph docs](https://linear.app/docs/cycle-graph)
- [Vercel Web Analytics](https://vercel.com/docs/analytics)
- [Cal-Heatmap library](https://cal-heatmap.com/) and [wa0x6e/cal-heatmap on GitHub](https://github.com/wa0x6e/cal-heatmap)
- [Duolingo Streak System breakdown — Medium](https://medium.com/@salamprem49/duolingo-streak-system-detailed-breakdown-design-flow-886f591c953f)
- [kevinsqi/react-calendar-heatmap (className conventions)](https://github.com/kevinsqi/react-calendar-heatmap)
- [Designing for data visualization's quiet moments (empty vs zero) — Medium](https://medium.com/@prernashaurya1/filling-the-void-designing-for-data-visualizations-quiet-moments-ec7dff31b8f5)
- [Accessibility-First Approach to Chart Visual Design — Smashing Magazine](https://www.smashingmagazine.com/2022/07/accessibility-first-approach-chart-visual-design/)
- [How to make interactive charts accessible — Deque](https://www.deque.com/blog/how-to-make-interactive-charts-accessible/)
- [React animate fade on mount — Josh Comeau](https://www.joshwcomeau.com/snippets/react-components/fade-in/)
