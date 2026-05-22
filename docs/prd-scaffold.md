# PRD — Web App Scaffold

Requirements for the **scaffold milestone**: getting a coding agent from an empty repo to a runnable, navigable, dev-account-populated app shell. No mocks except the ML/CV layer. Feature work begins after this milestone.

> **This PRD is the source of truth for the scaffold.** It points to other docs for the *why*, but every concrete decision the agent needs is in this file. If something is ambiguous here, stop and ask before inventing.

---

## Goal

After this milestone, a developer should be able to:

1. `git clone`, `cp .env.example .env`, `docker compose up -d`, `npm install`, `npm run db:migrate`, `npm run db:seed`, then `npm run dev:api` (terminal 1) + `npm run dev` (terminal 2)
2. Open `http://localhost:5173`, see the landing page
3. Click `[Dev: Skip login]` on the sign-in page, signed in as `dev@asl-pilot.local`
4. Land on Dashboard, see populated month heatmap, mastery bar at "38 / 75", recent lessons strip
5. Navigate to every one of the 23 page routes (Route Map below) and see at minimum a header + breadcrumb + placeholder content
6. On the Practice Screen: click `[Set Gray]` / `[Set Orange]` / `[Set Green]` mock buttons, see the bounding box change color; tap `[I got it]` on the self-report row, see the rep advance
7. `npm test` passes the 6 anchor specs (5 e2e + 1 routes smoke) + Vitest unit specs
8. `axe-core` scan of Dashboard returns 0 violations

If 8/8 pass, scaffold milestone is **done**.

---

## Decisions resolved (from PRD review)

These were ambiguous in earlier drafts; locked now:

