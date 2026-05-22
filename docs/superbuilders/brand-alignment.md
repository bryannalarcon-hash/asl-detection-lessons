# SuperBuilders Brand Alignment — Synthesis

Cross-synthesis of the three teardowns in this directory: [visual-identity.md](./visual-identity.md), [brand-voice.md](./brand-voice.md), [portfolio.md](./portfolio.md). Produces concrete design tokens and copy patterns to apply to our ASL pilot.

---

## Who SuperBuilders is — confirmed

- **Austin, TX edtech engineering team** ("foundry"), located at Gauntlet AI HQ on N Congress Ave
- Staffed by **GauntletAI cohort-1 alumni**
- Builds production software for four named partner schools: **Alpha School, GT School, Texas Sports Academy, Montessorium**
- Mission: **"Fix education, everywhere."** (signature phrase + "1 billion kids" framing)
- Two public web surfaces:
  - [`superbuilders.school`](https://www.superbuilders.school/) — marketing splash
  - [`superbuilders.dev`](https://www.superbuilders.dev/) — product / team site
- **33 public repos** on [github.com/superbuilders](https://github.com/superbuilders)
- Disambiguated from `super-builders.com` (San Jose fencing contractor) — unrelated

---

## The critical insight: two-tier visual system

The visual identity teardown and the portfolio teardown disagreed at first read. They actually describe **two different brand surfaces**:

| Tier | What it is | Aesthetic |
|---|---|---|
| **SuperBuilders' own brand** | `superbuilders.school` + `.dev`, GitHub org, internal/recruiting materials | Dark mode, all-monospaced, indigo `#4f46e5` + CRT-green `#0f0`, `2rem` rounded cards, single AI-painterly hero |
| **Partner-project brands** | Alpha Dash, Khan-TimeBack, GT Anywhere, Montessorium, Texas Sports Academy | **No shared template** — each partner brand stands alone with its own colors, fonts, layout |

Our ASL pilot is **not a partner-school project** in the Alpha/GT/TSA/Montessorium sense. It's a **direct SuperBuilders pilot** (per the brief title "Superbuilders Partner Project — ASL Learning with Computer Vision"). That means we have two defensible paths:

### Path A — Adopt SuperBuilders' own brand (recommended)

We're a SuperBuilders project without a third-party partner identity to inherit. Visually belonging to SuperBuilders' portfolio makes the app feel like part of their foundry output.

### Path B — Treat ourselves as a partner-style project with a new sub-brand

Mirror Khan-TimeBack's pattern: pick a custom display font + Inter body, design our own palette, no SuperBuilders styling. Closer to how Alpha School or GT School branding works.

**Recommendation: Path A.** Reasons:
1. We don't have a learner-facing brand owner (no "Alpha School" of our own)
2. SuperBuilders has a strong, concrete visual identity we can adopt cleanly
3. The pilot is meant to be showcased as SuperBuilders' work
4. The dark-mono-indigo system aligns well with our adult college audience tone (the Linear/Notion quiet aesthetic we already committed to)
5. Atkinson Hyperlegible Mono is genuinely the best typeface choice for a learning app from an accessibility standpoint

---

## Design tokens — apply directly to Tailwind config

```ts
// tailwind.config.ts — recommended additions
export default {
  theme: {
    extend: {
      colors: {
        // Background scale (dark-mode-first)
        bg: {
          DEFAULT: '#1c1c1c',  // body
          elevated: '#252525', // cards
          deepest: '#0f0f0f',  // gutters
        },
        fg: {
          DEFAULT: '#eeeeee',  // primary text
          muted: '#9a9a9a',    // secondary text
          subtle: '#666666',   // tertiary
        },
        border: {
          DEFAULT: '#333333',  // card borders, dividers
          strong: '#555555',   // focus rings, hover states
        },
        // Interactive accent — primary brand color
        accent: {
          DEFAULT: '#4f46e5',  // indigo-600
          hover: '#6366f1',    // indigo-500
          ring: '#818cf8',     // indigo-400 — focus ring
          // Secondary accent: mirrors the SuperBuilders hero hologram glow.
          // Used ONLY for data-viz highlights (heatmap today, drill markers,
          // completion toasts) — never on general interactive UI.
          cyan: '#06b6d4',
          'cyan-bright': '#22d3ee',
        },
        // Status colors — used sparingly
        status: {
          ok: '#00ff00',       // CRT-green — pass / mastery-met
          warn: '#fbbf24',     // amber — retry / not-yet
          // No red — we don't use failure framing per principles.md
        },
      },
      fontFamily: {
        // Atkinson Hyperlegible (proportional) for sans + JetBrains Mono for mono.
        // The "Atkinson Hyperlegible Mono" variant suggested by earlier research
        // does NOT exist as a published font — corrected post-scaffold.
        // Bungee added for the chunky SB-style display headings (hero, logo).
        sans: ['"Atkinson Hyperlegible"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
        display: ['Bungee', '"Atkinson Hyperlegible"', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        // SuperBuilders' signature very-rounded cards
        card: '2rem',
        button: '0.75rem',
      },
      fontSize: {
        // Oversized viewport-relative headings per SB marketing patterns
        hero: ['clamp(2.5rem, 6vw, 5rem)', { lineHeight: '1.05' }],
        h1: ['clamp(1.75rem, 3vw, 2.5rem)', { lineHeight: '1.15' }],
      },
    },
  },
};
```

### Why this typeface choice is load-bearing

Switching our spec from Inter to **Atkinson Hyperlegible Mono** is a real change. Justifications:

1. **On brand**: SuperBuilders' own marketing uses it. Their `.dev` site uses Space Mono — also a monospace. The all-monospaced convention is consistent.
2. **Accessibility**: Designed by the Braille Institute to maximize letterform distinctiveness (the `1/l/I/0/O` problem is solved by design). For an app with English vocab labels next to ASL signs, this is a real win.
3. **Free + open**: Released under SIL Open Font License. Self-hostable, no Google Fonts dependency, no CDN-blocked-in-classroom risk.
4. **Distinctive without being precious**: monospaced typography reads as "engineering-serious," matching SuperBuilders' tonal register and avoiding the Duolingo-cute trap we explicitly rejected.

The only tradeoff: monospaced body text reads slower than proportional fonts at long-form lengths. Since our app is mostly **short labels** (sign names, drill labels, button text, microcopy) and **camera/video content**, the slowness penalty is minimal.

---

## Voice tokens — apply to the microcopy bank

From [brand-voice.md](./brand-voice.md), our microcopy should:

| Do | Avoid |
|---|---|
| Declarative sentences ("Locked in.") | Exclamation marks (zero across SB material) |
| Modal verbs in requirements ("The app must...") | Adjective stacks ("an amazing, beautiful, revolutionary app") |
| Hyphens (`-`) | Em-dashes (`—`) **outside formal docs** (this brand-alignment doc and principles.md use em-dashes; learner-facing UI uses hyphens) |
| Sentence case in UI ("Sign in") | Title Case in UI ("Sign In") |
| Oxford commas | Inconsistent comma placement |
| Contractions ("don't", "we'll") | Stiff longform ("do not", "we will") |
| Concrete nouns ("handshape", "movement") | Vague verbs ("try harder", "do better") |
| **Stripe-precise / Linear-minimal register** | Discord-meme energy, mascot voice, decorative emoji |

### Microcopy rewrites — apply these to our existing bank

| Existing | Revised |
|---|---|
| "Nice." | Keep — already on-brand |
| "Got it." | Keep |
| "Locked in." | Keep |
| "Handshape down — let's move on." | "Handshape locked. Next: movement." (cleaner, drops mascot voice) |
| "THANK YOU — done." | Keep |
| "That's three. Onward." | "Three reps. Moving on." |
| "Try once more — focus on the handshape." | Keep |
| "Almost. Watch the movement in the reference." | Keep |
| "We need your camera to practice. Your video stays on your device." | Keep (already declarative + scoped) |
| "Day 4 streak. You're building a habit." | "Day 4 streak. Practice tomorrow to extend it." (more concrete, less inspirational) |
| "8 signs from Learning to Familiar this week." | Keep — already perfectly on-brand |

### Words to use vs avoid in product copy

| Use | Avoid |
|---|---|
| "Practice" | "Game", "play" |
| "Sign", "drill", "rep" | "Card", "quiz", "challenge" |
| "Learner" | "Student", "user", "you" (in formal docs) |
| "Pass / not yet" | "Right / wrong" |
| "Reference" (the Deaf signer video) | "Demo", "example", "answer" |
| "Mastery" | "Score", "level up" |
| Concrete sign-parameter names | Generic "wrong technique" |

---

## Stack alignment — partial confirm, partial adjust

The portfolio teardown found SuperBuilders' student practice apps converge on:

| Pattern | Our current spec |
|---|---|
| **Vite + React + Tailwind** | ✅ Same |
| **PWA** | ⚠️ Not yet specified — recommend add |
| **AWS Cognito** for auth | ❌ We have Supabase Auth as the post-pilot path |
| **Display font + Inter body** | ⚠️ Adjust to all-monospace per brand-alignment above |
| **Tailwind** with `rounded-2xl` cards (matching SB `2rem`) | ✅ Same |
| **shadcn/Geist-style app shell** | ✅ Already our pick |

### Recommended spec adjustments

1. **Add PWA support** to the v1 stack (manifest + service worker). Cheap, matches SB convention, useful for the camera-permission persistence story.
2. **Note AWS Cognito as the post-pilot auth path** alongside the Better Auth / Lucia options in `ux-spec.md`. AWS Cognito is what SuperBuilders converges on; if we want to be deployable to their infra later, it's the lowest-friction choice.
3. **Replace Inter with Atkinson Hyperlegible Mono** in the typography section.
4. **Accent colors: `#4f46e5` indigo (primary interactive) + `#06b6d4` cyan (data-viz only) + `#0f0` status**. Cyan was added post-scaffold to match the SuperBuilders hero hologram palette — applied only on heatmap today/hover, activity-panel hairline + corner glow, and the sign-complete toast. Don't use cyan on buttons, links, or general interactive surfaces.
5. **Cards at `2rem` border-radius** — match SB's signature.

---

## Hero / imagery direction

From visual-identity.md: SuperBuilders uses **a single AI-generated painterly piece** ("holograms over a meadow") as the marketing hero. **No stock photography, no team shots, no gradients** beyond a 5%-opacity rainbow whisper.

For our app:

- **Landing page hero**: one AI-generated painterly image. Suggested concept: hands signing against a soft abstract background, in the same "holograms over a meadow" register. Commissioned or generated; not stock.
- **Reference videos**: real Deaf signers, individually credited. No stock signers. (Already in our principles.md — confirms alignment.)
- **Iconography**: outlined / monoline. Avoid filled, avoid Material Design rounded-fill style. Match the all-white hand-drawn quality of SB's "cupped hands cradling stars" icon mark.
- **No decorative gradients in the app shell**. The only gradient allowed is the 5%-opacity whisper on long-form sections, if at all.

---

## What to update in our existing docs

1. **`ux-spec.md` Typography row**: change Inter → Atkinson Hyperlegible Mono
2. **`ux-spec.md` Tech stack table**: add PWA to v1; note AWS Cognito as a post-pilot auth candidate alongside Better Auth/Lucia
3. **`ux-spec.md` color contrast section**: explicitly note dark-mode-first; add the token names from this doc
4. **`ux-spec.md` microcopy bank**: apply the rewrites above
5. **`ux-spec.md` lesson-complete celebration**: confirm "subtle green checkmark" uses `#0f0` CRT-green specifically (not Tailwind's `green-500`)
6. **`principles.md` cultural framing**: no doc edits needed — voice posture already matches
7. **New file: `tailwind.config.ts` skeleton** (when frontend scaffolding lands) with the token map above

---

## Open strategic questions

1. **Brand name for the app itself** — does it have its own name (like Khan-TimeBack, AlphaRead, AlphaMath Fluency) or is it just "SuperBuilders ASL"? The SuperBuilders pattern is to name partner-school apps after the school (Alpha…); for SuperBuilders' own pilots, naming is unclear. Worth deciding before shipping.

2. **Light-mode support** — SuperBuilders' own brand is dark-mode-first with no documented light mode. Their partner products (Alpha Dash, Khan-TimeBack) tend to be light-mode-first. **Recommendation**: ship light-mode default for the learner-facing app (better in classroom lighting; less eye strain for long sessions), with dark mode as a setting. Allow both. This deviates from SuperBuilders' own brand on the rationale that **learner audience ≠ recruiting audience**.

3. **Should we use SuperBuilders' GitHub org** for the repo? `github.com/superbuilders/asl-learning` would visually catalog us with their other 33 repos. Depends on whether the partner agreement transfers code ownership — out of design scope but worth flagging.

4. **TimeBack platform integration** — Alpha's TimeBack platform has components (Dash, Tiger Wallet, AlphaRead, AlphaWrite, AlphaLearn, AlphaMath Fluency, TeachTales). Should our ASL app slot into TimeBack as a future component, or remain standalone? Out of design scope but architectural — could affect auth choice (AWS Cognito vs anything else).

---

## TL;DR for the build

1. Adopt SuperBuilders' own brand for the app (Path A above).
2. Tailwind tokens: `#1c1c1c` bg, `#252525` elevated, `#2c2c2c` raised, `#eee` fg, `#4f46e5` accent indigo + `#06b6d4` accent cyan (data-viz only), `#0f0` status, `#333/#444/#555` borders, `2rem` card radius. Body has a subtle dual-radial gradient (warm indigo top-left → deep dark bottom-right).
3. Typography: **Atkinson Hyperlegible Mono everywhere** (replaces Inter).
4. Voice: declarative, hyphens not em-dashes in UI, zero exclamation marks, zero emoji, zero mascot voice.
5. Add PWA support to the stack.
6. Note AWS Cognito as a post-pilot auth path option.
7. Light-mode default for the learner-facing surfaces; dark mode optional. (Calculated deviation from SB's own dark-only brand.)
8. Hero imagery: one AI-painterly piece, no stock photos.
9. Reference videos: named Deaf signers, no stock.
