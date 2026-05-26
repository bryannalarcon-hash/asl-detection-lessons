# PRD / Spec Implementation Gap Audit

Code-verified audit of the ASL Pilot app against its spec/PRD docs. Status is
determined by reading the actual code, not by trusting the docs. Date: 2026-05-25.

Scope note: this audit covers the **web app** (frontend/backend) + the
**CV interface contract** (ml-handoff). It does NOT re-derive ML accuracy
numbers — `docs/SWARM_FINDINGS.md` covers the 4-net model accuracy story and
its conclusions (e.g. Net 4 top-3 ceiling ~0.45-0.60, Net 3 PCK targets
unreachable under Req 7) are taken as given here.

Legend: DONE = implemented and wired; PARTIAL = present but incomplete or not
wired into the live path; MISSING = absent.

---

## Source: docs/prd-scaffold.md (scaffold milestone — primary)

### Repository / tooling / build

| Requirement | Status | Evidence / Gap |
|---|---|---|
| npm workspaces monorepo (frontend, backend) | DONE | `package.json` scripts use `npm --workspace frontend/backend`; both workspaces present |
| `npm run dev` / `dev:api` / `db:migrate` / `db:seed` / `test` scripts | DONE | `package.json` lines: `dev`, `dev:api`, `db:migrate`, `db:seed`, `test`, `test:unit`, `test:e2e`, `typecheck` |
| Node >=20.11 engine | DONE | `package.json` `engines.node: ">=20.11.0"` |
| `scripts/seed-dev-user.ts` exists, idempotent | DONE | `scripts/seed-dev-user.ts`; wipes dev-user state then reseeds; catalog upsert is find-or-update |

### Route map (23 pages)

| Requirement | Status | Evidence / Gap |
|---|---|---|
| All 23 routes registered | DONE | `frontend/src/router.tsx` registers every route in the map (landing, signup, signin, forgot-password, verify-email, 4 onboarding, dashboard, lessons, lessons/:slug, practice, complete, 3 settings, privacy, help, about, camera-denied, offline, `*` 404). Plus a dev-only `/dev/lesson-config`. |
| 1 Landing `/` (real, minimal) | DONE | `pages/Landing.tsx` — hero, scope statement, 3 privacy/self-paced/original bullets, sign-in/up CTAs, footer |
| 2 Sign-up `/signup` (placeholder + dev bypass) | DONE+ | `pages/SignUp.tsx` (7.5KB) — real RHF/Zod form AND dev bypass; exceeds scaffold ask |
| 3 Sign-in `/signin` (real, dev skip) | DONE | `pages/SignIn.tsx`; `components/auth/SkipLoginButton.tsx` |
| 4 Forgot password (placeholder + dev bypass) | DONE+ | `pages/ForgotPassword.tsx` (4.4KB) — full form, not a bare stub |
| 5 Email verification (placeholder + dev bypass) | DONE+ | `pages/VerifyEmail.tsx` (4.4KB) — code-input UI, `testid page-verify-email` |
| 6 Onboarding Welcome (real) | DONE | `pages/OnboardingWelcome.tsx` |
| 7 Onboarding Camera (real getUserMedia) | DONE | `pages/OnboardingCamera.tsx` — real `request()` via `useCameraPermission`, no-upload copy, dev force-state toolbox |
| 8 Onboarding Calibration (real, framing guide) | PARTIAL | `pages/OnboardingCalibration.tsx` is only 1.7KB. Live preview present but the dashed head/shoulders/hands silhouette overlay + "hands in frame?" auto-detect + mirror toggle (ux-spec §8) need verification; file is too small to contain the full calibration UI |
| 9 First-Sign Tutorial (placeholder → dashboard) | PARTIAL | `pages/FirstSignTutorial.tsx` uses `PlaceholderLayout` (1.2KB). Matches PRD's "placeholder that routes to Dashboard" — but the endowed-progress mastery tick + faded-hint tutorial logic (principles.md, ux-spec §9) is feature work, still absent |
| 10 Dashboard (real) | DONE | `pages/Dashboard.tsx` + `components/dashboard/{Heatmap,MasteryBar,RecentLessons,StreakIndicator}.tsx` |
| 11 Lesson Catalog (real) | DONE | `pages/LessonCatalog.tsx` (6KB) |
| 12 Lesson Intro (real) | PARTIAL | `pages/LessonIntro.tsx` — sign list + camera/reference toggles + start CTA + back-nav all real. MISSING from ux-spec §12: per-sign thumbnail + reference-video preview modal, difficulty 1-3 dots, category badge, already-mastered check overlay |
| 13 Practice Screen (real) | DONE (mock-CV) | `pages/Practice.tsx` (18KB) — drill machine, camera/reference panels, dev panel, self-report row, hint, pause, resume cursor, toast |
| 14 Lesson Complete (real, static) | DONE | `pages/LessonComplete.tsx` — confirms static: per-sign `pct = 60 + ((i*13)%35)` is fabricated, not computed (matches "static render, NOT computed deltas") |
| 15 Account Settings (placeholder) | DONE | `pages/AccountSettings.tsx` — `PlaceholderLayout §15` |
| 16 App Settings (real, persist-only) | DONE | `pages/AppSettings.tsx` (4.2KB) + `lib/settings.ts` (localStorage persist) |
| 17 Notification Prefs (placeholder) | DONE | `pages/NotificationSettings.tsx` — `PlaceholderLayout §17` |
| 18 Privacy & Data (placeholder) | DONE (as stub) | `pages/Privacy.tsx` — `PlaceholderLayout §18`. NOTE: see Privacy section below; the *guarantee* is real but this page has no plain-language copy/export/deletion controls |
| 19 Help / How It Works (placeholder) | DONE | `pages/Help.tsx` — `PlaceholderLayout §19` |
| 20 About / Credits (placeholder) | DONE (as stub) | `pages/About.tsx` — `PlaceholderLayout §20`. Deaf-signer credits (ux-spec §20, principles cultural-framing) are NOT present anywhere |
| 21 Error Camera Denied (real) | DONE | `pages/CameraDenied.tsx` (2.5KB) — browser re-enable instructions |
| 22 Error Offline (placeholder) | DONE | `pages/Offline.tsx` — `PlaceholderLayout §22` |
| 23 404 (real wildcard) | DONE | `pages/NotFound.tsx`, `*` route |