| Decision | Value |
|---|---|
| Color mode default | **Dark mode only** in scaffold. Tokens match `brand-alignment.md` exactly (`#1c1c1c` bg, `#eee` fg). Light-mode support deferred to a later milestone. |
| Monorepo tool | **npm workspaces** (zero install) |
| Tailwind version | **v3.4.x** (pinned; v4's CSS-first config is out of scope) |
| XState version | **v5.x** (`setup().createMachine()` API, NOT v4 `Machine()`) |
| Font (display + body) | **Atkinson Hyperlegible** (proportional, via `@fontsource/atkinson-hyperlegible`) for body, **JetBrains Mono** (via `@fontsource/jetbrains-mono`) for code/labels. The "Mono" variant SuperBuilders' marketing implies does not exist as a published font; this is the buildable approximation. |
| PWA | **`vite-plugin-pwa`** with `registerType: 'autoUpdate'`; hand-rolled SW out of scope |
| Email column | `text NOT NULL` + unique functional index `LOWER(email)`. No `citext` extension. |
| Table name | `drill_definition` (not `drill`) |
| App name in copy | "ASL Pilot" placeholder; revisit before launch |

---

## Non-goals (what NOT to build)

- Real ML inference (CV layer is mocked — see CV Mock section below)
- Real auth backend (dev-bypass only — no SMTP, no OAuth, no email verification)
- Real reference videos (one placeholder mp4 in `/public/videos/hello.mp4` is the fallback for every sign)
- Real lesson content beyond ~12 lessons × ~6 stub signs = 75 total signs (the actual final 75–100 come later)
- The SRS expanding-interval scheduler (simple advance/regress only)
- Per-sign per-parameter hint strings (one hardcoded fallback hint is fine)
- Light-mode support / theme switcher
- Real Deaf-signer reference video production
- Real notification system (cron, push, email)
- `vite-plugin-pwa` install banners or Add-to-Home-Screen prompts
- Per-sign public dictionary pages `/signs/<slug>`
- Slow-motion toggle on reference videos
- Pretesting / productive-failure variant of the Rep state machine
- Hint frequency fading after N successful reps
- Leech detection / auto-suspend
- Pixel-perfect UI polish — apply tokens, don't grind micro-spacing
- i18n
- Analytics / Sentry / PostHog
- CI/CD or production deployment
- Light/dark theme switcher

---

## Inputs — read before starting

| Doc | What to extract |
|---|---|
| [`principles.md`](./principles.md) | Mastery state model, hint priority order, scope honesty |
| [`ux-spec.md`](./ux-spec.md) | Page features, practice screen state machine details, dev scaffolding spec, microcopy bank |
| [`local-setup.md`](./local-setup.md) | Stack versions, env vars, prerequisites |
| [`ml-handoff.md`](./ml-handoff.md) | CV `init()` / `processFrame()` / `evaluateRep()` interface, `DetectionResult` shape |
| [`superbuilders/brand-alignment.md`](./superbuilders/brand-alignment.md) | Tailwind tokens, microcopy patterns, hero direction |
| `superbuilders-partner-project-asl-learning-with-computer-vision.pdf` | Original 15 requirements |

---

## Repository structure

```
/home/bryann/gauntlet/asl-learning/
├── docker-compose.yml                  (exists)
├── .env.example                        (exists)
├── .env                                (gitignored)
├── .nvmrc                              NEW — "20.11.0"
├── package.json                        NEW — root, with workspaces ["frontend", "backend"]
├── tsconfig.base.json                  NEW
├── .gitignore                          (verify excludes .env, .env.local, node_modules, dist, frontend/dist, backend/dist)
├── README.md                           NEW — one page
├── scripts/
│   ├── db/init.sql                     (exists)
│   ├── seed-dev-user.ts                NEW
│   └── (no separate reset script — seed always wipes + reseeds the dev user)
├── docs/                               (exists)
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   ├── tsconfig.json
│   ├── index.html
│   ├── public/
│   │   ├── videos/hello.mp4            (placeholder; ~2–5 second loop)
│   │   ├── videos/.gitkeep
│   │   ├── models/.gitkeep
│   │   └── fonts/                      (populated by @fontsource at install time; no manual files)
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── router.tsx
│   │   ├── pages/                      (23 files — see Route Map)
│   │   ├── components/
│   │   │   ├── ui/                     (shadcn-generated)
│   │   │   ├── practice/
│   │   │   ├── dashboard/
│   │   │   ├── auth/
│   │   │   └── layout/                 (PlaceholderLayout shared by stub pages)
│   │   ├── cv/
│   │   │   ├── evaluate.ts             (re-exports from evaluate.mock)
│   │   │   ├── evaluate.mock.ts
│   │   │   └── types.ts
│   │   ├── lib/
│   │   │   ├── api.ts
│   │   │   ├── auth.ts
│   │   │   ├── env.ts
│   │   │   ├── constants.ts            (TOTAL_SIGNS = 75 etc.)
│   │   │   └── machines/practice.ts    (XState v5)
│   │   └── styles/globals.css          (Tailwind + @font-face + CSS variables)
│   └── tests/
│       ├── e2e/
│       ├── a11y/
│       └── unit/
├── backend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── drizzle.config.ts
│   ├── src/
│   │   ├── index.ts                    (Hono entry, listens on BACKEND_PORT)
│   │   ├── routes/
│   │   │   ├── auth.ts                 (POST /api/auth/dev-login, GET /api/me)
│   │   │   ├── lessons.ts              (GET /api/lessons, GET /api/lessons/:slug)
│   │   │   ├── progress.ts             (POST /api/progress/rep, GET /api/progress/dashboard)
│   │   │   └── health.ts               (GET /api/health)
│   │   ├── db/
│   │   │   ├── client.ts
│   │   │   ├── schema.ts
│   │   │   └── migrations/             (Drizzle output)
│   │   └── lib/
│   │       ├── session.ts              (cookie helpers)
│   │       └── cors.ts
├── playwright.config.ts                (launch args include camera mock)
├── vitest.config.ts
```

---

## Route Map (23 pages)

| # | Page | Route | Real or Placeholder | Notes |
|---|---|---|---|---|
| 1 | Landing | `/` | Real (minimal) | Hero block (no image yet), sign-in CTA |
| 2 | Sign-up | `/signup` | Placeholder + dev bypass | `[Dev: Create local account]` button works |
| 3 | Sign-in | `/signin` | **Real** | `[Dev: Skip login]` signs in as dev user |
| 4 | Forgot password | `/forgot-password` | Placeholder + dev bypass | |
| 5 | Email verification | `/verify-email` | Placeholder + dev bypass | |
| 6 | Onboarding: Welcome | `/onboarding/welcome` | **Real** | Scope statement, "Let's set up your camera" CTA |
| 7 | Onboarding: Camera Priming | `/onboarding/camera` | **Real** | Real getUserMedia() prompt |
| 8 | Onboarding: Calibration | `/onboarding/calibration` | **Real** | Live preview + framing guide overlay |
| 9 | Onboarding: First-Sign Tutorial | `/onboarding/first-sign` | **Placeholder** that routes to Dashboard | Tutorial-specific logic (faded hint, endowed-progress tick) is feature work |
| 10 | Dashboard | `/dashboard` | **Real** | Heatmap + mastery bar + recent lessons |
| 11 | Lesson Catalog | `/lessons` | **Real** | Grid of seeded lessons |
| 12 | Lesson Intro | `/lessons/:slug` | **Real** | Sign-list preview + practice-settings toggles |
| 13 | Practice Screen | `/lessons/:slug/practice` | **Real** | Drill state machine + mock CV dev panel |
| 14 | Lesson Complete | `/lessons/:slug/complete` | **Real (static render)** | Renders mastery snapshot, NOT computed deltas |
| 15 | Account Settings | `/settings/account` | Placeholder | |
| 16 | App Settings | `/settings/app` | **Real (persist-only)** | Toggle changes persist to DB; Lesson Intro pre-fill is feature work |
| 17 | Notification Preferences | `/settings/notifications` | Placeholder | |
| 18 | Privacy & Data | `/privacy` | Placeholder | |
| 19 | Help / How It Works | `/help` | Placeholder | |
| 20 | About / Credits | `/about` | Placeholder | |
| 21 | Error: Camera Denied | `/errors/camera-denied` | **Real** | Browser-specific re-enable instructions |
| 22 | Error: Offline | `/errors/offline` | Placeholder | |
| 23 | 404 / Not Found | `*` wildcard | **Real** | Fallback for unknown routes |

10 real, 13 placeholders or partial. Placeholders use the shared `<PlaceholderLayout>` component (defined below).

---

## Database schema (Drizzle, Postgres 16)

In `backend/src/db/schema.ts`. **All column types resolved**:

```typescript
import { pgTable, pgEnum, uuid, text, timestamp, integer, boolean, date, time, index, uniqueIndex } from 'drizzle-orm/pg-core';

// === Enums ===
export const masteryLevelEnum = pgEnum('mastery_level', [
  'new', 'learning', 'familiar', 'known', 'mastered'
]);
export const repOutcomeEnum = pgEnum('rep_outcome', ['pass', 'fail', 'skip']);
export const repSourceEnum = pgEnum('rep_source', ['cv', 'self-report', 'dev']);
export const drillTypeEnum = pgEnum('drill_type', ['handshape', 'movement', 'sign']);

// === Tables ===
export const user = pgTable('user', {
  id: uuid('id').primaryKey().defaultRandom(),
  email: text('email').notNull(),
  displayName: text('display_name').notNull(),
  createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  emailVerifiedAt: timestamp('email_verified_at', { withTimezone: true }),
}, (t) => ({
  emailLowerUnique: uniqueIndex('user_email_lower_unique').on(/* LOWER(email) — Drizzle raw SQL */),
}));

export const lesson = pgTable('lesson', {
  id: uuid('id').primaryKey().defaultRandom(),
  slug: text('slug').notNull().unique(),
  title: text('title').notNull(),
  category: text('category').notNull(),
  signCount: integer('sign_count').notNull(),
  orderIndex: integer('order_index').notNull(),
});

export const sign = pgTable('sign', {
  id: uuid('id').primaryKey().defaultRandom(),
  slug: text('slug').notNull().unique(),
  englishGloss: text('english_gloss').notNull(),
  lessonId: uuid('lesson_id').notNull().references(() => lesson.id, { onDelete: 'cascade' }),
  orderIndex: integer('order_index').notNull(),
});

export const drillDefinition = pgTable('drill_definition', {
  id: uuid('id').primaryKey().defaultRandom(),
  signId: uuid('sign_id').notNull().references(() => sign.id, { onDelete: 'cascade' }),
  drillType: drillTypeEnum('drill_type').notNull(),
  targetString: text('target_string').notNull(),  // e.g. 'flat-B', 'forward-arc', 'THANK_YOU'
  orderIndex: integer('order_index').notNull(),
});

export const repLog = pgTable('rep_log', {
  id: uuid('id').primaryKey().defaultRandom(),
  userId: uuid('user_id').notNull().references(() => user.id, { onDelete: 'cascade' }),
  signId: uuid('sign_id').notNull().references(() => sign.id, { onDelete: 'cascade' }),
  drillType: drillTypeEnum('drill_type').notNull(),
  outcome: repOutcomeEnum('outcome').notNull(),
  source: repSourceEnum('source').notNull(),
  hintRequested: boolean('hint_requested').notNull().default(false),
  createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
}, (t) => ({
  userDateIdx: index('rep_log_user_date_idx').on(t.userId, t.createdAt),
}));

export const masteryState = pgTable('mastery_state', {
  userId: uuid('user_id').notNull().references(() => user.id, { onDelete: 'cascade' }),
  signId: uuid('sign_id').notNull().references(() => sign.id, { onDelete: 'cascade' }),
  level: masteryLevelEnum('level').notNull().default('new'),
  lastPracticedAt: timestamp('last_practiced_at', { withTimezone: true }),
  advanceCount: integer('advance_count').notNull().default(0),
  regressCount: integer('regress_count').notNull().default(0),
}, (t) => ({
  pk: /* compound (user_id, sign_id) */,
}));

export const streakState = pgTable('streak_state', {
  userId: uuid('user_id').primaryKey().references(() => user.id, { onDelete: 'cascade' }),
  currentStreakDays: integer('current_streak_days').notNull().default(0),
  longestStreakDays: integer('longest_streak_days').notNull().default(0),
  freezesRemaining: integer('freezes_remaining').notNull().default(2),
  lastPracticeDate: date('last_practice_date'),
});

export const notificationPref = pgTable('notification_pref', {
  userId: uuid('user_id').primaryKey().references(() => user.id, { onDelete: 'cascade' }),
  dailyReminderTime: time('daily_reminder_time'),  // nullable; null = opted out
  weeklySummaryEnabled: boolean('weekly_summary_enabled').notNull().default(true),
  streakAtRiskEnabled: boolean('streak_at_risk_enabled').notNull().default(false),
});
```

**`practice_session` table is deferred** — no scaffold AC requires it, analytics are explicitly non-goal.

**`citext` is not enabled.** Email comparisons use the `LOWER(email)` unique index.

Drizzle config (`backend/drizzle.config.ts`):

```typescript
import type { Config } from 'drizzle-kit';
export default {
  schema: './src/db/schema.ts',
  out: './src/db/migrations',
  dialect: 'postgresql',
  dbCredentials: { url: process.env.DATABASE_URL! },
} satisfies Config;
```

---

## Seed data shape

In `scripts/seed-dev-user.ts`. **Idempotent by design**: always `DELETE FROM rep_log, mastery_state, streak_state, notification_pref WHERE user_id = devUserId` (and re-insert the user if missing), then re-seed. Safe to run repeatedly.

Per [`ux-spec.md`](./ux-spec.md) §"Development scaffolding (remove before launch)" → "4. Dev account":

- **User**: `dev@asl-pilot.local`, "Dev User", `created_at` = today - 75 days, `email_verified_at` = same
- **Catalog seed (one-time, not user-specific)**: 12 lessons × 6–7 signs each = ~75 total signs; each sign has 3 `drill_definition` rows (Handshape / Movement / Sign drill); lesson categories pulled from a fixed list (Greetings, Numbers, Family, Feelings, Food, Time, Places, Verbs, Question Words, etc.)
- **`mastery_state`** for dev user: 38 rows touched — 12 Mastered, 9 Known, 8 Familiar, 5 Learning, 4 New
- **`rep_log`** for dev user: 75 days of varied data
  - ~40% of days: 0 rows
  - ~25% of days: 1–3 rows (light)
  - ~25% of days: 4–8 rows (moderate)
  - ~10% of days: 9+ rows (heavy)
  - Streak windows: 14-day continuous block ending 18 days ago, current 4-day streak, two single-day blips
  - Recent 7 days densest
- **`streak_state`**: `current_streak_days=4`, `longest_streak_days=14`, `freezes_remaining=2`, `last_practice_date=today`
- **`notification_pref`**: `daily_reminder_time='19:00:00'`, `weekly_summary_enabled=true`, `streak_at_risk_enabled=false`

A Vitest spec (`tests/unit/seed.spec.ts`) asserts these row counts after running the seed.

---

## CV mock module — exact code

`frontend/src/cv/types.ts`:

```typescript
export interface Frame {
  timestamp: number;
  imageData: ImageBitmap;
}

export type DrillType = 'handshape' | 'movement' | 'sign';

export interface DetectionResult {
  state: 'target-met' | 'low-confidence' | 'no-hands';
  confidence: number;
  oodScore?: number;
  parameter?: 'handshape' | 'movement' | 'palm-orientation' | 'location' | 'timing' | 'framing';
  detail?: string;
  latencyMs: number;
  modelVersion: string;
}

export interface InitResult {
  modelVersion: string;
  backend: 'webgpu' | 'wasm';
  warmupLatencyMs: number;
}
```

`frontend/src/cv/evaluate.mock.ts`:

```typescript
import type { Frame, DrillType, DetectionResult, InitResult } from './types';

let currentBoxState: 'no-hands' | 'hands-detected' = 'no-hands';
let framesBuffered = 0;

export async function init(): Promise<InitResult> {
  return { modelVersion: 'mock-0.1', backend: 'wasm', warmupLatencyMs: 0 };
}

export function processFrame(_frame: Frame) {
  framesBuffered++;
  return { state: currentBoxState, framesBuffered };
}

export async function evaluateRep(_drillType: DrillType, _target: string): Promise<DetectionResult> {
  // Mock NEVER returns 'target-met'. Mastery is driven by self-report row.
  return {
    state: 'low-confidence',
    confidence: 0,
    latencyMs: 0,
    modelVersion: 'mock-0.1',
  };
}

export function resetRepBuffer() { framesBuffered = 0; }
export async function dispose() {}

// Dev-panel-only — gated by import.meta.env.VITE_DEV_MODE
export function __devSetBoxState(state: 'no-hands' | 'hands-detected') {
  currentBoxState = state;
}
```

`frontend/src/cv/evaluate.ts`:

```typescript
export * from './evaluate.mock';
// v2 swap: change to `export * from './evaluate.real';` once the ML team ships
```

The Practice Screen's **dev panel** dispatches:
- `[Set Gray]` → `__devSetBoxState('no-hands')`
- `[Set Orange]` → `__devSetBoxState('hands-detected')`
- `[Set Green]` → calls `processFrame()` (state stays `hands-detected`) but the UI overlays a green border for ~600ms as a **purely visual** confirmation. Mastery is NOT advanced by this button.

**Mastery advancement** is exclusively driven by the self-report row:
- `[I got it]` → POST `/api/progress/rep` with `outcome: 'pass'`, `source: 'self-report'`
- `[Not quite]` → POST same with `outcome: 'fail'`
- `[Skip]` → POST same with `outcome: 'skip'`

---

## API contract (backend routes)

### Auth

| Method | Path | Body | Response | Notes |
|---|---|---|---|---|
| POST | `/api/auth/dev-login` | `{}` | `{ user }` + sets session cookie | Dev-only; rejects in prod |
| POST | `/api/auth/sign-out` | `{}` | `{ ok: true }` | Clears cookie |
| GET | `/api/me` | — | `{ user }` or 401 | |

### Progress

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/api/progress/rep` | `{ signId, drillType, outcome, source: 'self-report' \| 'cv' \| 'dev' }` | `{ masteryState }` (updated) |
| GET | `/api/progress/dashboard` | — | `{ masterySummary, heatmap, recentLessons, streak }` |

### Lessons

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/lessons` | — | `{ lessons: [...] }` |
| GET | `/api/lessons/:slug` | — | `{ lesson, signs, drillDefinitions }` |

### Health

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/health` | — | `{ ok: true, dbReachable: boolean }` |

### Session + CORS

- **Cookie**: `asl_session`, signed, `httpOnly`, `sameSite='lax'`, `secure=false` in dev. Stores `{ userId }`.
- **CORS** (in `backend/src/lib/cors.ts`):
  ```typescript
  import { cors } from 'hono/cors';
  cors({ origin: 'http://localhost:5173', credentials: true })
  ```
- **Frontend fetch wrapper** in `frontend/src/lib/api.ts`:
  ```typescript
  export const apiFetch = (path: string, init?: RequestInit) =>
    fetch(`${API_URL}${path}`, { ...init, credentials: 'include' });
  ```

### Mastery state machine (in backend)

`POST /api/progress/rep` with `outcome='pass'` advances `mastery_state.level` by one stage and `+1` to `advance_count` (clamped at `mastered`). `outcome='fail'` regresses one stage with `+1` to `regress_count` (clamped at `new`). `skip` is a no-op on level but still logged. The full SRS scheduler is deferred.

### Backend startup safety

On boot, before listening, run `SELECT 1 FROM __drizzle_migrations` (or equivalent). If it errors with `relation "__drizzle_migrations" does not exist`, log `Run npm run db:migrate first` and exit 1. No stack trace.

---

## Brand tokens — exact Tailwind + CSS setup

**Tailwind v3.4.x** in `frontend/tailwind.config.ts`:

```typescript
import type { Config } from 'tailwindcss';
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',  // we ship dark-only but use the class for future light-mode
  theme: {
    extend: {
      colors: {
        bg: { DEFAULT: 'hsl(var(--bg))', elevated: 'hsl(var(--bg-elevated))' },
        fg: { DEFAULT: 'hsl(var(--fg))', muted: 'hsl(var(--fg-muted))' },
        border: { DEFAULT: 'hsl(var(--border))', strong: 'hsl(var(--border-strong))' },
        accent: { DEFAULT: 'hsl(var(--accent))', hover: 'hsl(var(--accent-hover))' },
        status: { ok: 'hsl(var(--status-ok))' },

        // shadcn compatibility — its CVA recipes reference these names
        background: 'hsl(var(--bg))',
        foreground: 'hsl(var(--fg))',
        primary: { DEFAULT: 'hsl(var(--accent))', foreground: 'hsl(var(--fg))' },
        secondary: { DEFAULT: 'hsl(var(--bg-elevated))', foreground: 'hsl(var(--fg))' },
        muted: { DEFAULT: 'hsl(var(--bg-elevated))', foreground: 'hsl(var(--fg-muted))' },
        card: { DEFAULT: 'hsl(var(--bg-elevated))', foreground: 'hsl(var(--fg))' },
        ring: 'hsl(var(--accent))',
      },
      fontFamily: {
        sans: ['"Atkinson Hyperlegible"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        card: '2rem',
        DEFAULT: '0.75rem',
      },
    },
  },
  plugins: [],
} satisfies Config;
```

`frontend/src/styles/globals.css`:

```css
@import '@fontsource/atkinson-hyperlegible/400.css';
@import '@fontsource/atkinson-hyperlegible/700.css';
@import '@fontsource/jetbrains-mono/400.css';

@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  /* HSL triplets — Tailwind v3 idiom for theme-able tokens */
  --bg: 0 0% 11%;            /* #1c1c1c */
  --bg-elevated: 0 0% 15%;   /* #252525 */
  --fg: 0 0% 93%;            /* #eeeeee */
  --fg-muted: 0 0% 60%;
  --border: 0 0% 20%;        /* #333333 */
  --border-strong: 0 0% 33%;
  --accent: 244 76% 59%;     /* #4f46e5 indigo */
  --accent-hover: 239 84% 67%;
  --status-ok: 120 100% 50%; /* #00ff00 */
}

