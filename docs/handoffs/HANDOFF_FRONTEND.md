# HANDOFF — ASL Pilot

**Single self-contained handoff for the next development session.** Read this first; everything else (PRD, ux-spec, principles) is reference.

---

## Current state

The scaffold is **live and working**. A developer can spin it up locally, sign in as a seeded dev user, and walk through a full lesson with mock CV. The ML team has not yet shipped a model; the entire CV layer is mocked behind a clean interface so the swap is one file.

**What works today**:
- Local Postgres (Docker), backend (Hono + Drizzle), frontend (Vite + React + Tailwind + shadcn 4 + Base UI)
- Dev-bypass auth ("Skip login" → seeded `dev@asl-pilot.local`)
- 12 lessons / 75 signs / 225 drill definitions / 38 mastery rows / 240 rep_log rows in the seed
- Dashboard with mastery bar, recent lessons (with slide controls), GitHub-style 75-day heatmap (clickable day-detail with lesson breakdown), streak indicator
- Lesson catalog → Lesson Intro (per-lesson camera + reference toggles) → Practice → Lesson Complete
- Practice screen: 3-drill (handshape → movement → sign) × 3 reps per drill, mock CV dev panel, self-report row (Continue / Skip), auto-advance on dev-panel "Set Green", reference video (nyan.mp4 placeholder) with segment-based playback per drill, camera panel with bounding box, pause modal that stops both videos, back-drill / back-sign / camera-toggle / hint controls
- Resume cursor: practice state persisted to localStorage, restored on revisit (≤7 days)
- Sign-complete toast: bottom-right, auto-dismiss 4s, non-blocking, only fires when no rep was skipped in the sign
- 4 practice modes (camera ON/OFF × reference ON/OFF) per the ux-spec
- All 23 routes wired, 6 anchor Playwright specs + 2 Vitest unit specs + axe-core a11y scan = 12/12 e2e + 22 unit = all green

**What's mocked / placeholder**:
- The CV `evaluate.mock` module — never returns `target-met`. Dev panel `[Set Green]` is the only way to trigger auto-advance.
- Reference videos: all signs share `/videos/nyan.mp4` (a 4.1 KB cat clip). Per-sign references arrive with the ML team's Deaf-signer recordings.
- Auth backend: no real users exist beyond the seeded dev account. The "Sign-up" / "Forgot password" / "Email verification" pages render placeholders + dev-bypass buttons.

---

## How to run (read after `laptop restarted, bring up demo`)

```bash
cd /home/bryann/gauntlet/asl-learning

# 1. Start infra (Postgres on 5433, Adminer on 8088)
docker compose up -d
# wait for postgres healthy
docker compose ps

# 2. Apply schema (Drizzle)
DATABASE_URL=postgres://asl:asl_dev_only@localhost:5433/asl_pilot npm run db:migrate

# 3. Seed the dev account (idempotent — always re-wipes + re-seeds the dev user)
DATABASE_URL=postgres://asl:asl_dev_only@localhost:5433/asl_pilot npm run db:seed

# 4. Backend (terminal 1)
DATABASE_URL=postgres://asl:asl_dev_only@localhost:5433/asl_pilot BACKEND_PORT=3000 npm run dev:api

# 5. Frontend (terminal 2)
npm run dev

# 6. Open http://localhost:5173 → click [Dev: Skip login]
```

**Postgres runs on 5433, not 5432** — port 5432 was taken by an unrelated container. `DATABASE_URL` carries the override everywhere; do NOT change `docker-compose.yml` or `.env.example` without checking what's still on 5432.

---

## Recent changes (since the scaffold milestone)

This list is the union of every change after `.scaffold-final-report.md`. Read it before touching anything.

### State machine + practice flow