### Database schema

| Requirement | Status | Evidence / Gap |
|---|---|---|
| All 8 tables (user, lesson, sign, drill_definition, rep_log, mastery_state, streak_state, notification_pref) | DONE | `backend/src/db/schema.ts` defines all 8 with exact columns/enums |
| `user_email_lower_unique` functional index on LOWER(email) | DONE | `schema.ts:41` `uniqueIndex(...).on(sql\`lower(${t.email})\`)` |
| `mastery_state` compound PK (user_id, sign_id) | DONE | `schema.ts:110` `primaryKey({ columns: [userId, signId] })` |
| `rep_log` user+date index | DONE | `schema.ts:91` `rep_log_user_date_idx` |
| Migrations present | DONE | `backend/src/db/migrations/0000_*.sql` + `0001_add_password_hash.sql` |
| `password_hash` column (beyond PRD) | DONE+ | `schema.ts:36` — added for real auth, not in original PRD scaffold schema (intentional scope growth) |

### Seed data

| Requirement | Status | Evidence / Gap |
|---|---|---|
| Dev user dev@asl-pilot.local, created 75 days ago | DONE | `seed-dev-user.ts` `DEV_EMAIL`, `DEV_CREATED_DAYS_AGO=75` |
| 12 lessons | DONE | `LESSON_CATALOG` has 12 entries |
| ~75 signs × 3 drill_definition rows | DRIFTED | Catalog grew to **96 signs** (`TOTAL_SIGNS=96`), not 75. Each sign still gets 3 drills. This is intentional (catalog = the 96 PopSign Net-4 vocabulary) but **conflicts with the backend's hardcoded `TOTAL_SIGNS=75`** (see Consistency below) |
| 38 mastery rows split 12/9/8/5/4 | DONE | `MASTERY_BUCKETS` = {mastered:12, known:9, familiar:8, learning:5, new:4} = 38; `distributeMastery()` |
| rep_log 75 days, distribution buckets + streak windows | DONE | `generateRepLogData()` implements 40/25/25/10 buckets, 14-day block ending 18d ago, current 4-day streak, two blips |
| streak_state current=4 longest=14 freezes=2 | DONE | `seedStreakAndPrefs()` |
| notification_pref reminder 19:00, weekly on, at-risk off | DONE | `seedStreakAndPrefs()` |

