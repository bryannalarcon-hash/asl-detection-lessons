# SuperBuilders (Austin) — Visual Identity Teardown

## Identity disambiguation

"SuperBuilders" is a generic-sounding name and several unrelated entities share variants of it. The one tied to our ASL Learning partner project is:

- **Legal/marketing entity:** SuperBuilders (also styled "Superbuilders") — a "foundry for transformative education companies"
- **Primary marketing site:** [https://www.superbuilders.school](https://www.superbuilders.school/) (the landing video splash, dark splash, "Fix education, everywhere" copy)
- **Product/team site:** [https://www.superbuilders.dev](https://www.superbuilders.dev/) (the React app the LinkedIn page lists as the official website)
- **Austin connection:** Their public events run out of "Gauntlet AI Headquarters, James H. Robertson Building, 416 N Congress Ave, Austin, TX 78701" — confirmed via [Luma event listing](https://luma.com/8hfh5h7s)
- **Origin story:** Founded/staffed by "trailblazing innovators from the first cohort of GauntletAI" ([source](https://www.superbuilders.school/)) — Gauntlet AI is the Austin elite-engineering bootcamp ([CBS Austin coverage](https://cbsaustin.com/news/local/inside-austins-gauntlet-ai-the-elite-bootcamp-forging-ai-first-builders))
- **What they actually build:** Hiring/engineering partner behind Alpha School, GT School, Texas Sports Academy, and Montessorium — per their [LinkedIn page](https://www.linkedin.com/company/superbuilders-edtech), mission: "accelerate educational outcomes for 1 billion kids"

**Ruled out as unrelated:**
- `super-builders.com` — Super Builders Inc., a San Jose, CA fencing/deck contractor (CA license #979937). Different industry, different geography. ([source](https://super-builders.com/))
- `superbuilders.com`, `superbuilders.io`, `joinsuperbuilders.com`, `superbuilders.co` — DNS unreachable or blank pages at time of investigation.

## Top-line aesthetic in one sentence

Two-headed identity: a **cinematic, dark, dreamlike marketing splash** with a hand-drawn-feeling icon mark on `superbuilders.school`, paired with a **stark, monospaced, terminal-flavored dark UI** on the product/team site `superbuilders.dev` — together reading as "engineers who care about education," not slick corporate edtech.

## Logo & wordmark

Two SVG assets are referenced from the splash page ([source HTML](https://www.superbuilders.school/)):

- `brand-white.svg` — the **wordmark "SuperBuilders"** in custom letterforms, all-white, drawn as filled paths (viewBox `0 0 2549 222`, very wide and slim). Not a standard webfont; it's been outlined into vector paths. The very wide aspect ratio (~11.5:1) means it's designed to span almost the entire viewport width as a banner-style mark.
- `logo.svg` — the **icon mark** (viewBox `0 0 804 853`). SVG `<g>` IDs are explicit and revealing: `hand-top`, `hand-bottom`, `star`, `star1`, `star2`. So the icon is two **cupped/curved hand shapes** (mirrored top and bottom, like an opening) with a **large central star + two smaller stars** between them. Everything is filled solid white. The hand silhouettes have organic, drawn curves rather than geometric construction — this is illustrative, not iconographic.

Both marks render in pure `#fff` against dark backgrounds, with heavy drop-shadows applied via CSS (`drop-shadow(0 0 20px rgba(0,0,0,0.8))` stacked with `drop-shadow(0 0 3px rgba(255,255,255,0.5))` for a subtle white glow). The shadow stack gives the logos a floating/embossed feel against the video background.

Favicons on the .dev site even differ by `prefers-color-scheme` (`favicon-light.ico` vs `favicon-dark.ico`) — they care about light/dark adaptation.

## Color palette

The two surfaces use overlapping but distinct palettes. Hex values are pulled directly from `superbuilders.school/css/style.css` and `superbuilders.dev/assets/index-SzlBmAOV.css`.

**Marketing splash (`superbuilders.school`):**
- `#1a1a1a` — darkest near-black, used for the splash gradient top and the footer
- `#333` — body background
- `#4a4a4a`, `#777777`, `#d0d0d0` — gray ramp used in the About section vertical gradient (top→bottom: light gray → mid → dark)
- `#fff` — primary text and logo fill
- `#aaa` — footer muted text
- `#000` — About section body text (on the gray gradient)
- A subtle **horizontal rainbow gradient at 5% opacity** overlays the About section (red → orange → yellow → green → blue → indigo → violet, each at `rgba(…, 0.05)`). It's nearly imperceptible but signals "diversity / spectrum / inclusion" without being loud. This is the closest thing they have to brand color beyond grayscale.

**Product/team site (`superbuilders.dev`):**
- `#1c1c1c` — primary body background (slightly warmer than .school's `#333`)
- `#eee` — primary text
- `#222`, `#333` — borders
- `#444` — input placeholder text
- `#555` — scrollbar hover
- `#666`, `#888`, `#bbb` — muted/secondary text tiers
- `#fff` — primary heading text & selection background
- `#0f0` — **terminal-green accent** (used sparingly for status/active state — classic CRT vibe)
- Tailwind `slate-900` (`#0f172a`), `slate-950` (`#020617`), `slate-800` (`#1e293b`) — dark surfaces and borders
- Tailwind `indigo-600` (`#4f46e5`), `indigo-500` (`#6366f1`), `indigo-400` (`#818cf8`) — the **interactive accent** (buttons, hover states, links)
- `red-500` (`#ef4444`) — error/destructive only

Both sites are **dark-mode-first**. The .school site has no light mode at all. The .dev site exposes light/dark favicons but the CSS hard-codes a dark body — light mode appears to be a future affordance, not shipped.

## Typography

**`superbuilders.school` (marketing):**
- `@import url('https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Mono:wght@400;700&display=swap')`
- Single typeface across everything: **Atkinson Hyperlegible Mono** (the Braille Institute's accessibility-optimized monospace). This is a deliberate, on-brand choice for an education company — "hyperlegible" is literally a readability advocacy typeface.
- Heading scale is **viewport-relative and dramatic**: `#about h2 { font-size: 10vh }` — about-page heading is 10% of viewport height, so ~96px on a 1080p screen. Body `#about p { font-size: 4vh }` — ~40px body copy. Mobile uses `clamp(2.5rem, 8vw, 4rem)` for headings and `clamp(1rem, 4vw, 1.5rem)` for body. Very generous, almost editorial sizing.
- `line-height: 1.6` on body. No tracking adjustments.

**`superbuilders.dev` (product):**
- `@import url('https://fonts.googleapis.com/css2?family=Space+Mono:ital,wght@0,400;0,700;1,400&display=swap')`
- `body { font-family: Space Mono, monospace }` — the **entire UI is monospaced**, including `code`, `kbd`, `samp`, `pre`. No proportional sans anywhere on the rendered surface (the Tailwind preflight fallback `ui-sans-serif, system-ui, sans-serif…` exists but isn't actually used by body styles).
- Type scale uses Tailwind defaults: `text-sm` (0.875rem), `text-lg` (1.125rem), `text-xl` (1.25rem), `md:text-2xl` (1.5rem). Compact, not editorial.
- Heavy use of `uppercase`, `tracking-widest` (`letter-spacing: 0.1em`), `tracking-tight` (`-0.025em`), and `font-bold` (700). Classic developer-tools / terminal label styling.

Both font choices are **monospaced** — Atkinson Hyperlegible Mono on marketing, Space Mono on product. This is a deliberate identity: SuperBuilders presents as an engineering team, not a design agency. Treat monospace as a brand requirement, not a stylistic option.

## Imagery & graphics

- **Marketing hero:** a **looping background video** (`assets/loop.mp4`) with a static `splashback.png` fallback. The fallback's embedded metadata describes "In the foreground, educational holograms float atop desks in a meadow. In the distance, kids fly kites" — an **AI-generated, painterly, hopeful, slightly surreal pastoral scene** with floating holographic UI (a flask, light bulb, bar chart, the equation E=mc², geometric primitives) hovering above old wooden school desks in a sunlit meadow with two large trees. The aesthetic is "Ghibli-meets-edtech-futurism," not photographic, not corporate stock.
- **Iconography:** Almost none visible on the marketing site. The single icon mark (hands + stars) is the only graphic element. On the product site, Tailwind classes for `h-4 w-4`, `h-5 w-5`, `h-8 w-8` suggest small inline icons — likely a standard developer icon set (Lucide / Heroicons style outlines), though the bundle minifies them away.
- **Signature motif:** **The cupped hands + stars mark** is the single repeatable graphic element — it reads as "lifting up, opening, surfacing potential." No gradients, no dot grids, no isometric, no 3D. The .school site's only "graphic motif" beyond the mark is the **5%-opacity rainbow horizontal gradient** layered on the About section.
- **No emoji** observed in marketing copy. No team photos. No stock photography. No illustrations beyond the AI hero scene.

## Layout & component patterns

**Marketing (`superbuilders.school`):**
- **Fullscreen-section scroll pattern.** Every section is `height: 100vh` with `padding: 40px 20px`. The user scrolls one full screen at a time. `scroll-behavior: smooth`.
- Content is **flex-centered**, no traditional grid. Width is `80%` on desktop / `90%` mobile for the About text block.
- **No buttons, no cards, no forms** on the marketing surface. Single subtle link style: inherited color, underlined, `opacity: 0.7` on hover. Zero CTA pressure.
- **Animation:** 3-second `fadeInCompanyName` opacity animation on logo entry. Hardware-accelerated (`will-change: filter, opacity; transform: translateZ(0)`). Heavy stacked `drop-shadow` filters on the logo for a luminous-mark effect. Background video supplies all other motion.

**Product (`superbuilders.dev`):**
- Container max-widths: `max-w-xl` (36rem), `max-w-2xl` (42rem), `max-w-5xl` (64rem), and a custom `max-w-[1400px]` for the widest layout. Centered with `mx-auto`.
- **Grid:** `grid-cols-1 md:grid-cols-2` — simple 1-up to 2-up at the `md` (768px) breakpoint. Generous gaps (`gap-6`, `gap-8`, `gap-12`).
- **Card style:** `rounded-[2rem]` (very rounded — 32px corners), `border` (1px), `border-[#333]` or `border-slate-800`, `bg-[#1c1c1c]` or `bg-slate-900`. Soft `shadow-2xl` (`0 25px 50px -12px rgba(0,0,0,0.25)`) on elevated surfaces. No glassmorphism beyond a single `backdrop-blur-md` on a `bg-slate-950/80` sticky nav.
- **Button style:** Indigo (`bg-indigo-600`, `group-hover:bg-indigo-500`), white text, `transition-colors duration-700`. Border-radius defaults to `.25rem` for inputs but the cards reach `2rem` — a deliberate **small-radius-on-controls / huge-radius-on-containers** dichotomy.
- **Form/input style:** Borderless or thin-bordered, `placeholder-[#444]`, monospace, dark background, no fills.
- **Motion:** `animate-pulse` (loading), `transition-all`, `duration-700`. Restrained — no bouncing, no parallax, no Lottie. Long durations (700ms) give it a deliberate, considered feel rather than a snappy SaaS feel.

## Partner project visual cues (light touch)

The .school splash links externally only to [gauntletai.com](https://www.gauntletai.com) — no visible project case-study gallery on the marketing surface yet (the source HTML has the comment `<!-- New individual project panels will go here later -->`, so the case-study section is **planned but not built**). The portfolio-agent investigation will need to look at `superbuilders.dev` directly and at the LinkedIn employee posts for examples of partner-project visual style. From `.dev`'s component patterns above, partner projects are likely presented as **dark, mono-typed, rounded-card grids** rather than as glossy marketing pages.

## How our ASL app should align

Five concrete recommendations grounded in the evidence above:

1. **Adopt a dark-mode-first palette anchored on `#1c1c1c` (background) + `#eee` (text), with `indigo-600` (`#4f46e5`) as the primary interactive accent and `#0f0` reserved for status/success states.** Use the `#222`/`#333` border tier and `#666`/`#888`/`#bbb` muted-text ramp. This is a direct, defensible match to `superbuilders.dev`.
2. **Pick a monospace as the body typeface.** Either **Space Mono** (matches `.dev`) or **Atkinson Hyperlegible Mono** (matches `.school` and is itself an accessibility typeface, perfect cover for an ASL/accessibility app). I'd lean Atkinson Hyperlegible Mono — it's the strongest brand alignment AND the most defensible a11y choice for a deaf-community-serving product.
3. **Use very-rounded containers (`border-radius: 2rem`) with thin 1px borders in `#333`, and small-radius (`0.25rem`) for inputs.** That radius dichotomy is the single most distinctive `.dev` shape language. Avoid pill buttons, avoid sharp corners.
4. **Lean into the cupped-hands-and-stars mark as conceptual scaffolding.** Don't copy the mark, but the gesture (open hands lifting something up) is on-theme for ASL and for accessibility. Avoid corporate iconography (filled rounded-rect tiles, gradient blobs); prefer outlined or simple white-on-dark glyphs.
5. **Mirror the section rhythm: oversized headings (clamp around `2.5rem`–`4rem`), generous vertical space (`min-h-[85vh]` for hero sections), all-uppercase tracking-widest labels for nav/eyebrow text.** Restrained motion — 700ms transitions, simple opacity fades, no parallax. Editorial pacing, not SaaS density.

## Open questions / could not verify

- **Is the .school splash the canonical brand surface, or is .dev?** LinkedIn lists `.dev` as the official site, but `.school` has the marketing video and tagline. Likely .dev is the post-launch team-and-projects portal while .school is the public mission landing. **UNVERIFIED whether one is being deprecated.**
- **Actual rendered shape of the wordmark.** I confirmed the SVG paths exist and fill white, but could not rasterize the SVG locally (no `rsvg-convert`/`cairosvg`/`inkscape` available in the sandbox). The wordmark letterforms — whether they're rounded, slabbed, geometric, or hand-drawn — are **UNVERIFIED visually**.
- **Twitter/X profile branding.** `x.com/Superbuilders` returned HTTP 402 to WebFetch; profile image and banner not captured. **UNVERIFIED**.
- **Light-mode design tokens.** The light favicon exists on `.dev` but the CSS only ships dark-mode body styles. Whether a light theme is planned (and what colors it would use) is **UNVERIFIED**.
- **Whether the rainbow horizontal gradient on `.school` About is intentional brand signal (Pride / spectrum / diversity) or designer flourish.** No public brand guide exists. **UNVERIFIED** — treat as suggestive, not authoritative.
- **Case-study / partner-project visual treatment.** The `.school` HTML has a commented-out projects section ("New individual project panels will go here later"). The portfolio-agent should look at `superbuilders.dev` (it's a React SPA so requires JS rendering — beyond what I could extract from the static bundle here).