body {
  background: hsl(var(--bg));
  color: hsl(var(--fg));
  font-family: 'Atkinson Hyperlegible', ui-sans-serif, system-ui, sans-serif;
}
```

**shadcn install command**:
```bash
cd frontend && npx shadcn@latest init -d
# When prompted: base color = neutral, CSS variables = yes
```

Then patch `components.json` and the generated `globals.css` block to use our HSL variables above. shadcn's CVA recipes will pick up our `--background`, `--foreground`, `--primary`, etc. through the Tailwind config bridge.

---

## Placeholder page template

Every placeholder page uses this exact template (in `frontend/src/components/layout/PlaceholderLayout.tsx`):

```tsx
import { type ReactNode } from 'react';
import { Link } from 'react-router-dom';

interface PlaceholderLayoutProps {
  title: string;
  uxSpecSection: string;  // e.g. "§15 Account Settings"
  children?: ReactNode;   // for dev-bypass buttons
}

export function PlaceholderLayout({ title, uxSpecSection, children }: PlaceholderLayoutProps) {
  return (
    <main data-testid="page-placeholder" className="mx-auto max-w-3xl px-6 py-12">
      <nav aria-label="Breadcrumb" className="mb-4 text-sm text-fg-muted">
        <Link to="/dashboard">Dashboard</Link> / {title}
      </nav>
      <h1 className="text-3xl font-bold">{title}</h1>
      <p className="mt-4 text-fg-muted">
        Placeholder. See <code>ux-spec.md</code> {uxSpecSection} for the full feature spec.
      </p>
      {children}
    </main>
  );
}
```

13 placeholder pages render `<PlaceholderLayout title="..." uxSpecSection="..." />`. The four with dev bypasses pass the bypass button as children.

---

## The 6 anchor tests

In `playwright.config.ts`:

```typescript
import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './frontend/tests',
  use: {
    baseURL: 'http://localhost:5173',
    launchOptions: {
      args: [
        '--use-fake-ui-for-media-stream',
        '--use-fake-device-for-media-stream',
      ],
    },
  },
});
```

### Spec 1: `e2e/auth.signin.dev-bypass.spec.ts`
```
test: visit /signin, click [data-testid="dev-skip-login"], expect URL to match /dashboard,
expect h1 to contain "Dev User" or "Welcome".
```

### Spec 2: `e2e/dashboard.heatmap.dev-account.spec.ts`
```
test: sign in via dev bypass, expect [data-testid="heatmap-cell"] count = 75,
expect at least 30 cells with intensity class "intensity-0" (gray, no practice),
expect at least 5 cells with "intensity-3" (heavy day).
Expect [data-testid="mastery-progress"] text to contain "38 / 75".
```

### Spec 3: `e2e/practice.dev-mock.full-flow.spec.ts`
```
test: sign in, visit /lessons/lesson-1/practice,
click [data-testid="dev-set-orange"], expect box to have class "border-status-ok" → no
  (sets currentBoxState='hands-detected', box turns orange).