### CV mock module

| Requirement | Status | Evidence / Gap |
|---|---|---|
| `cv/types.ts` exact shapes (Frame, DrillType, DetectionResult, InitResult) | DONE | `frontend/src/cv/types.ts` matches PRD verbatim |
| `cv/evaluate.mock.ts` — init/processFrame/evaluateRep/reset/dispose, never returns target-met, `__devSetBoxState` | DONE | mock never auto-passes; `DevPanel.tsx` imports `__devSetBoxState` from `@/cv/evaluate` |
| `cv/evaluate.ts` re-exports mock | DONE (intended), but see ml-handoff gap | `evaluate.ts` = `export * from './evaluate.mock'`. The real port exists (`evaluate.real.ts`) but is NOT wired |
| Dev panel Set Gray/Orange/Green + Skip drill + Auto-pass rep | DONE | `Practice.tsx:442-449` wires all five; green is purely visual, mastery via self-report |

### API contract

| Requirement | Status | Evidence / Gap |
|---|---|---|
| POST /api/auth/dev-login (404 in prod) | DONE | `routes/auth.ts:186` gated by `DEV_TOOLS_ENABLED !== '0'` → 404 |
| POST /api/auth/sign-out | DONE | `routes/auth.ts:224` |
| GET /api/auth/me (note: `/me` mounted under `/api/auth`, PRD said `/api/me`) | DONE (path differs) | `routes/auth.ts:234` is `/me` under `/api/auth` → `/api/auth/me`, not `/api/me` |
| POST /api/progress/rep (mastery advance/regress/skip) | DONE | `routes/progress.ts:81` advance/regress logic + streak update |
| GET /api/progress/dashboard | DONE | `routes/progress.ts:204` masterySummary/heatmap/recentLessons/streak |
| GET /api/lessons + /api/lessons/:slug | DONE | `routes/lessons.ts` |
| GET /api/health | DONE | `routes/health.ts` exists |
| GET /api/progress/day/:date (post-scaffold addition) | DONE | `routes/progress.ts:355` |
| Session cookie `asl_session`, httpOnly, sameSite=lax, **signed** | PARTIAL | `lib/session.ts` — cookie is httpOnly+lax but **plain UUID, NOT signed/HMAC** (code comments admit this). PRD §API said "signed". Functionally OK for dev; a real gap vs the written contract |
| CORS origin localhost:5173, credentials | DONE | `lib/cors.ts` |
| Backend startup migration safety (exit 1 with clear message) | DONE | `index.ts:32` `ensureMigrationsApplied()` prints "Run npm run db:migrate first" + exit 1 |

### Tests / a11y

| Requirement | Status | Evidence / Gap |
|---|---|---|
| 6 anchor specs (5 e2e + routes smoke) | DONE | `tests/e2e/{auth.signin.dev-bypass, dashboard.heatmap.dev-account, practice.dev-mock.full-flow, practice.modes.toggle-flow, routes.smoke}.spec.ts` + `tests/a11y/dashboard.axe-scan.spec.ts` all present, plus ~12 extra e2e |
| Vitest unit: practice-machine + seed | DONE | `tests/unit/practice-machine.spec.ts`, `tests/unit/seed.spec.ts` (+ cv-features, cv-verifier, dev-tools-gate, etc.) |
| axe-core 0 violations on Dashboard | NOT RE-RUN | Spec file exists (`dashboard.axe-scan.spec.ts`); pass/fail not verified in this audit |

### Practice state machine

| Requirement | Status | Evidence / Gap |
|---|---|---|
| XState v5 nested Lesson>Sign>Drill>Rep machine | PARTIAL | `lib/machines/practice.ts` is a real XState v5 machine with Drill/Rep transitions, back-step, resume-cursor clamping. BUT `Practice.tsx`'s `toFullSignDrills()` **collapses every sign to a single full-sign drill**, so the Handshape→Movement→Sign 3-drill decomposition (ux-spec §"Hierarchy of state machines", principles "drill handshape first") is never actually exercised in the live lesson flow. The machinery exists; the pedagogy doesn't run |
| Self-report drives mastery (Continue/Skip; "Not quite"/FAIL removed) | DONE | `SelfReportRow` → PASS/SKIP; FAIL event defined but only on dev panel |
| Auto-advance on green box | DONE | `Practice.tsx:208-229` green→PASS after 350ms with re-fire latch |

