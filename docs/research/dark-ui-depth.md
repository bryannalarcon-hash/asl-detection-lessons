# Dark UI Depth — Research

Compiled from Linear's redesign post, Vercel Geist + Web Interface Guidelines, GitHub Primer shadow tokens, Refactoring UI, NN/g, and dark-mode design-system deep-dives. Targets our existing tokens: `#1c1c1c` body / `#252525` elevated / `#0f0f0f` deepest, `#eee/#999/#666` text, `#333` borders, `#4f46e5` accent, `#0f0` status.

## Top-line principles

In dark mode, **depth is luminance, not shadow**. Light-mode shadows simulate occluded light against a bright surface; on `#1c1c1c`, a `rgba(0,0,0,0.4)` shadow has no contrast to push against and reads as a smudge. Linear, Vercel, Stripe, and Primer all replace shadows-as-primary-elevation with a **layered surface system** (each level ~4–8% lighter) reinforced by **hairline 1px borders**. Shadows still exist, but their job demotes from "this thing floats" to "this thing has a soft edge." Treat shadows, gradients, and glow as condiments — applied to focal interactive elements, never to the chrome.

## Shadow / elevation system

Four levels mapping to the Linear/Vercel/Primer pattern. Each pairs a surface with a 1px border; only floating levels get shadow.

| Level | Use | Surface | Border | Shadow |
|-------|-----|---------|--------|--------|
| 0 body | Page bg | `#0f0f0f` / `#1c1c1c` | — | — |
| 1 resting | Cards in flow | `#1c1c1c` or `#252525` | `1px #333` | — |
| 2 raised | Hover, active row, sticky | `#2c2c2c` | `1px #444` | `inset 0 1px 0 rgba(255,255,255,0.04)` |
| 3 floating | Dropdown, popover | `#2c2c2c` | `1px #444` | `0 8px 16px -4px rgba(0,0,0,0.5), 0 4px 8px -2px rgba(0,0,0,0.3)` |
| 4 overlay | Modal, toast | `#2c2c2c` over `rgba(0,0,0,0.6)` scrim | `1px #555` | `0 24px 48px -12px rgba(0,0,0,0.6), 0 8px 16px -4px rgba(0,0,0,0.4)` |

**Reference values**:
- **GitHub Primer** (only light-mode values are published; dark mirror is the same recipe): `--shadow-floating-large: 0 0 0 1px #d1d9e000, 0 40px 80px 0 #25292e3d`; `--shadow-floating-medium: 0 8px 16px -4px rgba(0,0,0,0.08), 0 24px 48px -12px rgba(0,0,0,0.08), 0 48px 96px -24px rgba(0,0,0,0.08)`; `--shadow-resting-small: 0 1px 1px 0 rgba(31,35,40,0.04), 0 1px 2px 0 rgba(31,35,40,0.03)`. The "transparent 1px outline + multiple low-opacity blurred drops" pattern is what Vercel's Web Interface Guidelines codify as "Layered shadows. Mimic ambient + direct light with at least two layers."
- **Linear** uses LCH-generated luminance steps (their redesign post: "different elevations for our surfaces — background, foreground, panels, dialogs, and modals"), driven by three inputs (base, accent, contrast 30–100).
- **Refactoring UI / Uxcel** baseline: 0dp `#1E1F22` → 1dp `#252629` (+4%) → 3dp `#2C2D32` (+6%) → 6dp `#323438` (+8%) → 8dp `#393C41` (+10%). Our `#1c → #25` step (~+5%) sits inside this range.

## Gradient usage that works

The "no decorative gradients" rule in `competitive/comparison.md` correctly bans colorful conic blobs in product chrome. Three gradient patterns *do* show up in serious dark UIs:

1. **Top-edge sheen (inset highlight)** on raised interactive surfaces: `box-shadow: inset 0 1px 0 rgba(255,255,255,0.06)` gives a primary button a 1px light-source hint. Vercel uses it on primary buttons; Linear uses it on active sidebar items. Tailwind: `shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]`.
2. **Subtle surface gradient** on large elevated cards: `linear-gradient(180deg, rgba(255,255,255,0.02), transparent 40%)` over the base surface. Reads as soft top-light, not "shiny." Use only on hero / primary dashboard panels.
3. **Progress / drill fill**: flat indigo with a one-stop gradient to a brighter step: `linear-gradient(90deg, #4f46e5 0%, #6366f1 100%)`. Standard Stripe/Vercel progress-meter pattern. No animated shimmer — too playful for the register.

**Out of scope**: conic page backgrounds, animated gradient borders, multi-stop rainbow CTAs.

## Button feedback