Click [data-testid="self-report-got-it"] three times → drill advances from Handshape to Movement.
Click [data-testid="self-report-got-it"] three more times → drill advances from Movement to Sign.
Click [data-testid="self-report-got-it"] three more times → sign completes,
  next sign appears OR Lesson Complete page appears.
```
(Note: this verifies the state machine transitions, not the full 9-rep progression — softer than original AC #9.)

### Spec 4: `e2e/practice.modes.toggle-flow.spec.ts`
```
test: visit /lessons/lesson-1, toggle "Show instructor reference video" OFF,
click Start, expect [data-testid="reference-panel"] to NOT exist on Practice Screen,
expect [data-testid="camera-panel"] to exist.
Repeat for camera-off: expect [data-testid="self-report-row"] to exist, no camera-panel.
(This verifies toggles PERSIST and PASS the value through. Layout-reflow correctness is feature work.)
```

### Spec 5: `a11y/dashboard.axe-scan.spec.ts`
```
test: sign in, visit /dashboard, run @axe-core/playwright,
expect 0 violations at WCAG 2.2 AA.
```

### Spec 6: `e2e/routes.smoke.spec.ts`
```
const ROUTES = ['/', '/signup', '/signin', /* ...all 23 from Route Map... */];
for each route:
  test: visit route, expect no console.error events, expect [data-testid] present
    (either page-placeholder for stubs or page-real for real pages).