- **3-event fast-forward in PROMPT_SHOWN**: the React effect that auto-advances through COUNTDOWN → RECORDING → SELF_REPORT now sends 3 events (was 2 — was getting stuck in RECORDING, killing every "I got it" click).
- **Removed `pending` lock on `SelfReportRow`** — the previous behavior disabled buttons during the in-flight `/api/progress/rep` call, which is what users were perceiving as "stops working at some stage." Buttons now fire-and-forget. UI advance is synchronous.
- **Removed "Not quite" button** — was redundant with the retry path (clicking nothing IS the retry). The `FAIL` machine event is preserved for future CV-driven failure detection.
- **Renamed "I got it" → "Continue"** in the SelfReportRow. Same `data-testid="self-report-got-it"` for test compat.
- **Auto-advance on green**: when `boxState === 'green'` and machine is in SELF_REPORT, send `PASS` after a 350ms flash. Dev panel `[Set Green]` is the canonical test trigger.
- **Helper text under the action zone**: "Click Continue when you're ready, or we'll advance automatically when the camera detects success" + small green status dot.
- **Back navigation**: added `BACK_DRILL` and `BACK_SIGN` events on the machine root with `backDrill`/`backSign` actions (clamp at 0). Toolbar buttons + inline "Back drill" near the action zone.
- **Camera toggle mid-lesson**: writes `?camera=0/1` to the URL, persisted across reloads.
- **Pause stops videos**: `Practice.tsx` threads a `paused` boolean into both `CameraPanel` (disables tracks via `track.enabled = false` — keeps the stream allocated so resume doesn't re-prompt permission) and `ReferenceVideo` (calls `video.pause()`).
- **Resume cursor persistence**: `localStorage` key `asl-pilot.practice-resume.<slug>` stores `{signIndex, drillIndex, repIndex, updatedAt}`. Read on Practice mount (if <7 days old), written on every cursor change, cleared when the machine reaches `LESSON_COMPLETE`. Machine `context` initializer accepts `initialSignIndex/initialDrillIndex/initialRepIndex` clamped against actual lesson shape.
- **Sign-complete toast (not modal)**: `Practice.tsx` tracks `signSkippedRef` per current sign. When `signIndex` advances and the ref is false, opens a non-blocking toast in `fixed bottom-4 right-4` with cyan border + `Sparkles` icon + "Sign saved to memory" + sign gloss + dismiss X. Auto-dismisses after 4s.
- **Dev panel moved in-flow** (was `fixed bottom-4 left-4`, was overlapping the I-got-it button on smaller viewports).

### Reference video

- All signs use `frontend/public/videos/nyan.mp4` (converted from `nyan.cat/cats/original.gif` via `ffmpeg-static` npm package — see "Gotchas" for why ffmpeg isn't installed natively).
- The clip is divided into three segments per drill:
  - `handshape` drill plays 0 → 1/3
  - `movement` drill plays 1/3 → 2/3
  - `sign` drill plays 0 → end
- **Auto-loop toggle** next to the play button: ON (default) loops the segment; OFF pauses at segment end.
- Replay button restarts the current segment.
- Slow-motion (0.5×) toggle.
- 3-pill timeline overlay shows which segment is active (indigo fill).

### Drill indicator

- Rewrote as connector-line + chevron between dots (research recommended over chevrons-as-breadcrumbs; the connector line carries the "where am I" semantics).
- Active dot: full indigo `#4f46e5`, 18%-alpha halo, larger size, white digit
- Completed dot: 55% indigo + check glyph (no second accent color)
- Upcoming dot: bordered well with `#555` border (kept legible per USWDS rule — not faded gray)
- Wrapped in `bg-bg-elevated/40` panel with inner shadow

### Rep counter

- From small mono text → bordered inset well: small `Rep` label + **2xl indigo digit** + `of 3` muted. Big, central, immediately legible.

### Heatmap (full rewrite)

- **GitHub-style 7-row × N-week layout** (was 5-row × 15-col chronological). Each cell positioned via `grid-area` based on `(weekIndex, dayOfWeek)`.
- Day-of-week labels (Mon / Wed / Fri sparse) on the left.
- Month labels (Mar / Apr / May...) along the top of the columns.
- Bottom legend: "today" cyan dot + "Less □□□□□ More" calibrated palette.
- **5-tier intensity scale** (was 4). Thresholds: 0=no practice, 1=1–9 reps, 2=10–19, 3=20–29, **4=30+**.
- Palette: GitHub's calibrated `#0e4429 / #006d32 / #26a641 / #39d353` for tiers 1–4 + dark neutral for tier 0.
- **Today's cell**: cyan-bright ring + soft cyan glow shadow (`shadow-[0_0_8px_-2px_hsl(var(--accent-cyan-bright)/0.6)]`).
- **Hover**: cyan ring (1.5px). No scale-up (kept grid geometry).
- **Removed**: streak-run inset glow (was confusing user — looked like unhovered cells were "highlighted").
- First-paint stagger animation (6ms/col + 2ms/row), gated by `prefers-reduced-motion`.
- Wrapped in a styled **"data well" card** (see Dashboard panel below).
- **Click a cell → day detail Dialog**: fetches `GET /api/progress/day/:date`, shows long date, rep count + outcome breakdown (pass/fail/skip), intensity label, and the list of lessons touched that day (with category + reps + signs + click-through links).

### Dashboard

- Mastery + dashboard query: `staleTime: 0` + `refetchOnMount: 'always'` so any back-nav into `/dashboard` re-pulls fresh data. `refetchOnWindowFocus: true` too.
- Activity panel: bordered card with a cyan top-edge gradient hairline + soft cyan corner blur (matches SuperBuilders hero hologram palette). Header strip with "Activity / Last 75 days" eyebrow + intensity legend. Inset shadow on the heatmap surface itself (data-well feel).
- Recent lessons: slide-left/slide-right arrow buttons anchored to the strip + edge-fade gradients. Auto-hide when at scroll ends via `ResizeObserver` + scroll listener.
- "Continue last lesson" link passes `state={{ from: '/dashboard' }}` → LessonIntro reads `location.state.from` and shows "Back to dashboard" instead of the default "Back to catalog".

### Backend

- New endpoint `GET /api/progress/day/:date` returning `{date, drillCount, intensity, outcomes: {pass, fail, skip}, lessons: [{slug, title, category, reps, signs}]}`.
- `intensityForCount` widened to 5 tiers (1–9 / 10–19 / 20–29 / 30+).
- `HeatmapCell.intensity` type widened from `0|1|2|3` to `0|1|2|3|4` in both schemas.
- Startup migration probe accepts `drizzle.__drizzle_migrations` schema location (drizzle-kit migrate writes there in some versions).

### Theme + design tokens

- **Cyan secondary accent** added: `--accent-cyan: #06b6d4`, `--accent-cyan-bright: #22d3ee`. Applied to data-viz surfaces only (heatmap today/hover, activity panel hairline + corner glow, sign-complete toast, Landing hero text-shadow). Indigo stays the primary interactive accent.
- **`--bg-raised`** (`#2c2c2c`): level-2 surface for hover states (per `docs/research/dark-ui-depth.md`).
- **`--border-strong`** (`#444`) and **`--border-stronger`** (`#555`): hover/overlay borders.
- **Bungee** display font (chunky SB-style block face): `@fontsource/bungee`, exposed as Tailwind's `font-display`. Applied to Landing hero, AppShell logo, Dashboard "Welcome back" heading, sign-complete toast. NOT for body text.
- **Body radial gradient**: dual radial from indigo-tinted warm top-left to deep dark bottom-right, `background-attachment: fixed`. Matches the SB About-page subtle gradient.
- **Button (shadcn-generated) rewritten**: per `docs/research/dark-ui-depth.md` — primary has top-edge sheen + colored hover shadow + 1px press, ghost has no translate, all transitions are enumerated (no `transition-all`).
- **Card hover lift**: only on clickable cards (RecentLessons). Inert dashboard tiles don't animate.
- **Progress bar** track is an inset well (`bg-bg-deepest border shadow-inset`); fill is `bg-gradient-to-r from-accent to-accent-hover`.
- **BoundingBox**: removed neon glow (research called it "instant cyberpunk-amateur"). Now a 2-color ring at 30% alpha on detection.
- **AppShell header**: sticky, subtle backdrop blur, two-row inset shadow (no hard 1px line).

### Navigation

- Lesson Intro "Back to catalog" reads `location.state.from`:
  - Came from dashboard → "Back to dashboard"
  - Came from anywhere else (direct visit, catalog link) → "Back to catalog"
- Tested in `tests/e2e/lesson-intro.return-nav.spec.ts`.

---

## File map

| Path | Purpose |
|---|---|
| `docs/principles.md` | Pedagogy + design synthesis (research output) |
| `docs/ux-spec.md` | Page-level UX spec, state machines, 23 routes, dev scaffolding, tech stack |
| `docs/prd-scaffold.md` | Scaffold-milestone PRD with acceptance criteria |
| `docs/local-setup.md` | How to run locally (mirrors §"How to run" above) |
| `docs/ml-handoff.md` | CV integration contract for the ML team |
| `docs/training-plan.md` | ML side (separate track) |
| `docs/hoyso-architecture.md` | Stage 2 architecture reference |
| `docs/superbuilders/brand-alignment.md` | Design tokens + brand voice |
| `docs/superbuilders/{visual-identity,brand-voice,portfolio}.md` | Brand research |
| `docs/competitive/*.md` | 8 competitive teardowns + comparison |
| `docs/research/dark-ui-depth.md` | Dark-mode depth + gradient + button research |
| `docs/research/heatmap-patterns.md` | GitHub-style heatmap research |
| `docs/research/step-indicators.md` | Drill indicator research |
| `docs/handoffs/HANDOFF_FRONTEND.md` | **This file** |
| `frontend/src/pages/Practice.tsx` | The main practice loop. Resume cursor, sign-complete toast, mode toggles, auto-advance on green. Most-edited file. |
| `frontend/src/pages/Dashboard.tsx` | Mastery bar, continue-last CTA, recent lessons, activity card |
| `frontend/src/pages/LessonIntro.tsx` | Per-lesson mode toggles + back-to-source navigation |
| `frontend/src/components/practice/{SelfReportRow,DrillIndicator,RepCounter,ReferenceVideo,CameraPanel,BoundingBox,DevPanel,HintButton}.tsx` | Practice screen components |
| `frontend/src/components/dashboard/{Heatmap,MasteryBar,RecentLessons,StreakIndicator}.tsx` | Dashboard components |
| `frontend/src/lib/machines/practice.ts` | XState v5 practice machine (Lesson > Sign > Drill > Rep) |
| `frontend/src/cv/{evaluate,evaluate.mock,types}.ts` | Mocked CV interface per `ml-handoff.md` |
| `backend/src/routes/{auth,lessons,progress,health}.ts` | API routes |
| `backend/src/db/schema.ts` | Drizzle schema (7 tables + 4 pgEnums) |
| `backend/src/db/migrations/` | Generated SQL migrations |
| `scripts/seed-dev-user.ts` | Idempotent dev-account seeder (12 lessons × ~6 signs × 3 drills) |
| `frontend/tests/e2e/` | 6 anchor specs + 1 nav spec + 1 self-report spec |
| `frontend/tests/a11y/dashboard.axe-scan.spec.ts` | WCAG 2.2 AA scan |
| `frontend/tests/unit/{practice-machine,seed}.spec.ts` | Vitest unit specs |

---

## Tech stack — exact versions

| Layer | Choice | Pinned to |
|---|---|---|
| Frontend framework | React + TypeScript | React 18.3, TS 5.4 |
| Build | Vite | 5.4 + `vite-plugin-pwa` 0.20 |
| Styling | Tailwind | **v3.4** (NOT v4 — different config style) |
| Components | shadcn/ui **v4** on **Base UI** | shadcn 4.8.x; `@base-ui/react` 1.5.x. NOT Radix. |
| State machine | XState | **v5** (`setup().createMachine()` API — NOT v4) |
| Data fetching | TanStack Query | v5 |
| Forms | React Hook Form + Zod | latest |
| Backend | Hono on Node | Hono 4.6 |
| ORM | Drizzle | 0.36 |
| DB driver | `postgres` (NOT `node-postgres`) | 3.4 |
| DB | Postgres | 16-alpine via Docker |
| Fonts | `@fontsource/atkinson-hyperlegible`, `@fontsource/jetbrains-mono`, `@fontsource/bungee` | 5.x. **Note: Atkinson Hyperlegible Mono does not exist as a published font** — we use proportional Atkinson + JetBrains Mono for the monospace role + Bungee for the SB-style display headings. |
| Tests | Playwright + Vitest + axe-core | latest |

---

## Production-deploy preconditions

Now lives in `CLAUDE.md` §"Prod-deploy preconditions" so it's visible
every session. Summary: `DEV_TOOLS_ENABLED=0`, `VITE_DEV_TOOLS=0`, don't
seed the prod DB, update CORS allow-list, flip cookie `secure: true`.

---

## Gotchas

1. **shadcn 4.x is dramatically different** — uses Base UI instead of Radix, ships with oklch colors and Tailwind-v4-style CSS. We patched `globals.css` to restore our HSL brand tokens (`--bg`, `--fg`, etc.) and shadcn's semantic aliases (`--background`, `--foreground`, etc.) both point at the same brand colors. **Do NOT run `npx shadcn@latest add ...` blindly** — it overwrites `globals.css` and breaks the theme. Hand-author additional components using `@base-ui/react` + CVA pattern.
2. **Atkinson Hyperlegible Mono doesn't exist.** The SuperBuilders visual-identity teardown mistakenly identified the SB site's mono font as "Atkinson Hyperlegible Mono." It's not a published font. We use Atkinson Hyperlegible (proportional) for sans + JetBrains Mono for mono + Bungee for display headings.
3. **Postgres is on port 5433** (not 5432). `DATABASE_URL` env var must include `:5433`. The docker-compose file binds to 127.0.0.1 only.
4. **ffmpeg is not installed natively.** When converting `nyan.gif` → `nyan.mp4`, we used `npx ffmpeg-static`. If you need to regenerate the placeholder:
   ```bash
   cd /tmp && npm init -y && npm install ffmpeg-static
   FFMPEG=$(node -e "console.log(require('ffmpeg-static'))")
   "$FFMPEG" -y -i input.gif -movflags faststart -pix_fmt yuv420p \
     -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=15" -c:v libx264 -preset fast -crf 23 -an output.mp4
   ```
5. **Seed drift in tests**: every `practice.dev-mock.full-flow.spec.ts` run touches one new sign, bumping the dev account's mastery rows from 38 → 39. The heatmap test was relaxed to accept `/3[0-9]\s*\/?\s*75/`. Re-seed before running specific assertions: `npm run db:seed`.
6. **The Vite dev server is fragile in long Playwright runs** — `webServer` in `playwright.config.ts` boots its own copies. When the test run ends, those servers exit. After running tests you may need to manually restart `npm run dev` / `npm run dev:api`.
7. **State machine fast-forward sends 3 events, not 2.** PROMPT_SHOWN → COUNTDOWN → RECORDING → SELF_REPORT. If you reduce to 2 sends, every button click stops working at random points.
8. **Don't use the `gridcell`/`grid` ARIA roles on the heatmap.** WCAG requires `gridcell` to descend from `row`; my layout uses absolute `grid-area` positioning with no row containers. Use generic `role="group"` instead.
9. **The mock `evaluate.mock.ts` NEVER returns `'target-met'`.** Mastery state is driven exclusively by the self-report row (and now also by the dev panel's `[Set Green]` → auto-advance pathway). When the real CV module ships, it can return `'target-met'` and the auto-advance effect picks it up.
10. **`.env.local` at repo root may contain real-looking API tokens** (`VAST_API`, `KAGGLE_API`). It's gitignored. If those are live, rotate them before any wider deploy.

---

## Test status

```
12/12 e2e (Playwright)
- e2e/auth.signin.dev-bypass.spec.ts
- e2e/dashboard.heatmap.dev-account.spec.ts
- e2e/lesson-intro.return-nav.spec.ts (2 tests)
- e2e/practice.dev-mock.full-flow.spec.ts
- e2e/practice.modes.toggle-flow.spec.ts (2 tests)
- e2e/practice.self-report-single-click.spec.ts (3 tests: single, 9-click, Set-Green-auto-advance)
- e2e/routes.smoke.spec.ts

1/1 a11y (axe-core WCAG 2.2 AA — dashboard)
22/22 vitest unit
```

Run with: `DATABASE_URL=postgres://asl:asl_dev_only@localhost:5433/asl_pilot npx playwright test`

---

## Open items / known caveats

- **Real ML model not yet shipped.** The CV mock satisfies the integration contract; the ML team's deliverable plugs in by replacing `frontend/src/cv/evaluate.ts`'s re-export from `evaluate.mock` → `evaluate.real`.
- **Reference videos are all nyan.mp4 placeholders.** Production needs real Deaf-signer recordings per sign, with named credits per `docs/principles.md`.
- **Real auth backend not wired.** The dev-bypass `[Skip login]` is the only sign-in path. Adding Better Auth / Lucia is a future milestone.
- **No light mode.** Per `docs/superbuilders/brand-alignment.md`, deferred. Theme switcher not built.
- **Seed re-run is required between test runs** if mastery-count assertions matter.
- **Dashboard "Browse lessons" card and Lesson Catalog category filtering** work but aren't polished — secondary surfaces.
- **The `practice_session` table is not in the schema** — deferred per the scaffold PRD's scope discipline. Sessions are inferred from `rep_log` timestamps if needed.
- **No streak-freeze management UI** — the table tracks `freezesRemaining` but there's no display affordance. Future.
- **`recentLessons` on the dashboard uses `lastPracticedAt` from `rep_log MAX()`** — accurate but doesn't distinguish between "completed" and "abandoned mid-session." Won't matter until real users exist.

---

## What to do next (suggested order)

1. **Test in browser**: hard-refresh, walk through Sign-in → Dashboard → Continue → Lesson Intro → Practice. Confirm sign-complete toast fires bottom-right (not modal). Confirm heatmap looks GitHub-styled. Confirm dashboard refreshes on back-nav.
2. **Real reference videos**: replace `nyan.mp4` with placeholder Deaf-signer clips. Add per-sign filename routing in `ReferenceVideo` (it currently falls back to `MOCK_REFERENCE_VIDEO_URL`).
3. **CV module integration**: when the ML team ships, replace `evaluate.ts`'s mock re-export with the real module per `docs/ml-handoff.md`.
4. **Real auth**: Better Auth or Lucia. Spec is in `docs/local-setup.md` §"Real auth (deferred)".
5. **Lesson Catalog polish**: search, filter, sort, mastered overlay polish.
6. **Account Settings / Notification Preferences / Privacy / Help / About** pages — currently placeholders.
7. **Streak freeze UI**: surface `freezesRemaining` in the dashboard.
8. **Port live sign verification to TS + ship INT8-quantized models**: translate `src/stage2/sign_verifier.py` (the reference impl) to the browser, and quantize Nets 1-4 to INT8 for in-browser/WASM inference. See the design note below.

---

## Live sign verification (sliding-window persistence)

The lesson loop shows ONE target sign and confirms the user produces it from a
live webcam stream. This is VERIFICATION (known target), not open-set
recognition — strictly easier and more robust: we only ever ask "is the target
class confident, consistently, while the hand moves?"

Net 4 is trained on pre-segmented ~30-frame clips and has NO neutral/"no-sign"
class — that is fine, because the target framing means we never ask "what sign
is this?" on a still or absent hand. We slide a `window_len`≈30-frame window
(roughly one sign's duration; 10 is too short for a net trained on ~30-frame
clips) every `stride` frames, gate each window by motion + presence, and fire
when a `vote_frac` fraction of the MOTION-GATED windows in the last `span_sec`
put the TARGET class above `conf_thresh`. We use the target-class probability
(not top-1) so a consistent close-#2 still verifies, plus `hold_sec`
hysteresis so a verified state doesn't flicker.

Motion/presence gate: mean per-frame keypoint velocity over the window
(computed on RAW pixel coords, since the model features are scale-normalised)
>= `motion_min_speed`, AND fraction of frames with a hand present >=
`presence_min`. Ungated windows never spend the classifier and never vote, so
votes don't accumulate on a still or absent hand.

Tunable knobs (all in the `SignVerifier` constructor): `window_len`, `stride`,
`span_sec`, `fps`, `conf_thresh`, `vote_frac`, `motion_min_speed`,
`presence_min`, `min_gated_windows`, `hold_sec`. The classifier is INJECTED as
a callable `classify(window (T,feat_dim)) -> probs (num_classes,)` plus a
`gloss_to_idx` map, so the module is pure-numpy, decoupled from Net 4/torch,
and unit-testable. Per-frame features reuse Net 4's own
`sign_dataset._build_per_frame_features` so live features match training.

`src/stage2/sign_verifier.py` is the REFERENCE for the eventual TS/browser
port (action item #8), which also needs INT8-quantized models.

---

## Workflow doctrine

Workflow doctrine (commit cadence, build-then-review swarm pattern, push
rules, style invariants, prod-deploy preconditions) lives in `CLAUDE.md`
at the project root — auto-loaded by Claude Code every session. **Read
that first.** This file is for codebase-state context only.

---

## Quick orientation if you're a fresh agent

- Read this file end-to-end.
- Read `docs/principles.md` and `docs/ux-spec.md` for context on *why* things are the way they are.
- Read `docs/ml-handoff.md` to understand the CV black-box interface.
- `frontend/src/pages/Practice.tsx` is the most-edited file in the codebase. Start there if asked to change practice behavior.
- `frontend/src/lib/machines/practice.ts` is the source of truth for the practice state graph.
- `backend/src/routes/progress.ts` owns the mastery state machine + heatmap aggregation + day-detail endpoint.
- When in doubt about a token color: check `frontend/src/styles/globals.css` first, then `frontend/tailwind.config.ts`.