---

## Source: docs/ux-spec.md (23-route UX spec + dev scaffolding)

| Requirement | Status | Evidence / Gap |
|---|---|---|
| Four practice modes from 2 toggles (cam×ref) | DONE | `Practice.tsx` reads `?camera`/`?reference`; renders camera/reference/quiz layouts; `data-mode` attr |
| Camera-OFF collapses drills to one self-report per sign | PARTIAL/MOOT | Drills already collapse to one full-sign stage in ALL modes (see machine note), so camera-off behaves like every mode. Spec's distinct collapse isn't a separate code path |
| Dev scaffolding gated by single flag, stripped from prod | DONE | `lib/env.ts` `isDevToolsEnabled()` (`VITE_DEV_TOOLS`); `router.tsx:34` DCE-drops dev routes; `data-dev-override` attr on dev buttons |
| Dev bypass per auth page (signup/signin/verify/forgot/camera) | DONE | Each auth page carries its labeled `[Dev: …]` affordance; `auth.dev-tools-gating.spec.ts` asserts absence when off |
| `no-dev-affordances` prod test | PARTIAL | `auth.dev-tools-gating.spec.ts` + `dev.lesson-config-gating.spec.ts` cover gating; a single consolidated prod-build `no-dev-affordances.spec.ts` (removal-checklist item 5) not found by that name |
| Bottom toolbar: REC toggle, back-step, back-to-start, help, pause + keyboard shortcuts | PARTIAL | `PracticeHeader` has back-drill/back-sign/camera-toggle/pause/exit; help via `HintButton`. Keyboard shortcuts (M/B/Shift+B/H/Space) from ux-spec table NOT verified present |
| Reference video: slow-mo, segment loop, replay | DONE | `components/practice/ReferenceVideo.tsx` (per HANDOFF_FRONTEND notes: 3-segment, loop, replay, slow-mo) |
| Reference video = real Deaf-signer footage | PARTIAL (placeholder) | `constants.ts` `MOCK_REFERENCE_VIDEO_URL='/videos/nyan.mp4'`; `public/videos/lessons/` dir exists (some per-lesson clips grabbed). Real Deaf-signer production is an explicit non-goal for scaffold |
| Captions (.vtt) on reference video | MISSING | No `.vtt` files in `public/videos/`; ReferenceVideo has no track element verified. a11y checklist + principles require captions |
| Hint: single-parameter, side-by-side replay, faded after 2 passes | PARTIAL | `HintButton` exists + takes `failCount` for adaptive surfacing (`aurora.adaptive-hint.spec.ts`). Side-by-side user-clip-vs-reference replay and faded-after-2-passes are not evidenced; one hardcoded hint per PRD non-goal |
| Microcopy bank applied | DONE (largely) | Practice/landing copy matches bank tone; "Not quite" intentionally removed per HANDOFF_FRONTEND |

### Per-page features still missing (ux-spec §11/§12/§15-20)

| Requirement | Status | Evidence / Gap |
|---|---|---|
| Lesson Catalog: category filter chips, search, state filter, locked-lesson gating | PARTIAL | `LessonCatalog.tsx` renders the grid; filter chips / search / lock states not verified and likely absent in a 6KB file |
| Account Settings real (name/email/password/delete/sign-out-all) | MISSING | Placeholder only |
| Notification Prefs real | MISSING | Placeholder only |
| Privacy page real (summary, stored-fields, JSON export, deletion, FERPA copy) | MISSING | Placeholder only |
| Help page real (how-a-lesson-works, four-modes, why-no-NMM, FAQ) | MISSING | Placeholder only |
| About page real + Deaf-signer credits | MISSING | Placeholder only; no credits anywhere in the app |
| Offline page real (cached-review degradation) | MISSING | Placeholder only |

---

## Source: docs/ml-handoff.md (CV interface contract)