```

### Vitest unit specs

- `tests/unit/practice-machine.spec.ts` — XState transitions: Idle → Active → SelfReport on `done` event; SelfReport → next drill on `pass`; SelfReport → retry on `fail`.
- `tests/unit/seed.spec.ts` — Run seed, query DB, assert dev user has 38 mastery rows, X rep_log rows in the prescribed buckets, streak_state and notification_pref present.

---

## PWA configuration

`vite.config.ts`:

```typescript
import { VitePWA } from 'vite-plugin-pwa';
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.ico'],
      manifest: {
        name: 'ASL Pilot',
        short_name: 'ASL Pilot',
        description: 'Vocabulary practice for ASL 1 learners',
        theme_color: '#1c1c1c',
        background_color: '#1c1c1c',
        display: 'standalone',
        start_url: '/',
        icons: [/* 192 + 512 placeholder SVGs */],
      },
      workbox: {
        // App shell precaching — Workbox handles this automatically
        // Runtime caching for reference videos with strict limits
        runtimeCaching: [
          {
            urlPattern: /\/videos\/.*\.mp4$/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'reference-videos',
              expiration: { maxEntries: 10, maxAgeSeconds: 7 * 24 * 60 * 60 },
            },
          },
        ],
        // DON'T precache videos — they're served on demand
        globIgnores: ['**/*.mp4'],
      },
    }),
  ],
});
```

No install banner, no Add-to-Home-Screen prompt in scaffold.

---

## Acceptance criteria

Scaffold milestone is done when **every** statement below is true:

| # | Criterion | How to verify |
|---|---|---|
| 1 | Fresh clone runs end-to-end via `local-setup.md` | Walk through; reach `npm run dev` without errors |
| 2 | `docker compose ps` shows postgres healthy on 5432, adminer on 8088 | Visual check |
| 3 | `npm run db:migrate` applies all migrations cleanly | Exit code 0 |
| 4 | `npm run db:seed` creates the dev account; `tests/unit/seed.spec.ts` passes | Vitest run |
| 5 | Sign-in page renders; `[Dev: Skip login]` lands on Dashboard | Manual + spec 1 |
| 6 | Dashboard shows populated heatmap, mastery bar "38 / 75", 3+ recent lessons | Manual + spec 2 |
| 7 | All 23 routes exist and render without console errors | Spec 6 (routes smoke) |
| 8 | `[Set Gray]` / `[Set Orange]` / `[Set Green]` change the bounding box | Manual + spec 3 |
| 9 | Practice Screen state machine transitions on self-report click | Spec 3 + unit spec |
| 10 | Lesson Intro toggles persist and pass values to Practice Screen | Spec 4 |
| 11 | `npm test` passes all 6 anchor specs + Vitest unit specs | CI-style run |
| 12 | axe-core scan of Dashboard returns 0 violations | Spec 5 |
| 13 | Atkinson Hyperlegible (proportional) is the only sans font; JetBrains Mono for mono | DevTools computed styles |
| 14 | Color palette matches token map exactly | DevTools inspection |
| 15 | No leftover scaffolding boilerplate (no Vite splash, no shadcn placeholder copy) | Visual sweep |
| 16 | Backend exits gracefully with clear message if migrations not run | Manual: clear DB, start backend, observe stderr |

**Removed from scaffold AC** (moved to launch-prep milestone):
- Production-build dev-affordance scrub (`VITE_DEV_MODE=0` guardrail)
- Full Handshape → Movement → Sign 9-rep progression (was AC #9 over-spec)
- Practice mode layout reflow correctness (was AC #10 over-spec)
- Lesson Complete delta computation (was a deliverable; now static render)
- Settings → Lesson Intro pre-fill propagation (was a deliverable; now persist-only)

---

## Sequence of work

1. Root `package.json` with workspaces, `.nvmrc`, `tsconfig.base.json`, `.gitignore` audit
2. Backend: Drizzle config, `schema.ts`, initial migration; `client.ts`; startup safety check; health route
3. Backend: auth route (dev-login + /me), session helper, CORS, cookie config
4. Backend: lessons + progress routes
5. Frontend init: Vite + React + TS, Tailwind v3.4, shadcn install with `--base-color neutral`, brand tokens in `globals.css`
6. Frontend lib: `env.ts`, `api.ts` (credentials: include), `auth.ts` hook, `constants.ts`
7. Frontend routing: 23 placeholder pages + 10 real ones via `router.tsx`
8. CV mock module (`types.ts`, `evaluate.mock.ts`, `evaluate.ts`)
9. Sign-in page with working `[Dev: Skip login]`
10. Dashboard with heatmap + mastery bar + recent lessons (backend-driven)
11. Lesson Catalog → Lesson Intro → Practice Screen (mock CV + dev panel + self-report row) → Lesson Complete (static)
12. Settings page (persist-only)
13. Seed script (catalog + dev user, idempotent)
14. PWA via `vite-plugin-pwa`
15. Playwright + Vitest specs (6 e2e + 2 unit)
16. README

Don't ship until step 16. Don't skip seeding — the dashboard looks broken without it.

---

## Open questions (defaults will be used if no answer)

1. **App name in copy**: default "ASL Pilot"
2. **Hero image**: default `TODO: hero image` marker (no generated art yet)
3. **Light-mode support**: default OUT of scope for scaffold
4. **TimeBack platform integration**: out of scope; document for v1

---

## What to skip vs do — concrete examples

| Scenario | Do | Don't |
|---|---|---|
| "Implement the full SRS scheduler" | Advance one stage on pass, regress on miss | 1d/3d/7d/14d expanding intervals |
| "Per-sign per-parameter hint strings" | One hardcoded "Try again — focus on the handshape." | 75 × 6 = 450 strings |
| "Heatmap keyboard nav" | Arrow keys cycle day cells, axe-core enforces ARIA labels | Skipping a11y because it's "scaffold" |
| "Sign-up email verification" | Placeholder + `[Dev: Create local account]` | SMTP wiring |
| "Reference videos" | One `hello.mp4` placeholder | Real Deaf-signer production |
| "Forms validation" | React Hook Form + Zod, basic shape | Custom field validators |
| "Dark mode" | Ship dark-only | Theme switcher |
| "Public sign dictionary" | Skip entirely | `/signs/<slug>` pages |

---

## Done definition for this PRD

A coding agent can execute this PRD + the linked docs without follow-up questions. All 16 ACs are objectively verifiable. The PRD has been reviewed by a 3-agent swarm and the major blockers found have been resolved in this revision.