**Primary (`accent` indigo)** — fill + 1-step-lighter border + top sheen, hover brightens with colored drop shadow, active presses down:
```css
.btn-primary {
  background: #4f46e5; color: #fff;
  border: 1px solid #6366f1;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.08);
  transition: background-color 150ms ease, border-color 150ms ease,
              box-shadow 150ms ease, transform 100ms ease;
}
.btn-primary:hover {
  background: #6366f1; border-color: #818cf8;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.12),
              0 2px 8px -2px rgba(79,70,229,0.4);
}
.btn-primary:active {
  background: #4338ca; transform: translateY(1px);
  box-shadow: inset 0 1px 2px rgba(0,0,0,0.2);
  transition-duration: 50ms;
}
.btn-primary:focus-visible { outline: 2px solid #818cf8; outline-offset: 2px; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
```

**Ghost / secondary** — transparent + hairline border, hover brightens surface + border, no shadow, no translate:
```css
.btn-ghost { background: transparent; color: #eee; border: 1px solid #333;
  transition: background-color 150ms ease, border-color 150ms ease; }
.btn-ghost:hover { background: #252525; border-color: #555; }
.btn-ghost:active { background: #1c1c1c; border-color: #444; }
```

**Vercel Web Interface Guidelines rules** (apply all four): "Interactions increase contrast." "Never `transition: all` — enumerate properties." "Honor `prefers-reduced-motion`." "Match visual & hit targets — if visual <24px, expand hit to ≥24px."

**Lift vs press**: Linear and Notion buttons do *not* `translateY(-2px)` on hover — that's a marketing pattern. In productivity UI, hover *brightens and outlines*; active/press moves down 1px for tactile feel. Reserve hover-lift for cards.

## Cards and surfaces

**Default card** — border only: `bg-[#252525] border border-[#333] rounded-[2rem]`. The 2rem radius is our signature; pair with a single hairline border.

**Hover (clickable) card**: brighten surface + border + 1px translate. Skip the drop shadow.
```
hover:bg-[#2c2c2c] hover:border-[#444] hover:-translate-y-px
transition-colors duration-150 transition-transform duration-100
```

**Inert card** (dashboard stats, summary tiles): no hover. Animating non-interactive surfaces is the #1 thing that makes a UI feel cheap.

**Inset/depressed surface** (camera viewport, code blocks, heatmap container): `bg-[#0f0f0f] border border-[#333] shadow-[inset_0_1px_2px_rgba(0,0,0,0.4)]`. Inset shadow on a darker-than-surroundings surface is the one shadow pattern that *does* work in dark mode — reads as a recessed well, not a floating object.

**Tinted "you are here"**: 2–4% accent alpha on `aria-current`: `bg-[rgba(79,70,229,0.08)] border-l-2 border-accent`. Standard Linear/Notion pattern.

## Focus rings

WCAG 2.4.13 baseline: ≥2px thick, ≥3:1 contrast against element and background. Use `:focus-visible` so the ring only shows on keyboard nav:

```css
:focus-visible {
  outline: 2px solid #818cf8;   /* accent.ring (indigo-400) */
  outline-offset: 2px;
  border-radius: inherit;
}
```

`outline-offset: 2px` lets the ring breathe past rounded corners. For dark-on-accent cases where indigo-400 fails 3:1, use the double-outline / "white-gap" technique: `box-shadow: 0 0 0 2px #1c1c1c, 0 0 0 4px #818cf8` — a 2px ring of body color, then 2px of accent. Vercel rule: never `outline: none` without replacing it.

## Anti-patterns (what kills it)

- **Pure black `#000`** body — halation/eye-strain on OLED. Use `#0f0f0f`/`#1c1c1c` (we do).
- **Pure white `#fff` text** — too much contrast. Use `#eee–#f0f0f0` (we do).
- **Dark drop shadows on dark surfaces** — invisible noise. If you can't see it, delete it.
- **Glassmorphism / `backdrop-filter: blur()`** in product chrome — wrong register, performance hit on low-end, "translucent panels often glow instead of receding" (Muzli).
- **Neon glow on borders** (`box-shadow: 0 0 12px #00ff00`) — instant cyberpunk-amateur. CRT-green is a *small status fill*, never a glow source.
- **Animated gradient borders / rotating conic backgrounds** — premium-SaaS cliché, fights Linear-quiet posture.
- **`transition: all`** — animates layout accidentally. Enumerate properties.
- **Hover animations on non-interactive surfaces** — promises a click that doesn't exist.
- **Color-only state encoding** — already banned in `comparison.md`; status pills must pair color with icon.
- **Grey text at 50% opacity** — washed out, fails contrast. Use the named scale at full opacity.

## Concrete recommendations for our app

Tailwind utility classes assume the brand-alignment token additions are in place.