| Requirement | Status | Evidence / Gap |
|---|---|---|
| `init()` / `processFrame()` / `evaluateRep()` / `resetRepBuffer()` / `dispose()` interface | DONE (both impls) | mock in `evaluate.mock.ts`; real in `evaluate.real.ts` implements all five + `setTarget`/`setVerifierParams` |
| Real WebGPU/WASM-backed port exists | DONE | `cv/evaluate.real.ts` + `cv/ort/{session,models}.ts` + `cv/pipeline/{stage1,stage2,verifier,features,geom,anchors}.ts`; ONNX models present in `public/models/{net1,net2,net3,net4}.onnx` (~64MB total) |
| **Real CV wired into the live app** (Req 5 browser-first inference) | **MISSING / NOT WIRED** | `evaluate.ts` still `export * from './evaluate.mock'`. No page/component imports `evaluate.real`, `processFrame`, or `evaluateRep` (grep: only `@/cv/types` type imports + `__devSetBoxState` from the mock). `CameraPanel` shows raw `<video>` only; its `matchScore` prop is never fed by CV (always undefined in `Practice.tsx`). The real cascade is fully built but **dead code** from the app's perspective — the live experience is still mock + self-report |
| `evaluateRep` never falsely returns target-met (OOD guard, Req 7) | DONE (contract level) | mock never returns target-met; real port routes through `SignVerifier` with confidence/vote thresholds |
| Bundle ≤ 25MB total (INT8/distill) | AT RISK | `public/models/net1.onnx` alone is **53.5MB** (net2 1.4MB, net3 5.9MB, net4 4.2MB) → ~65MB, **well over the 25MB target and the 40MB ceiling**. These are not quantized for web deploy |
| Models served from `/public/models/` | DONE | all four `.onnx` present |
| Test fixtures (labeled frame sequences per drill type) in `frontend/test-fixtures/cv/` | MISSING | No `frontend/test-fixtures/cv/` dir; unit tests `cv-features.spec.ts`/`cv-verifier.spec.ts` use `tests/unit/__fixtures__` instead, not the handoff-specified fixture set |
| `processFrame` p95 ≤ 33ms / `evaluateRep` p95 ≤ 200ms on low-spec laptop | UNVERIFIED | No in-app benchmark; not measurable since CV is unwired in app. `evaluate.real` uses `processEveryN=3` cadence to amortize but no measured numbers |
| v2 deploy gates (top-1 ≥92%, top-3 ≥98%, OOD ≥90%, A/B) | NOT MET | Per SWARM_FINDINGS, honest Net-4 ceiling is top-3 ~0.45-0.60; these gates are explicitly aspirational. CV stays in mirror/self-report mode |
| `evaluate.real` config requires `glossToIdx` (net4 gloss_to_idx) | DONE (port) / GAP (app) | `RealCvConfig.glossToIdx` required; the app has no init call passing it, since CV is unwired |

---

## Source: docs/principles.md (pedagogy + UX principles)

| Requirement | Status | Evidence / Gap |
|---|---|---|
| Scope-honest copy ("vocabulary practice, not ASL translation") | DONE | Landing footnote + onboarding; "not full ASL" framing present |
| Sign Mirror + self-report as v1 mechanism | DONE | Self-report row drives mastery; CV not gating |
| Drill handshape first, then movement | NOT IMPLEMENTED | Drills collapsed to single full-sign stage (`toFullSignDrills`); handshape-first ordering never runs in the live flow despite being the "load-bearing pedagogical decision" |
| 5-stage mastery (New→Learning→Familiar→Known→Mastered) | DONE | `masteryLevelEnum` + advance/regress in `routes/progress.ts` |
| Mastery bars primary, soft streak secondary, 2 freezes | DONE | MasteryBar + StreakIndicator + `freezesRemaining` default 2 |
| No public leaderboard / no shame loss-state | DONE | None present |
| Hint priority order (handshape→...→framing) | MISSING | Single hardcoded hint (PRD non-goal); `DetectionResult.parameter` field exists but no priority logic |
| Endowed progress: pre-mastered HELLO/THANK YOU in tutorial | MISSING | FirstSignTutorial is a placeholder; no endowed-progress tick |
| Deaf-signer reference videos, credited | MISSING | Placeholder nyan/per-lesson clips; no credits (About is a stub) |
| Captions on reference videos | MISSING | No .vtt tracks |
| WCAG 2.2 AA, prefers-reduced-motion, focus rings, color+icon pairing | PARTIAL | axe scan spec exists; reduced-motion honored in heatmap/buttons (per HANDOFF). Full-app AA conformance not re-run here |
| FERPA / privacy copy ("video stays on device") | PARTIAL | The *guarantee* holds in code (camera is local getUserMedia, no frame upload anywhere — verified); the *copy* appears on Landing/onboarding but the Privacy page itself is a stub with no detailed/FERPA copy, export, or deletion controls |

