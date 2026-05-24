# UX Spec — Pages, Features, and the Practice Screen

Reference for the v1 site build. Reads from [`principles.md`](./principles.md) (research synthesis) and the partner-project requirements. CV is black-boxed; bounding-box semantics are noted where they depend on the ML team's deliverables.

> **Reading order**: this doc is the *as-designed* spec from the scaffold milestone. For *as-built* state and recent changes (state machine fixes, sign-complete toast, GitHub-style heatmap, cyan secondary accent, removed "Not quite" button, resume cursor, etc.), see `/docs/handoffs/HANDOFF_FRONTEND.md` in the repo root and the §"Implementation notes — post-scaffold changes" section at the end of this file.

---

## Naming hierarchy

| Level | Name | Example |
|---|---|---|
| Top container | **Course** | "ASL 1 Vocabulary" |
| Themed group of signs | **Lesson** | "Lesson 1: Greetings" — ~8–12 signs |
| One vocab item | **Sign** | THANK YOU |
| Parameter-focused mini-stage | **Drill** | Handshape Drill → Movement Drill → Sign Drill |
| One attempt | **Rep** | 3 per drill |

Hierarchy: `Course > Lesson > Sign > Drill > Rep`. Complex signs add extra drills before the final Sign Drill (e.g., Initial-Handshape Drill → Final-Handshape Drill → Movement Drill → Sign Drill).

The term **Drill** is established in motor-skill pedagogy and in the 2022 ASL corrective-feedback literature. Avoid "Stage" — collides with the ML team's Stage 1 / Stage 2 model architecture.

---

## Page inventory

| # | Page | Purpose |
|---|---|---|
| 1 | **Landing / Marketing** | Public; explains scope (vocab practice, not ASL translation), links to sign-up |
| 2 | **Sign-up** | Account creation |
| 3 | **Sign-in** | Returning user |
| 4 | **Forgot password / Reset** | Password recovery |
| 5 | **Email verification** | One-time confirmation post sign-up |
| 6 | **Onboarding: Welcome** | First-run, value pitch + scope honesty |
| 7 | **Onboarding: Camera Priming** | NN/g-formula permission explainer |
| 8 | **Onboarding: Calibration** | Camera framing + mirror check |
| 9 | **Onboarding: First-Sign Tutorial** | A trivial sign (HELLO) with extra scaffolding; ends with endowed-progress mastery tick |
| 10 | **Dashboard** | Home; recent lessons, progress bar, month heatmap, "continue" CTA |
| 11 | **Lesson Catalog** | Browse by category, filter, search |
| 12 | **Lesson Intro** | Pre-lesson preview: sign list, estimated time, "Start" |
| 13 | **Practice Screen** | The main camera + drill flow |
| 14 | **Lesson Complete** | Post-lesson summary, mastery changes, next-lesson CTA |
| 15 | **Account Settings** | Email, name, password, sign out, delete account |
| 16 | **App Settings** | Camera device, mirror toggle, audio feedback, font size, reduced motion |
| 17 | **Notification Preferences** | Daily reminder time, weekly summary on/off, channel |
| 18 | **Privacy & Data** | What's stored, data export, deletion controls, FERPA-aware copy |
| 19 | **Help / How It Works** | Camera setup, how Drills work, why we don't grade facial grammar in v1 |
| 20 | **About / Credits** | Deaf signer credits, app scope statement, licensing |
| 21 | **Error: Camera Denied** | Recovery card with browser-specific re-enable steps |
| 22 | **Error: Offline / Service Down** | Graceful degradation; offline allows local-only review of mastered signs |
| 23 | **404 / Not Found** | Standard |

---

## Per-page feature lists

### 1. Landing / Marketing
- Hero: "Practice ASL vocabulary with your camera. 75 beginner signs to start."
- Scope statement (above fold): "This is vocabulary practice, not full ASL learning. Practice with a Deaf instructor for fluency."
- Value bullets (3): private (video stays on device), self-paced, from-scratch model trained by us
- Sign-up / Sign-in CTA
- Footer: privacy, accessibility statement, Deaf signer credits link

### 2. Sign-up
**v1 (local, dev-bypass only)**: A single `[Dev: Create local account]` button generates a random local user, skips verification, lands on Onboarding. No SMTP, no real account creation flow.