- **Buttons (primary)**: `bg-accent border border-accent-hover shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] transition-colors duration-150`. Hover: `bg-accent-hover border-accent-ring shadow-[0_2px_8px_-2px_rgba(79,70,229,0.4)]`. Active: `bg-indigo-700 translate-y-px` + swap to inset pressed shadow.
- **Buttons (ghost)**: `bg-transparent border border-border` → hover `bg-bg-elevated border-border-strong`. No shadow, no translate.
- **Buttons (disabled)**: `opacity-40 cursor-not-allowed`. Opacity does the work; don't grey out colors separately.
- **Cards (clickable)**: `bg-bg-elevated border border-border rounded-card` → hover `bg-[#2c2c2c] border-border-strong -translate-y-px`. No drop shadow.
- **Cards (inert)**: same surface, no hover, no transitions. Static.
- **Hero / primary panel**: `bg-bg-elevated` + a `::before` with `background: linear-gradient(180deg, rgba(255,255,255,0.025), transparent 40%)` `pointer-events:none`. Single use.
- **Heatmap cells**: borderless squares on `#0f0f0f` container. 5 mastery levels = indigo at `0.15 / 0.30 / 0.50 / 0.75 / 1.0` alpha. Empty cells `bg-[#1c1c1c]` (one step above container so they read as "slot" not "missing"). Hover: `border border-border-strong`.
- **Drill recording indicator**: CRT-green `#0f0` as a 12px fill with `ring-status-ok/30` 2px halo. Pulse only during active capture, behind `prefers-reduced-motion`. Never use as glow source.
- **Video panels (reference + user replay)**: `bg-bg-deepest border border-border shadow-[inset_0_1px_2px_rgba(0,0,0,0.4)]` — recessed well. Video is the brightest thing; panel recedes.
- **Progress bars**: track `bg-[#0f0f0f] border border-[#333]` with inset shadow; fill `bg-gradient-to-r from-accent to-accent-hover`. No animation.
- **Status pills**: tinted bg + full-color border + icon + label. Pass: `bg-[rgba(0,255,0,0.08)] border border-status-ok text-status-ok`. Border carries meaning; tint is hint.
- **Sidebar active item**: `bg-[rgba(79,70,229,0.08)] border-l-2 border-accent`.
- **Focus rings (global)**: `focus-visible:outline-2 focus-visible:outline-accent-ring focus-visible:outline-offset-2`. Upgrade to double-outline box-shadow on dark-on-dark cases.
- **Transitions (global)**: `transition-colors duration-150 ease-out` default. `transition-transform duration-100` only with translate-y. Never `transition-all`. Always honor `motion-reduce:transition-none`.

Net effect: depth comes from the **layered surface scale** (`#0f0f0f` → `#1c1c1c` → `#252525` → `#2c2c2c`) reinforced by **1px borders** (`#333` → `#444` → `#555`). Shadows reserved for **floating overlays** and **inset wells**; gradients reserved for **top-edge sheens** and **progress fills**; the accent carries the only colored shadow on the page (primary-button hover). No glow, no glass, no conic blobs, no animated borders. The brand stays Linear-quiet; the UI stops feeling flat.

## Sources

- [Linear — How we redesigned the Linear UI (Part II)](https://linear.app/now/how-we-redesigned-the-linear-ui) — LCH theme, elevation-as-luminance, three-variable generator.
- [Vercel Geist — Colors](https://vercel.com/geist/colors), [Material](https://vercel.com/geist/material), [Button](https://vercel.com/geist/button) — surface 1/2/3 + border 4/5/6 scale, elevation roles, button variants.
- [Vercel Labs — Web Interface Guidelines](https://github.com/vercel-labs/web-interface-guidelines) — layered shadows, contrast on interaction, `:focus-visible`, no `transition: all`, 24px hit target.
- [GitHub Primer — Foundations: Color](https://primer.style/foundations/primitives/color) — published shadow tokens with exact rgba.
- [Refactoring UI applied — "Designing a Scalable Dark Theme"](https://www.fourzerothree.in/p/scalable-accessible-dark-mode) — saturation −15–25% for dark, layered surfaces, no pure black.
- [Uxcel — Mastering Elevation for Dark UI](https://uxcel.com/blog/mastering-elevation-for-dark-ui-a-comprehensive-guide-342) — 0/1/3/6/8 dp values validating our `#1c → #25 → #2c` step.
- [Muzli — Dark Mode Design Systems Guide](https://muz.li/blog/dark-mode-design-systems-a-complete-guide-to-patterns-tokens-and-hierarchy/) — 4-level hierarchy, "shadows don't read on dark."
- [Chyshkala — Why Linear Design Systems Break in Dark Mode](https://chyshkala.com/blog/why-linear-design-systems-break-in-dark-mode-and-how-to-fix-them) — borders/outlines/contrast shifts for hover in dark.
- [NN/g — Dark Mode UX](https://www.nngroup.com/articles/dark-mode/) — light-mode performs better for normal vision; allow toggle.
- [MDN — `:focus-visible`](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Selectors/:focus-visible), [a11y-collective — Focus Indicators](https://www.a11y-collective.com/blog/focus-indicator/) — WCAG 2.4.13, double-outline technique.
