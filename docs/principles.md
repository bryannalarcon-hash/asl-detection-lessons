# ASL Pilot — Pedagogy & App Design Principles

Synthesis of primary research, independent fact-check, and tertiary deep-dives. The CV system is treated as a black box with the signature `evaluate(videoFrames) → { pass, confidence, errorParameter? }`. Where the primary research disagreed with the fact-check, the resolution is cited.

---

## North-star principles

1. **You are building a vocabulary practice tool, not "ASL learning."** Scope honestly in copy and onboarding (Desai et al. 2024 — five Deaf authors; NAD vocab-app category). This protects you from the "ASL translator" critique that has burned every prior hearing-built attempt.
2. **The dominant learning mechanism for hearing adults is self-production (motor encoding), not external correction** (Hocking et al. 2024, peer-reviewed). A Sign Mirror captures the most-evidenced learning mechanism for free. Don't sweat the absence of CV grading in v1.
3. **Stage the CV grader.** Ship v1 as Sign Mirror + self-report. Define hard gate criteria for v2 (numbers below). This decouples site-build from the ML team's accuracy curve.
4. **Match feedback grain to the system's truth.** Surface only what you can verify. If you can only check hands, *say* "this app checks your hands" — don't pretend.
5. **Engagement mechanics: mastery bars primary, soft streak secondary.** The streak debate resolved decisively against hard streaks for college learners on a bounded curriculum.
6. **Drill handshape first, then movement.** The tertiary parameter brief corrected both the primary brief AND the fact-check on this — both perception studies actually agree (movement hardest to perceive), and production studies show handshape errors break lexical recognition fastest. Handshape first is the load-bearing pedagogical decision.
7. **Don't decide cultural framing without a Deaf consultant on call.** The most damaging mistakes (translator framing, ungated NMM grading, uncredited reference videos) cost more than the review.

---

## The practice loop (v1: Sign Mirror)

### Layout

Desktop:
```
┌──────────────────────────────────────────────────────────────┐
│ [████████░░░░░░░░] 3 of 10                          [Settings]│
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ Sign: THANK YOU                                              │
│ ─────────────────                                            │
│                              ┌─────────────────────┐         │
│ ┌────────────────────┐       │  Reference          │         │
│ │ YOUR CAMERA        │       │  (Deaf signer,      │         │
│ │ (mirrored)         │       │   muted autoplay,   │         │
│ │ 16:9               │       │   looping)          │         │
│ │ [framing guide]    │       │                     │         │
│ │      [● REC]       │       │  Slow ▸             │         │
│ └────────────────────┘       └─────────────────────┘         │
│                                                              │
│ ╭─── Action Zone (state-dependent) ─────────────────────╮   │
│ │  [● Start signing]    [I got it ✓]    [Show me again] │   │
│ ╰────────────────────────────────────────────────────────╯   │
└──────────────────────────────────────────────────────────────┘
```

Mobile portrait: camera full-width 9:16, reference video collapsed to bottom-right thumbnail (tap to expand), action zone in bottom safe-area. The UX fact-check explicitly noted side-by-side doesn't survive portrait — mobile sign-app convention is stacked/toggle (Lingvano, Ace ASL).

### State machine

```
IDLE (camera off, value pitch shown)
  └─ "Turn on camera" → PERMISSION_PROMPT
PERMISSION_PROMPT
  ├─ allow → READY
  └─ deny → PERMISSION_RECOVERY (browser-specific re-enable)
READY → first prompt:
PROMPT_SHOWN (reference video plays, camera live, mirrored)
  ├─ "Start signing"     → COUNTDOWN (3-2-1, ~1.5s)
  └─ keyboard SPACE      → COUNTDOWN
COUNTDOWN → RECORDING (3-5s, REC ring + pulsing dot)
RECORDING
  ├─ timer / "Done"      → SELF_REPORT
  └─ cancel              → PROMPT_SHOWN
SELF_REPORT (replay user's clip + reference side-by-side)
  ├─ "I got it"          → MASTERY_TICK → next PROMPT_SHOWN
  ├─ "Not quite"         → HINT_OPTIONAL → PROMPT_SHOWN (retry)
  └─ "Skip for now"      → DEFER → next PROMPT_SHOWN
HINT_OPTIONAL (when user requests; never auto-shown)
  └─ shows: one-line hint + parameter icon + slowed reference
SESSION_END (after N signs) → summary
```