**Post-pilot (when we add real users)**: Email + password OR magic link OR OAuth (Google — most likely campus email). Optional display name. Terms / Privacy checkbox (don't pre-check). Honeypot anti-bot. On submit: send verification email, route to verification-pending screen. See `local-setup.md` and `ml-handoff.md` for the auth migration path.

### 3. Sign-in
**v1 (local, dev-bypass only)**: A single `[Dev: Skip login]` button signs in as the seeded `dev@asl-pilot.local`. No real auth backend is wired up.

**Post-pilot**: Email + password OR magic link. "Forgot password" link. "Sign in with Google" if OAuth enabled. Rate-limit failed attempts; show generic error ("email or password incorrect" — never disclose which).

### 4. Forgot password / Reset
**v1**: Hidden — there's no real auth backend to recover credentials for. The `[Dev: Skip — go to reset]` button described in the dev-bypass section exists so the visual page can still be inspected during dev.

**Post-pilot**: Email entry → success message regardless of whether email exists (anti-enumeration). Reset email contains one-time token, 15-minute expiry. Reset form: new password + confirm; force re-sign-in after reset.

### 5. Email verification
**v1**: Hidden (no email sending). `[Dev: Mark verified]` lets devs view the page state and flip the flag locally.

**Post-pilot**: "Check your inbox" pending state. "Resend" button with 60s cooldown. Verified → route to Onboarding: Welcome.

### 6. Onboarding: Welcome
- One screen, three bullets
- Lead with scope: "You're going to learn 75 essential ASL signs"
- Honest disclaimer: "This app checks your hands. For facial grammar, watch the model. For full ASL, practice with a Deaf instructor."
- CTA: "Let's set up your camera"
- Skip button (small, secondary) for returning users

### 7. Onboarding: Camera Priming
- Pre-prompt explainer (NN/g formula): "We need your camera so you can practice signs against a Deaf instructor's example. Your video stays on your device — nothing is uploaded."
- "Turn on camera" button → fires native `getUserMedia()`
- On allow → Calibration
- On deny → Error: Camera Denied

### 8. Onboarding: Calibration
- Live camera preview, mirrored
- Faint dashed silhouette of head + shoulders + hands at 30% opacity (framing guide)
- Auto-detect: are hands in frame?
- Mirror toggle (some users prefer non-mirrored)
- "Looks good — continue" CTA enabled when framing is acceptable

### 9. Onboarding: First-Sign Tutorial
- Trivial sign (HELLO or THANK YOU)
- One Drill cycle: Handshape × 3 reps → Movement × 3 reps → Sign × 3 reps
- Extra scaffolding: reference video plays full-speed AND slow, hint always visible (faded out after 2 successful reps)
- On completion: mastery tick (endowed-progress effect — Nunes & Drèze 2006). Learner enters dashboard with 1/75 already shown.

### 10. Dashboard
**Layout** (top → bottom):
- Greeting + current course progress bar: "47 / 75 signs mastered"
- "Continue last lesson" hero card with thumbnail + sign count remaining
- **Month heatmap**: 5-row × 7-column calendar grid for the current month; each cell colored by activity intensity that day (gray = no practice, light-green = 1 drill, mid = 2–3 drills, dark = 4+ drills). Hover/tap reveals exact counts. Inspired by GitHub contributions but with ASL-appropriate copy ("8 reps on Mar 4").
- **Recent lessons**: horizontally scrollable strip of 3–5 cards (last accessed); each shows lesson title, # signs, completion %
- **Lesson catalog** entry: "Browse all lessons" tile that links to page 11
- **Stats bar** (secondary): current soft-streak count (with freeze indicator), signs mastered this week, total practice time this week
- Top-right: notifications bell, account avatar (links to settings)

**Behavior**:
- Day cells in heatmap accept keyboard nav (arrow keys); ARIA labels announce "March 4, 2026, 8 reps"
- "Continue" defaults to last-accessed lesson with unmastered signs; falls back to first unmastered lesson
- No public leaderboard, no shame state if streak is zero

### 11. Lesson Catalog
- Category filter chips (horizontal): All / Greetings / Numbers / Family / Feelings / Food / Time / Places / Verbs / Question Words
- Lesson grid: each card has title, sign count, est. time (2–4 min/sign × N signs), completion percentage, mastery badge
- Filter by state: Not started / In progress / Mastered
- Search box (sign name + lesson name)
- Locked lessons (if sequential gating used) show lock icon and "complete Lesson X first" hint
- Empty state: "Pick any lesson — you can do them in any order" (if free-order) or guidance toward Lesson 1

### 12. Lesson Intro
- Lesson title, category badge, est. time
- One-paragraph description (what concepts this covers, not what they translate to)
- Sign list: thumbnail (still from Deaf signer's reference video) + English gloss for each sign, ~8–12 entries
- Each thumbnail tappable for a pre-lesson reference-video preview (modal)
- Difficulty indicator: 1–3 dots (based on marked-handshape density and complex-sign count)
- **Practice settings for this lesson** (two independent toggles, both default on, defaults from App Settings):
  - ☑ Camera on (with drill feedback)
  - ☑ Show instructor reference video
  - One-line helper: "Hiding the reference tests recall. Turning off camera switches to self-report."
- Primary CTA: "Start lesson"
- Secondary: "Back to catalog"
- Already-mastered signs in this lesson get a check overlay

#### The four practice modes (from the two toggles)

| Camera | Reference video | Mode | What runs |
|---|---|---|---|
| ON | ON | **Default** | Handshape → Movement → Sign drills × 3 reps each, reference visible |
| ON | OFF | **Recall** | Same drill structure, reference panel hidden; on-demand reference still available via Hint button mid-rep |
| OFF | ON | **Receptive review** | Drill decomposition collapses to 1 self-report per sign; reference plays, learner signs offline, taps "Got it / Not quite / Skip" |
| OFF | OFF | **Quiz** | Prompt only, learner signs from memory offline, self-report |

Camera-OFF modes skip the camera permission ask entirely. Mastery state updates identically in all four modes — the toggle is about *how* a sign is practiced, not whether it counts.

### 13. Practice Screen — the main flow

See dedicated section below. This is the most complex page.

### 14. Lesson Complete
- Celebratory but college-appropriate (no confetti barf):
  - Subtle green checkmark, 600ms gentle scale-in animation
  - "Lesson 1: Greetings — complete"
- Mastery summary table:
  - Signs that advanced (e.g., "THANK YOU: Familiar → Known")
  - Signs that need more practice (deferred / skipped)
- Time spent, total reps, hints requested
- Soft streak update (small): "Day 4 streak"
- Primary CTA: "Next lesson" (pre-populated with the next sequential one)
- Secondary: "Back to dashboard" / "Review this lesson"
- If this completes the course: dedicated end-screen with credit roll for Deaf signers, course stats, "celebrate with a friend" share (no public leaderboard, just a shareable image)

### 15. Account Settings
- Display name
- Email (with verify-on-change flow)
- Change password
- Connected accounts (Google OAuth toggle)
- Sign out (current device)
- Sign out all devices
- **Danger zone**: Delete account → confirmation modal → 7-day soft-delete with recovery email

### 16. App Settings
- **Camera**: device picker (if multiple), mirror toggle, framing-guide on/off
- **Accessibility**: reduced motion (mirrors `prefers-reduced-motion` but lets user override either way), high-contrast, font size (S/M/L)
- **Audio**: feedback sounds (on/quiet/off), volume slider; preview button
- **Practice defaults**:
  - Items per session (6–10 slider)
  - Session length cap
  - **Default camera state for new lessons** (on / off) — pre-fills the Lesson Intro toggle
  - **Default reference-video state for new lessons** (on / off) — pre-fills the Lesson Intro toggle
  - Reference video default playback speed (1x / 0.75x)
  - Auto-advance after pass (off / 800ms / 1500ms)
- **Language**: UI language (English in v1; structured for i18n)
- **Developer mode** (hidden behind 7 taps on About): show CV confidence values, FPS counter

### 17. Notification Preferences
- Daily reminder: time picker + opt-in toggle
- Channel: in-app banner / email / browser push (where supported)
- Weekly summary email: on/off
- Streak-at-risk notification: on/off (default off — anti-anxiety)
- Achievement notifications (mastered N signs, etc.): on/off
- Unsubscribe from marketing — separate from all of the above

### 18. Privacy & Data
- Plain-language summary at top:
  - "Video stays on your device. Nothing is uploaded."
  - "We store: which signs you've practiced, when, and your mastery state."
  - "We don't share data with third parties."
- Detailed list of stored fields with examples
- **Data export**: download JSON of all your data
- **Account deletion**: links to Account Settings flow
- FERPA statement (only if deployed via institution): correct two-prong framing per fact-check
- Cookie policy (if any tracking — minimize)
- Contact for privacy questions

### 19. Help / How It Works
- "How a lesson works" — walks through Handshape → Movement → Sign Drill with screenshots
- "The four practice modes" — explains the camera + reference toggles, when to use each (recall mode for memory test, receptive mode for tired/no-camera situations, quiz mode for spot-checks)
- "Why we don't grade facial expressions" — honest explainer, links to Deaf consultant note
- "Camera troubleshooting" — common issues, browser-specific tips
- FAQ accordion
- Contact / feedback link

### 20. About / Credits
- App scope statement (re-stated): vocabulary practice tool
- **Deaf signer credits**: name, role, compensation note ("All reference signers were Deaf and compensated") — individually credited per Glasser et al. recommendation
- Engineering credits, model architecture credits (hoyso48 acknowledgment per training-plan.md)
- Open-source acknowledgments
- License
- Version + last updated

### 21. Error: Camera Denied
- Clear visual (broken-camera icon, not alarming red)
- "Camera access is blocked. Here's how to re-enable it:"
- Browser-detection-aware instructions:
  - Chrome: "Click the camera icon in the address bar → Allow"
  - Safari: "Safari menu → Settings for this site → Camera: Allow"
  - Firefox: similar
- "I've re-enabled it" → re-attempt button
- Fallback: "Continue without camera" → browse-only mode (view reference videos, no practice)

### 22. Error: Offline / Service Down
- "You're offline" or "Service is down" detection
- If cached reference videos exist: allow review of mastered signs offline
- If lesson data not cached: show offline message with retry
- Service worker should cache critical UI + recent lessons

### 23. 404 / Not Found
- "We couldn't find that lesson." Link back to dashboard.

---

## Practice Screen — the deep dive

### Layout (desktop)

```
┌──────────────────────────────────────────────────────────────────┐
│  ← Lesson 1: Greetings              Sign 3 of 8     [pause][exit]│
│  [████████░░░░░░░░░░] 38%                                        │
├──────────────────────────────────────────────────────────────────┤
│  Sign: THANK YOU                                                 │
│  ─────────────                                                   │
│                                                                  │
│  Drill: ●━━━━━━━━○━━━━━━━━○    Rep 2 of 3                       │
│         Handshape Movement  Sign                                 │
│                                                                  │
│  ┌──────────────────────────┐   ┌──────────────────────────┐    │
│  │ ┃ YOUR CAMERA            │   │  REFERENCE               │    │
│  │ ┃ (mirrored)             │   │  (Deaf signer)           │    │
│  │ ┃                        │   │                          │    │
│  │ ┃  [orange bounding box  │   │  slow/normal toggle      │    │
│  │ ┃   when hands detected] │   │  loops automatically     │    │
│  │ ┃                        │   │                          │    │
│  │ ┃        ● REC           │   │                          │    │
│  │ ┗━━━━━━━━━━━━━━━━━━━━━━━┛   └──────────────────────────┘    │
│                                                                  │
│  ╭───────────── Bottom Toolbar ────────────────────────╮         │
│  │ [●REC on/off]  [← back step]  [⟲ back to start]  [?]│         │
│  ╰─────────────────────────────────────────────────────╯         │
│                                                                  │
│  ╭─── DEV PANEL (hidden in prod) ───────────────────────╮        │
│  │ Mock CV state for current drill:                     │        │
│  │ [▓ Set Gray]  [▓ Set Orange]  [▓ Set Green]          │        │
│  │ [↪ Skip drill]   [✓ Auto-pass rep]                   │        │
│  ╰──────────────────────────────────────────────────────╯        │
└──────────────────────────────────────────────────────────────────┘
```

### Layout reflow by mode

The wireframe above is the default (camera ON, reference ON) layout. Other modes reflow:

- **Reference OFF, camera ON**: reference panel hidden; camera panel centers and grows to fill horizontal space. Hint button still opens reference on-demand mid-rep.
- **Camera OFF, reference ON**: camera panel hidden; reference panel centers and grows. Action zone replaces drill state machine with a single per-sign self-report row: `[I got it]  [Not quite]  [Skip]`. Drill indicator and rep counter disappear (no drill decomposition in camera-off modes).
- **Both OFF (Quiz)**: only the prompt card and self-report row are visible. Camera-permission flow is never triggered. This is the minimum-friction recall test.

### Hierarchy of state machines

A Lesson runs a state machine over Signs. In camera-ON modes, a Sign runs a state machine over Drills, and each Drill runs over Reps; back-step-1 exits within Sign, back-to-lesson-start exits to Lesson. In camera-OFF modes, the Sign-level machine collapses: a Sign is one self-report (Got it / Not quite / Skip) and back-step has no meaning within a Sign.

```
LESSON_RUNNING
  └─ for each Sign in lesson.signs:
       SIGN_INTRO (250ms — show sign name + brief reference clip auto-plays)
       └─ DRILL: HANDSHAPE
            ├─ REP 1 → REP 2 → REP 3   (each rep: see Rep state machine)
            └─ on completion → DRILL: MOVEMENT
       └─ DRILL: MOVEMENT
            └─ same 3-rep cycle
       └─ DRILL: SIGN
            └─ same 3-rep cycle
       └─ SIGN_COMPLETE (positive feedback animation, 800ms)
  └─ LESSON_COMPLETE (→ page 14)
```

### Rep state machine

```
REP_IDLE (camera always on, gray box if no hands; orange if hands detected)
  └─ user signs naturally — system auto-detects start (hands enter sign-space)
     OR explicit "Start rep" if user prefers manual
REP_ACTIVE (recording window opens, ~3s, orange box)
  ├─ v1: window expires → SELF_REPORT (user taps "I got it" / "Not quite" / "Skip")
  │       "I got it"  → REP_PASS (green box, positive feedback, advance)
  │       "Not quite" → REP_RETRY (orange dims, hint button available)
  │       "Skip"      → defer to next sign
  ├─ v2: evaluateRep() returns 'target-met'
  │       → REP_PASS (green box, positive feedback, advance)
  ├─ v2: evaluateRep() returns 'low-confidence' or 'no-hands'
  │       → REP_RETRY (subtle prompt: "Try once more")
  └─ user invokes back-step
       → previous drill's last rep
```

### Bounding box semantics

The CV module exposes two calls (see [`ml-handoff.md`](./ml-handoff.md) for canonical contract):

- `processFrame(frame)` runs continuously while recording — returns the **live** state (gray or orange)
- `evaluateRep(drillType, target)` runs once at rep end — returns the **verdict** state (target-met / low-confidence / no-hands)

| Color | Meaning | v1 source (no CV) | v2 source (CV deployed) |
|---|---|---|---|
| **Gray** | No hands detected in frame | Mock dev panel button (`Set Gray`); no real detection | `processFrame()` returns `'no-hands'`, OR `evaluateRep()` returns `'no-hands'` |
| **Orange** | Hands detected; recording in progress | Mock dev panel button (`Set Orange`); no real detection | `processFrame()` returns `'hands-detected'` |
| **Green** | Rep target met | Mock dev panel button (`Set Green`) — informational only. **Mastery state is driven by the SELF_REPORT step**, not the box color. | `evaluateRep()` returns `'target-met'` (confidence ≥ 0.85, oodScore ≤ 0.30) |

**Important v1 behavior**: green box is **purely visual**. The dev panel sets it to demonstrate the success UI path. **Mastery state is updated by the user's self-report ("I got it" / "Not quite" / "Skip")**, NOT by the box turning green. This keeps the v1 mock clean and matches the [`ml-handoff.md`](./ml-handoff.md) contract: the CV module's `evaluateRep()` must never falsely return `target-met` for an unverified attempt, so v1's mock must not pretend it did.

v2 cutover removes the dev panel and lets `processFrame()` + `evaluateRep()` drive the box color and the rep outcome directly.

### Always-on recording

Per the user's UX spec:
- Once camera permission granted, the camera stream is **always active** in the Practice Screen until the user toggles it off via the bottom toolbar
- Recording (i.e., capturing frames for evaluation) is separate from the live preview. Recording auto-starts when a rep begins; the live preview is always visible
- Privacy framing: "Your camera is on. Frames stay on your device. Toggle off any time."
- The toolbar's recording-toggle button stops the camera stream entirely (not just paused frame capture); re-enable requires no new permission prompt

### Bottom toolbar buttons

| Button | Behavior | Keyboard |
|---|---|---|
| ● REC on/off | Toggles the camera stream | `M` (mute camera) |
| ← Back step | Returns to the previous Drill within the current Sign (Movement → Handshape, Sign → Movement) | `B` |
| ⟲ Back to lesson start | Returns to the first Sign of this Lesson; preserves mastery progress already earned | `Shift+B` |
| ? Help | Opens slide-in help panel with hints for the current sign | `H` |
| ⏸ Pause | Pauses everything; opens a modal with "Resume / Exit lesson" | `Space` |

Top-right `[exit]` returns to Lesson Catalog without losing progress (auto-saves after every rep).

### Positive feedback patterns (college-appropriate)

Keep this restrained. College students don't need confetti.

| Event | Visual | Audio (optional, off by default) | Microcopy |
|---|---|---|---|
| Rep pass | Green box pulse, 200ms fade | Soft single tone (440 Hz, 150ms, gentle attack) | none on first; "Nice." on rep 3 |
| Drill complete | Box flash to green, drill indicator dot fills | Two-tone confirmation | "Handshape locked in." |
| Sign complete | Subtle scale-in checkmark next to sign label | None | "THANK YOU — done." |
| Lesson complete | Page-level transition to Lesson Complete | None | Handled by Lesson Complete page |

Avoid: animated mascots, "STREAK!" callouts, bouncing springs, video-game-style "+100 XP" floats, "Duo is proud of you" voice. The audience is adult learners; the affordance should feel like Linear or Notion, not Duolingo.

### Sign decomposition for complex signs

Default: 3 drills per sign (Handshape, Movement, Sign). For complex signs (two-handed, sequential handshapes, location changes), insert additional drills:

```
Simple sign (e.g., THANK YOU):
  Handshape Drill → Movement Drill → Sign Drill

Two-handed sign (e.g., HELP):
  Dominant-Hand Handshape → Non-Dominant Handshape → Movement → Sign

Sign with sequential handshapes (e.g., NAME):
  Initial Handshape → Final Handshape → Movement → Sign

Sign with location change (e.g., MOTHER):
  Handshape → Location 1 → Location 2 → Movement → Sign
```

Lesson data should describe drills as a sequence per sign, not hardcode "always 3." Store as: `sign.drills: [{type: 'handshape', target: 'flat-B'}, {type: 'movement', target: 'forward-arc'}, {type: 'sign', target: 'THANK_YOU'}]`.

### Hint accessibility from Practice Screen

- Hint button (`?` in toolbar) opens a slide-in panel
- Panel shows: parameter-tagged hint, slowed reference video, optional side-by-side replay of user's last attempt
- Closing the panel returns to whatever state the user was in (no progress lost)
- After 2 successful reps on the current sign, hint button gets a subtle "faded" treatment (still available, less visually prominent) — implements faded feedback

---

## Microcopy bank

### Positive feedback (rep / drill / sign pass)
- "Nice."
- "Got it."
- "Locked in."
- "Handshape down — let's move on."
- "THANK YOU — done."
- "That's three. Onward."

### Retry / non-deficit framing
- "Try once more — focus on the handshape."
- "Almost. Watch the movement in the reference."
- "Compare your last attempt with the model."

### Permission / privacy
- "We need your camera to practice. Your video stays on your device."
- "Camera off. Toggle it back on whenever you're ready."

### Practice-mode toggles (Lesson Intro)
- "Hiding the reference tests recall."
- "Turning off camera switches to self-report."
- "Practice without the camera — sign offline and rate yourself."
- "Recall mode — sign from memory without the reference."
- "Quiz mode — prompt only, no camera, no reference."

### Lesson transitions
- "Lesson 1: Greetings — complete."
- "Next: Lesson 2: Numbers (0–9)."
- "Want to keep going, or take a break?"

### Encouragement (soft, infrequent)
- "Day 4 streak. You're building a habit."
- "8 signs from Learning to Familiar this week."

---

## Bounding box & detection — handoff to ML team

For v1, the front-end needs a stable interface from the ML team. Propose:

The CV module exposes three calls. Full schemas and field semantics are in [`ml-handoff.md`](./ml-handoff.md) (canonical source). Summary:

```typescript
// Called once at app start
await init({ modelBundleUrl, preferredBackend });

// Called continuously while recording (returns live box state)
processFrame(frame) → { state: 'no-hands' | 'hands-detected', framesBuffered }

// Called once at rep end (returns verdict)
await evaluateRep(drillType, target) → DetectionResult
//   DetectionResult.state = 'target-met' | 'low-confidence' | 'no-hands'
//   plus: confidence, oodScore?, parameter?, detail?, latencyMs, modelVersion
```

**v1 mock implementation** (`evaluate.mock.ts`):

- `init()` resolves immediately, returns `{ modelVersion: 'mock-0.1', backend: 'wasm', warmupLatencyMs: 0 }`
- `processFrame()` returns whatever the dev panel's `Set Gray` / `Set Orange` button last set; no real detection
- `evaluateRep()` always returns `{ state: 'low-confidence', confidence: 0, modelVersion: 'mock-0.1', ... }` — **the mock never returns `target-met`**. Mastery state is driven by the user's self-report row (`I got it / Not quite / Skip`), not by the mock's verdict.
- `Set Green` dev panel button is a *purely visual* override on the box color for testing the green-state UI path; it does not change `evaluateRep()`'s return value, does not advance mastery, and does not exist in production builds.

v2 cutover replaces `evaluate.mock.ts` with `evaluate.real.ts`, removes the dev panel, and lets the CV module drive both `processFrame()`-derived box color and `evaluateRep()`-derived mastery transitions.

---

## Development scaffolding (remove before launch)

Goal: **mock as little as possible**. The production UX shouldn't carry placeholders, but the parts that depend on infrastructure we don't have yet (CV inference, email-sending magic-link, OAuth callback) get a single, clearly-marked dev override per page.

All scaffolding is gated by:

```typescript
const DEV_MODE = import.meta.env.VITE_DEV_MODE === '1';
```

Dev mode is on in local + staging builds; **stripped from production bundles** via Vite's dead-code elimination. The dev panel never appears for end users.

### 1. Practice Screen — mock CV state buttons

A floating Dev Panel docked bottom-left of the Practice Screen. Visible only when `DEV_MODE === true`.

| Button | Effect | When to use |
|---|---|---|
| `Set Gray` | Forces bounding box to "no hands detected" state | Test the empty-frame UI without removing yourself from frame |
| `Set Orange` | Forces "hands detected, recording" state | Test mid-rep UI without holding pose |
| `Set Green` | Forces "target met" state, advances the rep | Skip the wait, test the success animation + advance logic |
| `Skip drill` | Auto-completes all 3 reps of the current drill | Move through long lessons fast |
| `Auto-pass rep` | Toggles "every rep auto-passes after 500ms" | Run an end-to-end lesson without performing signs |

These three colored buttons are the only mock UI on this page. When CV ships, **delete this entire panel** and the `DEV_MODE` branch that renders it. The `evaluate()` function it calls into stays — it just gets a real implementation.

### 2. Sign-up / Sign-in — dev bypass

Magic-link and OAuth flows require backend infrastructure (SMTP, OAuth callback URLs, etc.) that won't be configured during early development. Each auth screen carries a single dev bypass:

| Page | Dev override |
|---|---|
| Sign-up | `[Dev: Create local account]` — generates a random email + password, skips verification email, lands the user on Onboarding |
| Sign-in | **`[Dev: Skip login]`** — single-click sign-in as the seeded `dev@asl-pilot.local` user (see section 4 below). **This is the canonical dev login affordance in v1** (no real auth is wired up yet). |
| Email verification | `[Dev: Mark verified]` — flips the user's `email_verified_at` directly |
| Forgot password | `[Dev: Skip — go to reset]` — bypasses the email step and lands on the reset form directly |
| Camera Permission Priming | `[Dev: Skip camera setup]` — pretends permission was granted; subsequent pages use a recorded loop instead of live camera |

Every dev override is a `<button>` styled with a subtle yellow border + `data-dev-override` attribute. A Playwright e2e test asserts none of these elements exist when `DEV_MODE === false`.

### 3. Any blocker that depends on external infra — same pattern

Whenever you find yourself unable to test a flow because of an external dependency (email, OAuth provider, payment processor we don't have, etc.), add a labeled `[Dev: <action>]` button rather than mocking the dependency. The button performs the same downstream side effect that the real flow would have produced, then exits the dev branch. Removing the button at launch should remove all knowledge of the workaround from the codebase.

### 4. Dev account — seeded with rich history

A single seed-data user (`dev@asl-pilot.local`, password `dev-only-do-not-ship`) is inserted by `npm run db:seed` (or equivalent). Populate it with enough history that every UI surface that depends on user data looks lived-in.

**Profile**:
- Display name: "Dev User"
- `created_at`: 75 days before today (so the heatmap has data going back ~2.5 months)
- `email_verified_at`: same as created_at
- Soft streak: 4 days (active; broken once 30 days ago and recovered with a freeze)

**Practice history** (drives the dashboard heatmap):
- 75 days of data; aim for the GitHub-contributions look
- Distribution: ~40% of days have 0 reps (gaps); ~25% light (1–3 drills); ~25% moderate (4–8 drills); ~10% heavy (9+ drills)
- Streak windows: a 14-day streak ending 18 days ago, a current 4-day streak, two single-day blips
- Most recent 7 days are denser to show "Recent lessons" populated

**Mastery state**:
- 38 of the 75 signs touched (so progress bar shows 38 / 75 prominently)
- Of those: 12 Mastered, 9 Known, 8 Familiar, 5 Learning, 4 New (so the dashboard mastery distribution looks realistic)
- 4 lessons completed, 2 in progress, the rest not started
- Recent lessons strip: "Lesson 3: Numbers (in progress, 6/9)", "Lesson 1: Greetings (mastered)", "Lesson 2: Family (mastered)", "Lesson 4: Feelings (not started)"

**Hint requests** (drives the Help / How It Works empty-state-vs-populated branch):
- ~30 hint button presses across history; mostly during Learning state

**Notification state**:
- Daily reminder set to 7pm
- Weekly summary on
- One unread notification: "You moved 8 signs from Learning to Familiar this week."

The seed script lives at `scripts/seed-dev-user.ts` and is idempotent — re-running it resets the dev user's history without affecting any other accounts.

### 5. Demo mode (later)

Eventually we may want a "Demo" view for partners/investors that shows the populated dashboard without requiring sign-in. The dev account is the natural backing for that — wire `/demo` to auto-sign-in as the dev user with all dev overrides disabled. Out of scope for v1; mentioned here so the seed data anticipates it.

### 6. Removal checklist (before public launch)

1. Grep for `DEV_MODE` — should be zero matches outside `vite.config.ts`
2. Grep for `data-dev-override` — should be zero matches
3. Confirm seed script is not part of the production deploy pipeline
4. Confirm `dev@asl-pilot.local` cannot sign in via the public sign-in form (the dev sign-in button is the only path)
5. Run the Playwright `no-dev-affordances.spec.ts` test against a production build

---

## Tech stack — restated with rationale

| Layer | Choice | Why this, not the alternatives |
|---|---|---|
| **Framework** | React + TypeScript | Standard for component-rich SPAs; TS prevents the kind of refactoring drag this app will see during v1→v2. Considered: SvelteKit (smaller bundle but smaller ecosystem; React's Radix/shadcn maturity wins for an a11y-sensitive app). |
| **Build / dev** | Vite | Faster HMR than Webpack, near-zero config; deploys to any static host |
| **Routing** | React Router | Established, file-routes optional via TanStack Router if preferred |
| **State machine** | XState | Practice Screen's nested rep/drill/sign/lesson state is non-trivial; isolating it from React tree pays for itself in testability. Considered: hand-rolled reducers (gets messy past 3 nested states); Zustand (great for app state, weaker for state machines). |
| **Components** | shadcn/ui on Radix primitives + Tailwind | shadcn fastest-growing + highest-positivity in State of React 2024; copy-paste model means we own and customize. Radix provides WAI-ARIA-correct primitives (Dialog, Toast, Tooltip, Progress). Note (per UX fact-check): not "the default 2026 stack" — Mantine or MUI are equally defensible if existing team momentum dictates. |
| **Styling** | Tailwind | Pairs naturally with shadcn; design tokens via CSS variables for theming |
| **Typography** | Inter | Tall x-height, designed for on-screen UI, ships well at 16/18/24/32 |
| **Camera / video** | `getUserMedia()` direct; MediaRecorder for replay | No abstraction in v1; switch to a wrapper only when complexity demands |
| **ML inference (v2)** | ONNX Runtime Web + WebGPU | Per [`training-plan.md`](./training-plan.md); WebGPU gives 3–5× over WebGL on transformers (ONNX Runtime Web benchmarks). 30+ FPS realistic on a college laptop. v1 has no inference; this is the v2 swap-in. |
| **Auth (v1 local)** | **None — dev-bypass only.** Skip-login button signs in as the seeded `dev@asl-pilot.local` account. | Real auth providers were overkill while we're still pre-pilot. See [`local-setup.md`](./local-setup.md). |
| **Auth (post-pilot path)** | Better Auth OR Lucia v3 OR hand-rolled cookie sessions | Whichever path we pick, the migration changes only the backend's session layer — the frontend's `useUser()` shape doesn't change. |
| **Database** | **Postgres in local Docker** (`docker-compose.yml`) | Progress data is relational. Local Postgres in a container is identical to managed Postgres at the schema/query level — migration to managed hosting later is a connection-string change. |
| **ORM / DB client** | Drizzle ORM + node-postgres | Type-safe, lightweight, migration-friendly. Considered: Prisma (heavier, generated client), Kysely (query builder only). |
| **Backend** | Hono on Node, runs on host (no container in v1) | Small, fast, runs identically on Node/Bun/edge. Considered: Express (boring/fine), Fastify (overkill), tRPC (tighter coupling). |
| **Data fetching** | TanStack Query | Cache, retry, optimistic updates — saves a lot of manual coordination |
| **Analytics (v1 local)** | **None.** | No analytics until we have real users. Plausible or self-hosted PostHog when we ship a pilot. |
| **Error tracking (v1 local)** | **Console + browser devtools.** | Sentry when we ship a pilot; configure to never capture camera frames. |
| **Hosting (v1)** | **Local-only.** Backend + frontend on host, Postgres in Docker. | See `local-setup.md`. |
| **Hosting (post-pilot)** | Vercel / Cloudflare Pages for frontend; managed Postgres (Supabase, Neon, RDS) for the DB | Frontend is static; backend is a single Hono process or serverless function. Switching from local to cloud is mostly env-var changes. |
| **Reference videos (v1)** | **Served from `/public/videos/` in the Vite dev server.** | Local files, no CDN. Captions as `<slug>.vtt` alongside. |
| **Reference videos (post-pilot)** | Cloudflare R2 + Cloudflare Stream OR Bunny.net | R2 is cheap egress; Stream handles HLS variants. Same `<video>` element URL structure as local. |
| **Testing** | Vitest (unit) + Playwright (e2e) + axe-core (accessibility) | Vitest pairs with Vite; Playwright handles camera-mock e2e; axe-core enforces WCAG 2.2 AA in CI |
| **i18n** | react-i18next | English in v1; structured for future Spanish/other (campus demand-dependent) |
| **Forms** | React Hook Form + Zod | Validation at boundaries (per CLAUDE.md rule); Zod schemas reusable for API contracts |

### Notable non-choices

- **No CSS-in-JS** (styled-components, Emotion) — Tailwind handles styling; CSS-in-JS adds runtime cost and complicates SSR if we ever go server-rendered
- **No global state library** beyond TanStack Query for server state and XState for the practice machine; UI state is local
- **No mobile native apps** — browser-only per Req 3; design must not depend on native APIs
- **No video uploads anywhere in v1** — per Req 13 privacy; everything stays local. The CV inference (v2) runs locally too. Even bug reports should not capture frames.

---

## Accessibility implementation checklist (per principles.md)

- WCAG 2.2 AA target across all pages; CI gate via axe-core
- Honor `prefers-reduced-motion` for all transitions (replace animations with instant state changes)
- All text ≥ 4.5:1 contrast; large text ≥ 3:1; UI components ≥ 3:1
- Color-paired with icon for every success/fail state
- Full keyboard nav on non-camera UI (camera UI keyboard shortcuts documented in toolbar tooltips)
- Visible focus rings on every interactive element
- Captions on every reference video (deaf/HoH learners are part of the audience)
- Semantic HTML for screen-reader compatibility on enrollment/results/review surfaces
- iOS safe-area insets respected (44pt top / 34pt bottom on Face ID iPhones)
- No flash >3 Hz anywhere (WCAG 2.3.1 Level A — mandatory)
- Pause/stop control on any auto-playing animation >5s (WCAG 2.2.2 Level A — mandatory)

---

## Open questions before build

1. **Sign-list freeze**: Need the final 75–100 signs locked before catalog/lesson-data work begins. Coordinate with Deaf consultant per principles.md.
2. **Reference video pipeline**: who films, who edits, where they're stored. Cloudflare R2 + Stream is the bet; needs Deaf signer recruitment first.
3. **Lesson granularity**: ~8 signs per lesson means ~10 lessons for the 75-sign target. Confirm with pedagogy.
4. **Endowed-progress pre-mastered signs**: which two signs make it through tutorial as "already mastered"? Suggest HELLO + THANK YOU.
5. **Self-report vs auto-advance in v1**: when a rep window completes, does the system auto-mark "pass" or require user tap? Recommendation: explicit tap (drives engagement + reduces ambiguity). A/B-testable.
6. **Lesson sequencing**: free-order browse or sequential gating? Recommendation: free-order, since college students manage their own schedules; gate only Lesson 1 (tutorial) before others.
7. **Account deletion timeline**: 7-day soft delete vs immediate hard delete. Recommend 7-day soft for accidental clicks.

---

## Implementation notes — post-scaffold changes

This section captures the deltas between the as-designed spec above and the as-built app, accumulated since the scaffold milestone shipped. See `/docs/handoffs/HANDOFF_FRONTEND.md` for the full narrative.

### Practice screen — additions/changes

- **State-machine fast-forward sends 3 events**, not 2 (PROMPT_SHOWN → COUNTDOWN → RECORDING → SELF_REPORT). The 2-event version was getting stuck in RECORDING and breaking every Continue click.
- **"Not quite" button removed.** The action row is now just **Continue / Skip**. The `FAIL` machine event is still defined for future CV-driven failure detection. Test id `self-report-got-it` preserved for compat; button label is "Continue."
- **Auto-advance on green**: when the bounding box turns green via the dev panel (or, in v2, via CV) AND the machine is in `SELF_REPORT`, the system dispatches `PASS` after a 350ms flash. The action zone shows a helper line: *"Click Continue when you're ready, or we'll advance automatically when the camera detects success [green dot]."*
- **Back navigation**: added `BACK_DRILL` and `BACK_SIGN` events on the machine root. Toolbar buttons (`practice-back-drill`, `practice-back-sign`) + inline `Back drill` next to the action zone. Auto-disabled at the relevant index boundaries.
- **Camera toggle mid-lesson**: header toolbar button writes `?camera=0/1` to the URL.
- **Pause stops both videos**: `Practice.tsx` threads a `paused` boolean to `CameraPanel` (disables tracks via `track.enabled = false` so resume doesn't re-prompt permission) and `ReferenceVideo` (calls `video.pause()`).
- **Resume cursor persistence**: practice state persisted to `localStorage` under `asl-pilot.practice-resume.<slug>` as `{signIndex, drillIndex, repIndex, updatedAt}`. Read on Practice mount if <7 days old, written on every cursor change, cleared on `LESSON_COMPLETE`. The XState `context` initializer takes `initialSignIndex/initialDrillIndex/initialRepIndex` clamped against the actual lesson shape.
- **Sign-complete toast** (not modal): when a sign advances and none of its reps were skipped, a non-blocking toast fires in `fixed bottom-4 right-4` with cyan border + sparkles icon + "Sign saved to memory" + sign gloss. Auto-dismisses after 4s. `data-testid="sign-complete-toast"`. Practice continues underneath — no scrim, no focus trap.
- **Dev panel moved in-flow** (was `fixed bottom-4 left-4`, was overlapping the Continue button).
- **`RepCounter` redesigned**: bordered inset well + small `Rep` label + 2xl indigo digit + `of 3` muted (instead of tiny mono "Rep 1 of 3").
- **`DrillIndicator` redesigned**: filled connector line + ChevronRight glyph between dots; active dot has 18%-alpha indigo halo; past dots get a check glyph at 55% indigo; future dots have a bordered well rather than fading. Wrapped in `bg-bg-elevated/40` panel with inner shadow.
- **Reference video**: all signs share `/videos/nyan.mp4` (placeholder). Plays in three segments per drill (handshape 0–1/3, movement 1/3–2/3, sign full clip). Auto-loop toggle (default on) loops the segment; off pauses at segment end. Replay button restarts the current segment. Slow-mo toggle. Three-pill timeline overlay shows the active segment in indigo.
- **Video panel aspect**: changed from `aspect-video` (16:9) to `aspect-[4/3]` per user preference (more square, less letterboxed).

### Dashboard — additions/changes

- **`staleTime: 0` + `refetchOnMount: 'always'`** on the dashboard query so back-nav reflects fresh progress.
- **GitHub-style heatmap**:
  - 7-row × N-week layout (Sun-Sat rows, oldest column left, today rightmost).
  - Day-of-week labels (Mon/Wed/Fri sparse) on the left edge.
  - Month labels above the columns where each month starts.
  - **5-tier intensity scale** (was 4): 0 = no practice, 1 = 1–9 reps, 2 = 10–19, 3 = 20–29, **4 = 30+ reps**.
  - GitHub's calibrated dark palette: `#0e4429 / #006d32 / #26a641 / #39d353` for tiers 1–4.
  - Today's cell: cyan-bright ring + soft cyan glow shadow. Hover ring: cyan.
  - Click a cell → Dialog with date, rep count + outcome breakdown (pass/fail/skip), intensity label, lessons touched that day with click-through.
  - First-paint stagger animation, respects `prefers-reduced-motion`.
  - Removed: streak-run inset glow (was confusing user).
- **Activity panel framing**: bordered "data well" card around the heatmap with a cyan top-edge gradient hairline + soft cyan corner blur (matches SuperBuilders hero hologram palette). Header strip with "Activity / Last 75 days" eyebrow + legend. Inset shadow on the heatmap surface so it reads as recessed.
- **Recent lessons** got prev/next slide arrows + edge-fade gradients. Auto-hide via `ResizeObserver` when at scroll ends.
- **"Continue last lesson"** Link passes `state={{ from: '/dashboard' }}`. The Lesson Intro page reads `location.state.from` and shows "Back to dashboard" instead of "Back to catalog" when arrived from the dashboard.

### Heatmap day-detail (new)

New `GET /api/progress/day/:date` endpoint returns:
```json
{
  "date": "2026-05-21",
  "drillCount": 11,
  "intensity": 2,
  "outcomes": { "pass": 5, "fail": 4, "skip": 2 },
  "lessons": [
    { "slug": "lesson-1", "title": "Lesson 1: Greetings", "category": "Greetings", "reps": 2, "signs": 2 },
    ...
  ]
}
```

The day-detail Dialog renders these lessons as a list with click-through to the lesson.

### Design tokens — additions

- **Cyan secondary accent**: `--accent-cyan: #06b6d4`, `--accent-cyan-bright: #22d3ee`. Exposed as Tailwind `accent.cyan` / `accent.cyan-bright`. Used on: heatmap hover ring + today cell, activity panel hairline + corner glow, sign-complete toast, Landing hero text-shadow.
- **`--bg-raised`** (`#2c2c2c`): level-2 surface (hover states on cards). Exposed as `bg-raised`.
- **`--border-strong`** (`#444`) and **`--border-stronger`** (`#555`): hover/overlay borders.
- **`--accent-ring`** (indigo-400 `#818cf8`): focus rings on dark — passes contrast.
- **Bungee** display font added via `@fontsource/bungee`. Exposed as `font-display`. Used on Landing hero, AppShell logo, Dashboard "Welcome back" heading, sign-complete toast. **NOT for body text.**
- **Body radial gradient**: dual radial from indigo-tinted warm top-left to deep dark bottom-right, `background-attachment: fixed`. Matches the SuperBuilders About-page subtle gradient.

### Component polish (per `docs/research/dark-ui-depth.md`)

- **shadcn Button rewritten**: primary gets top-edge sheen (`inset 0 1px 0 rgba(255,255,255,0.08)`) + colored hover shadow (`0 2px 8px -2px hsl(var(--accent)/0.4)`) + 1px press. Ghost has no translate, no shadow. All transitions enumerated (no `transition-all`). `focus-visible:outline-2 outline-accent-ring outline-offset-2`.
- **Cards** (`RecentLessons`): clickable cards lift `-translate-y-px` on hover + brighten to `bg-bg-raised`, no drop shadow. Inert tiles don't animate (research: hover on inert surfaces is the #1 amateur-feel signal).
- **`Progress` primitive**: track is now an inset well (`bg-bg-deepest border shadow-[inset_0_1px_2px_rgba(0,0,0,0.4)]`); fill is `bg-gradient-to-r from-accent to-accent-hover`.
- **`BoundingBox`**: removed the neon glow on green/orange states (research called it "instant cyberpunk-amateur"). Now a 2-color ring at 30% alpha on detection + inset well treatment.
- **AppShell header**: sticky top-0, subtle backdrop blur, two-row inset shadow (no hard 1px divider).

### Tech-stack revisions

- **shadcn 4.x with Base UI** (not Radix). The published `shadcn@latest` CLI shipped a v4 rewrite that uses `@base-ui/react` (Radix's modern successor by the Material team). Functionally equivalent; the swap is documented in `docs/handoffs/HANDOFF_FRONTEND.md`'s Gotchas section. **Don't run `npx shadcn@latest add ...` after init — it overwrites `globals.css`.**
- **Atkinson Hyperlegible Mono doesn't exist as a published font.** We use Atkinson Hyperlegible (proportional) for sans + JetBrains Mono for mono + Bungee for display. The brand-alignment research mistakenly identified the SB site's mono font as a non-existent variant.

### Tests added since scaffold

- `tests/e2e/lesson-intro.return-nav.spec.ts` — back-to-catalog from-dashboard returns to dashboard; direct visit returns to catalog
- `tests/e2e/practice.self-report-single-click.spec.ts` — single click, 9-click walk, **Set-Green-auto-advance** (replaces the old Not Quite test)

Total: 12/12 e2e, 1/1 a11y, 22/22 unit, all green.

### Files to ignore as stale wording

The §"Practice Screen — the deep dive" wireframe above shows "I got it" inside the dev panel callout — current implementation reads "Continue" with a check icon. Functionally equivalent; the testid stayed.
