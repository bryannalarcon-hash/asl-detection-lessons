# Step Indicator Patterns — Research

Brief: the drill flow on the practice screen renders three stages — Handshape → Movement → Sign — as a flat row of equal-weight dots and labels. Goal: connect them visually, push the active stage forward, push completed/upcoming stages back without making them invisible.

## Notable examples

### Stripe Checkout (and Connect onboarding)
Stripe does not use a numbered chevron stepper on the consumer-facing Checkout itself; the flow is a single page with conditional sections. Where they do use sequence indicators (Connect onboarding, Dashboard setup, Atlas), the pattern is consistently a **thin horizontal progress bar that fills as you advance** plus a short text label ("Step 2 of 4 — Verify identity"). No chevrons. The visual emphasis is "how far along am I," not "what are the named stages." Their public guidance for checkout UX explicitly recommends a finite tracker like `Shipping → Payment → Review` to reduce drop-off — i.e. arrow-separated text labels with no decorative dots.

### Linear's workflow statuses
Linear shows status as **a single small icon next to the issue title, not a chained row**. Each status has its own distinct glyph: dashed-circle (Backlog), empty-circle (Todo), partial-pie / clockwise-fill (In Progress), filled-circle-with-check (Done), red-circle-with-slash (Canceled). When you open the status picker, the workflow chain becomes a vertical list of those icons + labels — Linear never paints "Backlog → Todo → In Progress → Done" as a horizontal connected stepper. Lesson: Linear earns its clarity from **the icon itself carrying the state**, not from connectors. The icons are monochrome with a single accent fill at the current state.

### Vercel deployment pipeline
Vercel renders build steps as a **vertical timeline**: each row has a status pip (spinner / check / x / dash) on the left, a step name, and a duration on the right. Completed rows collapse to one line, the active row expands inline with live logs. No horizontal stepper, no chevrons. Hierarchy comes from (a) the pip glyph and (b) the active row being expanded while siblings are collapsed.

### Apple HIG — page controls / progress indicators
HIG covers two relevant patterns: **page controls** (the row of dots for paginated content) and **progress indicators** (determinate bars and spinners). For step-style sequences HIG leans on determinate bars with text labels. Page-control dots are deliberately tiny and low-contrast for non-active states; the active dot is a solid filled circle, inactive dots are ~30% opacity of the same color. No connecting line between dots.

### USWDS step-indicator (US government design system)
Most explicit spec found. Three states with prescribed contrast deltas:
- Pending segment: 40 grades lighter than background (visible, not disabled)
- Current segment: 20 grades lighter than completed color, plus bold text
- Completed segment: grade 60 or higher (full saturation)
Connectors are short horizontal **segment bars** between numbered counters, not chevrons. On mobile they collapse to a single "Step 2 of 3 — Movement" sentence with a one-line progress bar.

## Common patterns

| Pattern | Looks like | Best for | Drawback |
|---|---|---|---|
| Numbered dots + connector line | `(1)──(2)──(3)` | Forms, onboarding, anything ≥4 steps | Numbers feel bureaucratic for a 3-step flow |
| Pill + chevron | `[Handshape] › [Movement] › [Sign]` | Short, named stages where the name matters more than the position | Chevrons can read as breadcrumb (navigable history) — not what we want |
| Breadcrumb | `Handshape › Movement › Sign` (no pill) | Navigation, not progress | Implies clickable / "go back" |
| Tabs with future tabs disabled | underline on active, gray on rest | When each step is also a content panel | Looks like nav, not progress |
| Filling progress bar + label | `▰▰▰▱▱▱` "Movement" | Continuous progress, unknown step count | Loses the "named stages" affordance |

For three named, ordered, non-navigable stages, the strongest fits are **pill + connector** or **numbered dots + connector**. Chevron-only (breadcrumb) is the wrong semantic.

## Active / completed / upcoming distinction

Refactoring UI's rule: combine size + weight + color, but never max out all three on more than one element. Apply that here:

- **Completed** — accent-tinted dot or check glyph at ~60% accent, label at muted foreground. The dot color stays in the brand family (don't introduce green just to mean "done") — saturation drop is enough.
- **Active (you are here)** — full accent fill, slightly larger dot, label at full foreground weight + medium font-weight. A soft outer ring at 20–30% accent opacity creates the "glow" without breaking the minimal aesthetic. Stripe-style: ring instead of shadow.
- **Upcoming** — hollow dot with `#333` border, label at muted foreground (`~50%` opacity). Visible, never invisible — USWDS contrast guidance.

The connector segments inherit the same logic: segment to the left of a completed step is solid accent at 60%, segment to the left of the active step is solid accent at 100% up to the active dot then border-color past it, segments between upcoming steps are flat `#333`.

## Mobile fallback

Three options, in order of preference for our use case:

1. **Keep the row, drop the labels under the active dot only**. At <480px, hide the upcoming/completed labels and show only the active stage's label centered under the row. Dots + connectors remain. Cheap, preserves the spatial metaphor.
2. **Collapse to a sentence**: "Step 2 of 3 — Movement" with a thin progress bar. USWDS pattern. Safe, boring.
3. **Vertical stack**. Overkill for 3 steps; reserve for ≥5.

Option 1 fits our brand better — less chrome, preserves continuity with desktop.

## Recommendations for our drill indicator

- **Layout**: pill-less numbered dots with horizontal connector segments. Three filled circles (12–14px), 2px segments between them, total component height stays under 32px so it doesn't compete with the video frame. Order: Handshape → Movement → Sign, left to right.
- **Active state**: dot scales to 14px, solid `#4f46e5`, wrapped in a 2px ring at `rgba(79, 70, 229, 0.25)`. Label below the dot, `text-fg` color, `font-medium`. Subtle 200ms color transition when stage advances — no bounce, no scale animation (Linear-precise).
- **Completed state**: dot becomes a check glyph (`Check` icon at 10px) inside a filled `rgba(79, 70, 229, 0.6)` circle. Label drops to `text-fg-muted`. The check + desaturation together signals "done" without introducing a second accent color.
- **Upcoming state**: hollow 10px dot, 1px `#333` border, transparent fill. Label at `text-fg-muted` with `opacity-60`. Stays legible; never disabled-gray.
- **Connector**: 2px-tall segment between dots. Color: solid `#4f46e5` for segments behind completed/active dots, `#333` for segments ahead. The "fill line" reaches up to the center of the active dot — this is the single strongest "you are here" affordance and the main thing missing today. No chevrons; chevrons read as navigable breadcrumb.
- **Labels**: keep the uppercase mono-tracked treatment from the current implementation — it matches the Stripe-precise typography. Place labels below dots (not inline) so the row collapses cleanly on mobile and the active label can be the only one shown.
- **Mobile (<480px)**: hide non-active labels, center active label below the dot row. Dots + connector unchanged.
- **Accessibility**: keep `aria-current="step"` on the active dot, add `aria-label="completed"` / `aria-label="upcoming"` on the others, and wrap the whole component in `role="list"` with each step as `role="listitem"`. The current `data-testid` hooks stay.

Current file to modify: `/home/bryann/gauntlet/asl-learning/frontend/src/components/practice/DrillIndicator.tsx`.

## Sources

- [Apple HIG — Progress indicators](https://developer.apple.com/design/human-interface-guidelines/components/status/progress-indicators/)
- [USWDS Step indicator](https://designsystem.digital.gov/components/step-indicator/)
- [Linear Docs — Issue status / Configuring workflows](https://linear.app/docs/configuring-workflows)
- [Stripe — Checkout UI strategies](https://stripe.com/resources/more/checkout-ui-strategies-for-faster-and-more-intuitive-transactions)
- [Stripe Docs — Connect embedded onboarding](https://docs.stripe.com/connect/embedded-onboarding)
- [Vercel Docs — Deployments / Builds](https://vercel.com/docs/deployments)
- [Material UI — Stepper component](https://mui.com/material-ui/react-stepper/)
- [Radix Vue — Stepper](https://www.radix-vue.com/components/stepper)
- [Eleken — 32 Stepper UI Examples](https://www.eleken.co/blog-posts/stepper-ui-examples)
- [Smart Interface Design Patterns — Breadcrumbs UX](https://smart-interface-design-patterns.com/articles/breadcrumbs-ux/)
- [Refactoring UI — Hierarchy is Everything (Jacob Shannon notes)](https://jacobshannon.com/blog/books/refactoring-ui/hierarchy-is-everything/)
- [UX Movement — Steppers on Mobile Forms](https://uxmovement.com/mobile/how-to-display-steppers-on-mobile-forms/)