Why this works:
- **Self-report instead of CV in v1** — the user judges their own attempt against the reference. This is exactly what Lingvano's Sign Mirror does, and it parallels the empirically-supported "Self-After" feedback request pattern (Carter et al. 2014) without requiring the contested "self-controlled feedback effect" to be real (McKay et al. 2022 found that effect underpowered).
- **Side-by-side replay** of user-clip + reference activates Mayer's signaling principle (the legitimate citation, not the Loom blog the UX brief mis-cited).
- **Hint is opt-in, never punitive.** No "WRONG" state ever appears in v1.

### Permission flow

Two screens, NN/g formula:
1. Explainer card: *"We need your camera so you can practice signs against a Deaf instructor's example. Video stays on your device — nothing is uploaded."* Then "Turn on camera" button.
2. Native `getUserMedia()` prompt fires only after click. (Chrome telemetry: post-interaction prompts get ~30% allow vs ~12% cold — verified Chrome-wide stat, not camera-specific, but directionally sound.)
3. On denial: recovery card with browser-specific re-enable instructions; do not re-prompt programmatically (web.dev).

---

## Session structure

| Setting | v1 default | Source |
|---|---|---|
| Session length | 5–8 minutes | Drops/Duolingo industry default; not derived optimum — treat as A/B-testable |
| Items per session | **6–10 signs**: 2–3 new + 4–7 review | SRS literature (Wozniak, Cepeda); NOT Miller 7±2 (that was a category error — fact-check refuted) |
| Vocabulary sequencing | **By frequency, not topic** | Lifeprint's verified pattern; explicit Vicars quote |
| Mastery model | 5-stage: New → Learning → Familiar → Known → Mastered | Streaks tertiary brief; spaced-repetition literature |
| Spacing intervals | 1d → 3d → 7d → 14d, expanding | Webb/Uchihara/Yanagisawa 2023 (g=1.71 spaced vs 0.58 massed, *corrected from primary brief's wrong numbers*) |
| Practice scheduling | Brief blocked exposure (3–5 reps) for first encoding, then interleave | Czyż et al. 2024 — adult SMD 0.63 for interleaving |
| Daily target | 10–15 min split into 1–3 mini-sessions | Industry convention, not derived |

**Note on the 75–100 sign scope** (Req 2): this is ~25–33% of Lifeprint's full ASL 1 (~300 signs). Defensible MVP scope.

---

## Hint system

### Priority order (when multiple parameters could be flagged)

This is the most consequential output of the research — both the primary brief and the SLA fact-check got the parameter ranking wrong, and the tertiary brief corrected them.

| Priority | Parameter | Why first |
|---|---|---|
| 1 | **Handshape** | Wrong handshape collapses lexical recognition (Chen Pichler 2010: marked handshapes drop to ~36% accuracy on low-sonority); also the easiest to correct from a still frame; L1 gesture transfer is real (hearing learners default to co-speech-gesture handshapes) |
| 2 | **Movement** (articulator + path) | Hardest to perceive in both ASL perception studies (Bochner et al., Williams & Newman); proximalization is ~20% in learners vs 3% in native signers (Mirus/Rathmann); name it explicitly: "use your wrist, not your elbow" |
| 3 | **Palm orientation** | Silent error — beginners don't self-notice; creates minimal-pair confusions (TUESDAY/BATHROOM) |
| 4 | **Location** | Most accurate parameter in beginners (Ortega & Morgan 2015); surface only when others clean |
| 5 | **Timing / hold** | Beginners aren't timing-sensitive; flag only when sign is otherwise correct |
| 6 | **Camera framing** | Precondition fallback when CV confidence is low |

**NMMs (facial grammar) are deliberately not graded in v1.** Show them in the reference video; don't flag them. ASL textbook sequencing supports this (Master ASL defers NMM to Lesson 8; TRUE+WAY introduces but doesn't enforce in Unit 1; Vicars: NMM/NMS deep work is post-beginner).

### Hint phrasing (non-deficit pattern)

| Use | Avoid |
|---|---|
| "Try again — focus on the handshape." | "Wrong." / "Incorrect." / "You failed." |
| "Close — try a flat-B handshape, not a 5." | "Bad sign." / "That's not ASL." |
| "Sign in front of your chest, not your face." | "Sign harder." / "Sign clearer." (NAD: pace, not effort) |
| "Use your wrist for the movement, not your elbow." | Multi-parameter dumps in one hint |
| "Compare your clip to the model." | Generic "look again" with no parameter |