---

## Privacy guarantee — code-level verification (Req 13)

| Claim | Status | Evidence |
|---|---|---|
| No video/frame upload anywhere | DONE | `CameraPanel.tsx` binds `getUserMedia` stream to a local `<video>`; no `fetch`/`POST` of frames in any component. `lib/api.ts` only sends rep outcomes (signId/drillType/outcome/source). Camera stream stays in-browser |
| In-browser CV (no server inference) | DONE (by design) / UNWIRED | The real port runs ORT in-browser (no network calls in `evaluate.real.ts`), but it isn't wired into the app yet, so today there is no inference at all |
| Only rep outcomes leave the device | DONE | `routes/progress.ts` `/rep` body = signId/drillType/outcome/source/hintRequested — no frames/keypoints |

---

## Cross-cutting consistency gaps (doc/over-claim flags)

1. **Catalog size vs mastery denominator mismatch.** Seed inserts **96** signs
   (`seed-dev-user.ts TOTAL_SIGNS=96`) but the backend dashboard hardcodes
   `TOTAL_SIGNS = 75` (`routes/progress.ts:21`) and the frontend constant is
   also `75` (`lib/constants.ts:3`). The mastery bar reads "38 / 75 signs in
   progress" while the actual catalog has 96 signs. The "38/75" anchor test
   (PRD spec 2) still passes against the hardcoded 75, but the number no longer
   reflects reality.

2. **`/api/me` path drift.** PRD §API lists `GET /api/me`; code mounts it as
   `GET /api/auth/me`. Frontend uses the latter, so internally consistent, but
   the written contract differs.

3. **Session cookie "signed" over-claim.** PRD §API states the cookie is
   "signed"; `lib/session.ts` stores a **plain UUID** (no HMAC). Documented in
   code comments as deliberate dev-grade, but the contract says otherwise.

4. **HANDOFF_FRONTEND says "12/12 e2e green"** — there are ~18 e2e specs now;
   the count in the doc is stale (not a code bug, a doc-staleness flag).

5. **ml-handoff implies a one-file swap to ship CV.** True structurally, but
   the swap also requires: bundle quantization (65MB → ≤25MB), an `init()` call
   wiring `glossToIdx` + model URLs into the app, feeding `processFrame` from
   `CameraPanel`, and routing `evaluateRep` into the rep machine. None of that
   app-side glue exists yet.

---

## Top missing requirements (ranked by importance)

1. **Real CV is built but not wired into the app (ml-handoff Req 5).** The
   entire ORT/WebGPU cascade (`cv/evaluate.real.ts`, `cv/pipeline/*`,
   `cv/ort/*`) and all four ONNX models exist, yet `evaluate.ts` still exports
   the mock and no component calls `processFrame`/`evaluateRep`. The flagship
   "camera-aware" capability does not run in the live experience. This is the
   single largest gap between what the repo contains and what the app does.

2. **Model bundle is ~65MB, far over the 25MB target / 40MB ceiling.**
   `net1.onnx` alone is 53.5MB, unquantized. Even once wired, this fails the
   ml-handoff performance budget and would make in-browser load impractical on
   the target laptop. Quantization/distillation is a prerequisite to shipping CV.

3. **Drill decomposition (handshape→movement→sign) never runs.** `Practice.tsx`
   collapses every sign to one full-sign stage, so the "drill handshape first"
   pedagogy — called the load-bearing decision in principles.md — is inert. The
   XState machine supports it; the lesson-build path discards it.

4. **Six content/feature pages are still bare placeholders that matter for a
   real pilot:** Privacy & Data (detailed copy + export + deletion + FERPA),
   About/Credits (Deaf-signer credits — a cultural-framing requirement in
   principles.md), Help/How-It-Works, Account Settings, Notification Prefs, and
   Offline degradation. The PRD marks these placeholder for the *scaffold*, but
   they block a learner-facing launch.

5. **Reference videos: no real Deaf-signer footage and no captions.** Placeholder
   clips only; captions (.vtt) are an accessibility hard-requirement
   (principles.md + ux-spec a11y checklist) and are absent. Tied to the missing
   Deaf-signer recruitment / credits.

6. **Catalog/denominator inconsistency (96 signs vs hardcoded 75).** Low effort
   to fix but currently makes the headline progress number wrong relative to the
   actual catalog.