Single parameter per hint. Always offer a parallel-play of user's clip + reference. (Source: Creative ASL Teaching pattern + Mayer signaling principle. Flag: Creative ASL Teaching's author Deaf status unverified — get Deaf reviewer to vet final copy.)

### Hint frequency / faded feedback

- **First 1–2 attempts on a new sign**: hint shown on request, side-by-side replay always available
- **After the sign has passed twice**: hint hidden by default, available behind "Show me what went wrong" button
- This implements faded feedback (Aoyagi 2019 / Winstein & Schmidt 1990 — note fact-check corrected the cited Winstein/Schmidt URL to Aoyagi 2019; both findings are real but distinct)

---

## Progress mechanic

**Primary: mastery bars.** Per sign, 5 stages (New / Learning / Familiar / Known / Mastered). Course-level: "47 / 100 mastered" — leverages goal-gradient effect on a bounded curriculum (Kivetz et al. 2006).

**Secondary: soft daily-practice streak with 2 auto-applied freezes per week** (no purchase, no decision cost — observational data shows freezes raise avg streak 11.6 → 17.2 days).

**Anti-patterns** (rejected by streak tertiary brief):
- No public leaderboards (Hanus & Fox 2015 — demotivation)
- No "you lost a 47-day streak" full-screen loss state
- No gating mastery behind streak status — keep them orthogonal
- No "Duo is disappointed in you" anthropomorphic shame

**Endowed progress on first session**: pre-fill 1–2 trivial signs (HELLO, THANK YOU) as Mastered during the tutorial so learners enter session 2 already non-zero (Nunes & Drèze 2006). Caveat from fact-check: endowed progress affects *completion*, not *retention* — use it to drive return visits.

**Weekly summary** focuses on mastery gains, not streak status. *"You moved 8 signs from Learning to Familiar this week."*

---

## Cultural framing & accessibility

### What to say and not say

| Use | Avoid |
|---|---|
| "ASL vocabulary practice" | "ASL translator" / "AI ASL" |
| "Sign for this concept" | "Translate this word" |
| "Deaf instructor" (capital D for cultural identity, lowercase d for audiological, per Desai et al.) | Generic "ASL teacher" without naming |
| "This app checks your hands. For facial grammar, watch the model." | Pretending you grade what you don't |
| "Handshape" (universal across all 5 verified ASL textbooks) | "Configuration" (linguistics jargon) |
| "Facial expression (non-manual markers / NMMs)" — lay term first, technical parenthetical | "Facial grammar" alone in beginner UI |

### Reference videos

- **Deaf signers**, paid, individually credited by name
- **Multiple signers** across age, race, regional variation (single-signer reference videos misrepresent ASL)
- **Include NMMs** in every reference — show what the full sign is, even if you can't grade it. Otherwise you teach a hands-only ASL, which Desai et al. explicitly critique.
- Compensation rate: don't anchor to interpreter rates; let the Deaf consultant set it

### Accessibility minimum bar

- **WCAG 2.2 AA target** (forward-looking; ISO/IEC 40500:2025). 2.1 AA is the legal floor for public colleges per DOJ Title II April 2024 rule (deadlines extended: April 2027 / April 2028).
- Honor `prefers-reduced-motion` (best practice; satisfies WCAG 2.3.3 AAA — this is *aspirational*, not the mandatory bar. The mandatory motion criteria are 2.2.2 Pause/Stop/Hide Level A and 2.3.1 Three Flashes Level A. The UX brief mis-framed this; corrected here.)
- 4.5:1 text contrast, 3:1 large text / UI components
- Pair color signals with icons (colorblind-safe success/fail)
- Captions on reference video (deaf/HoH instructors and learners are part of the audience)
- Camera-flip control, mirror toggle (some users find mirror confusing — UX fact-check flagged this)
- Full keyboard nav on non-camera UI (SPACE = start/stop, N = next, R = retry)
- iOS safe-area insets: 44pt top / 34pt bottom on Face ID iPhones

### FERPA framing

Brief said "video → FERPA record once tied to identifiable student." Fact-check corrected: FERPA needs **both** "directly related to a student" **AND** "maintained by an educational agency or institution." A learner's practice video stored only on their device is *not* automatically a FERPA record. UI should still say: *"Video stays on your device. Nothing is uploaded by default."*

---

## v2 trigger: when to ship CV grading

From the CV SOTA tertiary brief + verification-swarm follow-up — these are the gate criteria, not aspirations:

1. **Top-1 ≥ 92% AND top-3 ≥ 98%** on a held-out test set of **≥ 5 actual ASL-1 learners** (not the Kaggle/PopSign Deaf-signer pool) across the deployed 75–100 sign vocabulary, measured **per drill type** (handshape, movement, sign).
2. **OOD rejection rate ≥ 90%** — when the learner signs something else or nothing, `evaluateRep()` must return `'low-confidence'` or `'no-hands'`, never `'target-met'`. This is the PopSignAI sloppy-sign-rewarded failure mode and we explicitly guard against it.
3. **Latency budget** — `evaluateRep()` p95 ≤ 200ms AND `processFrame()` p95 ≤ 33ms on the lowest-spec target laptop (integrated GPU, WebGPU enabled).
4. **2-week A/B pilot**: CV-grader arm shows no worse confidence/usage retention than mirror arm, AND equal-or-better vocab quiz performance at week 2.

If any of those fails → keep mirror + self-report. The training-plan.md gate criteria for Stage 2 (≥ 0.80 top-1, ≥ 0.90 top-3) are **looser** than the v2 deploy criteria — Stage 2 passing the ML gate does not automatically mean it should be deployed to learners.

See [`ml-handoff.md`](./ml-handoff.md) for the full interface contract and how these gates are measured.

---

## Open questions where you should pull in a Deaf consultant *before* pilot

1. Final 75–100 sign list — regional variation, signs that carry cultural weight
2. Exact UI copy for "Try again — focus on the handshape" and the rest of the microcopy bank
3. Whether to label NMMs as "not graded" in reference videos, or just include them silently
4. Whether to use "NMM" abbreviation in beginner UI vs sticking with "facial expression"
5. Reference-video signer recruitment, compensation rate, credit format
6. Marketing language for the app's scope (vocab practice vs ASL learning)
7. Whether to publish CV accuracy metrics in v2 (overclaiming is the most-criticized pattern in the literature)

Glasser et al. ICCV 2025: **80% of surveyed Deaf community members rated Deaf involvement as a strong motivator; 60% rated compensation similarly.** Token consultation reads as the failure mode you're trying to avoid; structural involvement is the goal.

---

## Phased roadmap

- **Phase 0 (now → 4 weeks): build the site against a stub.** Don't wait for the ML team. The CV is a black-box function with a defined interface. Build everything around the interface.
- **Phase 1 (v1 launch): Sign Mirror + self-report.** Mastery bars, soft streak, Deaf-signer reference videos, accessibility floor, no CV grading. Hint button is opt-in and shows side-by-side replay + parameter-tagged advice. Self-report ("I got it" / "Not quite" / "Skip") drives mastery state.
- **Phase 2 (v2 trigger): swap in CV grading** behind the same interface when the three gate criteria above are met. The action zone changes from "I got it / Not quite" to an automatic pass/fail from CV + the same hint surface.
- **Phase 3 (out of pilot scope but design for it):** NMM-aware grading (face-pose model added), teacher dashboards (deferred — Req 11 explicitly excludes), classroom rostering.

---

## Confidence calibration

| Claim | Confidence |
|---|---|
| Hands-only CV is acceptable for a *vocab practice* tool with proper framing | High — multiple Deaf-led primary sources |
| Mirror v1 captures the dominant learning mechanism | High — Hocking et al. 2024, peer-reviewed |
| Hint priority: handshape → movement → palm orientation → location → timing → framing | High — converging evidence across Chen Pichler, Bochner, Ortega & Morgan, Ebling, Lifeprint, Vicars |
| Don't grade NMMs in v1 | High — textbook sequencing convergence; flag the load-bearing teacher blog source |
| Mastery bars > hard streaks; soft streak as secondary | High — SDT + spaced-repetition base evidence; Duolingo's own streak data is observational |
| 6–10 items per session, 5–8 min default | Medium — industry default, not derived optimum; A/B-test |
| WCAG 2.2 AA forward-looking, 2.1 AA legal floor | High — DOJ Title II April 2024 rule |
| shadcn/ui + Radix + Tailwind | Medium — defensible 2025-2026 choice but not "the default"; MUI/Mantine equally defensible |
| Stage CV grader behind hard gate criteria | High — Hocking et al. + ASL Educators CHI 2026 (12 instructors, "AI as teacher's assistant, not evaluator") |
