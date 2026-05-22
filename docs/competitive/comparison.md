# Competitive Comparison — 8 Learning Apps vs Our ASL Pilot

Cross-analysis of the 8 competitive teardowns in this directory ([Lingvano](./lingvano.md), [Duolingo](./duolingo.md), [Drops](./drops.md), [Anki](./anki.md), [PopSignAI](./popsignai.md), [ASL Bloom](./asl-bloom.md), [Brilliant](./brilliant.md), [Khan Academy](./khan-academy.md)) against our `../ux-spec.md` and `../principles.md`. Apps are grouped by what they're optimizing for so we don't conflate engagement design with learning effectiveness.

---

## Executive summary

Our spec is positioned in an unoccupied corner of the map: **parameter-level CV-graded production practice for ASL beginners, with a Deaf-led pedagogical posture, on the web**. The two largest ASL learning apps (Lingvano at 2.5M users; ASL Bloom at ~1,300+ signs across 10 apps from SignLab AS) are both receptive-only with no production grading. The one ASL app that does CV-graded production (PopSignAI) is a native Android-only research preview restricted to bubble-shooter gameplay for parents of Deaf children — a different audience and platform. The mastery model we adopted is closer to Khan Academy than Duolingo. The pretesting / productive-failure pattern from Brilliant maps cleanly onto our drill loop and is worth incorporating. Anki's interval-preview pattern is the strongest small UX detail we can borrow. Duolingo and Drops are studied here mostly to document anti-patterns, not as teaching exemplars — peer-reviewed evidence on their actual acquisition gains is modest at best.

---

## App categorization

| App | Optimizes for | Audience | Production grading? | Browser? |
|---|---|---|---|---|
| **Lingvano** | Engagement + content depth | General ASL/BSL learners | No (passive Sign Mirror) | Web + iOS + Android |
| **Duolingo** | Engagement (streaks) | Casual language learners | No | Web + native |
| **Drops** | Habit (5-min sessions) | Casual vocab learners | No | Web + native |
| **Anki** | Long-term retention (SRS) | Power users, students | No (self-graded) | Web + native (desktop-first) |
| **PopSignAI** | Sign production via CV | Parents of Deaf children | Yes (constrained 5-class) | No (native Android only) |
| **ASL Bloom** | Content breadth | General ASL learners | No | Web + native |
| **Brilliant** | Concept mastery | Adult STEM learners | N/A (interactive problems) | Web + native |
| **Khan Academy** | Mastery learning | K-12 + free learners | N/A (problems, not motor) | Web + native |
| **Our app** | Production practice + learning outcomes | College ASL 1 students | Staged: v1 self-report, v2 CV | Web-only |

We're the **only browser-first** product targeting **CV-graded production**.

---

## Feature presence matrix

Legend: ✅ has it · ⚠️ partial / paywalled · ❌ doesn't have · — N/A

| Feature | Lingvano | Duolingo | Drops | Anki | PopSignAI | ASL Bloom | Brilliant | Khan | **Us (v1)** |
|---|---|---|---|---|---|---|---|---|---|
| Camera input | ⚠️ (passive mirror only) | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ✅ |
| CV-graded production | ❌ | ❌ | ❌ | ❌ | ✅ (constrained) | ❌ | ❌ | ❌ | ❌ → ✅ v2 |
| Self-report grading | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Reference video (Deaf signer) | ✅ named | — | ❌ | ❌ | ✅ named (4 from DPAN) | ✅ unnamed | — | — | ✅ named |
| Streak | ✅ | ✅ (hard) | ✅ | ❌ | ❌ | ✅ | ✅ (soft) | ⚠️ (small) | ✅ (soft) |
| Streak freeze | ✅ | ✅ (auto) | ⚠️ Premium | — | — | ✅ | ✅ (earned) | — | ✅ (auto, 2/wk) |
| Hearts / lives | ❌ | ⚠️ → Energy 2025 | ⚠️ Premium gate | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Mastery levels per item | ❌ | ⚠️ (skill levels) | ⚠️ (Dojo) | ✅ (FSRS retention) | ❌ | ❌ | ❌ | ✅ (5-level) | ✅ (5-level) |
| Spaced repetition | ⚠️ Vocab Trainer | ⚠️ implicit | ✅ (Dojo) | ✅ (FSRS) | ❌ | ⚠️ flashcards | ❌ | ⚠️ | ✅ (1d/3d/7d/14d) |
| Public leaderboard | ❌ | ✅ (Leagues) | ❌ | ❌ | ❌ | ❌ | ⚠️ (auto-enrolled) | ❌ | ❌ |
| Mascot character | ✅ Mano | ✅ Duo | ⚠️ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Free tier | ⚠️ stub | ✅ (with ads) | ⚠️ 5-min/day | ✅ desktop free | ✅ free | ⚠️ deceptive paywall | ⚠️ limited | ✅ entirely free | ✅ (pilot) |
| Account / sign-in | ✅ | ✅ | ✅ | ⚠️ (sync only) | ❌ | ✅ | ✅ | ✅ | ✅ |
| Camera permission flow | ⚠️ basic | — | — | — | ✅ | — | — | — | ✅ (NN/g priming) |
| Side-by-side replay (user + reference) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Confidence indicator | — | — | — | — | ❌ | — | — | — | ⚠️ v2 |
| Hint usage penalizes mastery | — | ❌ | ❌ | ❌ | — | — | ❌ | ✅ | ❌ (consider) |
| Out-of-distribution / OOD rejection | — | — | — | — | ❌ | — | — | — | ⚠️ v2 |
| Native ASL parameter taxonomy in UI | ❌ | — | — | — | ❌ | ⚠️ (blog only) | — | — | ✅ |
| WCAG 2.2 AA target | ⚠️ unclear | ⚠️ partial (DuoRadio fails) | ⚠️ drag-only | ⚠️ | ⚠️ unverified | ⚠️ unverified | ⚠️ unverified | ✅ + annual VPATs | ✅ |
| Captions on reference video | ⚠️ | — | — | — | ⚠️ unverified | ⚠️ unverified | — | ✅ | ✅ |
| Dev / mock affordances spec'd | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

Two columns dominate our differentiation: **CV-graded production** and **side-by-side replay (user + reference)**. The only competitor with the first is PopSignAI, and it's Android-only with a constrained classifier and no confidence/OOD safety.

---

## Engagement-design lessons (Lingvano, Duolingo, Drops)

These apps optimize for daily active users and session repetition. We borrow selectively because engagement ≠ learning outcomes, but the patterns are real.

### What to take

- **Auto-applied streak freezes** (Duolingo, Brilliant, our spec) — no manual activation, no shame. Brilliant explicitly *earns* freezes through real learning, which closes the freeze-as-gimmick critique. **Borrow Brilliant's model.**
- **Two-slot push notification ceiling** (Duolingo) — max 2/day, no scheduled broadcasts, save-the-streak microcopy is the load-bearing one ("Your 36 day streak ends in 10 minutes. One lesson saves it."). Adopt the cap, drop the mascot guilt.
- **Soft paywall with no credit card on signup** (Lingvano) — friction-light onboarding, reveal pricing only after value is felt. For our college-pilot phase this is moot (free), but the pattern survives if we ever charge.
- **5-min hard timer as a focus mechanic** (Drops free tier) — *as a focus tool, not a monetization wall*. We've defaulted to 5–8 minutes per session for this reason; Drops shows it can become habit-forming. Don't gate it behind premium.
- **Vocabulary by frequency** (Lifeprint via our research, plus Drops categorizing by use-context) — keep this. Lingvano's Unit-by-theme model produces less mastery transfer per hour.

### What to avoid

- **Hearts / Energy / any system that gates practice on correctness** (Duolingo's July 2025 Hearts → Energy switch produced overwhelming backlash). Practice is the thing we're selling; rationing it is incoherent.
- **Public leaderboards / Leagues** (Duolingo, Brilliant's auto-enrolled Leagues) — both Hanus & Fox 2015 evidence and Brilliant's stumble argue against. If included at all, opt-in.
- **Mascot guilt-trip notifications** (Duolingo's "Duo is disappointed") — adult college learners. We use Linear / Notion as our tonal reference, not Duolingo.
- **Color-only result encoding** (Duolingo on a11y) — pair every color signal with an icon. We already spec'd this.
- **Audio content without transcripts** (Duolingo's DuoRadio) — a category fail for any app whose audience may include deaf/HoH instructors and learners. Our reference videos require captions per the spec.
- **Drag-only / no-keyboard interaction** (Drops) — a11y debt. Our keyboard shortcuts (SPACE / B / Shift+B / R / H / N) avoid this.
- **Hidden / deceptive paywall** (ASL Bloom, revealed only after profile creation) — destroys trust and reputation. Pricing should be visible before sign-up.

---

## Effectiveness-design lessons (Anki, Khan Academy, Brilliant, PopSignAI)

These apps have outcome-driven pedagogy. This is where most of our principles came from.

### What to take

- **Pretesting / productive failure** (Brilliant) — Brilliant starts lessons with a problem before any teaching, then unlocks the explanation. Translates directly to our Drill: present the sign target, give the learner one rep without coaching, then surface the reference + hint if they fail. Increases motor encoding (Hocking et al. 2024) and frames the reference video as relief, not preview. **Add this to our Rep state machine.**
- **Interactive wrong-answer panels** (Brilliant) — when wrong, Brilliant shows a manipulable explanation (slider, drag, etc.), not text. Our analogue: a slowed reference clip the learner can scrub, overlaid with the failing parameter highlighted (handshape diagram, movement arrow). **More valuable than a one-line hint string.**
- **5-level mastery model** (Khan Academy) — we adopted this in principles.md. Khan's thresholds: 70 / 85 / 100 / 100-on-test for advancement, with asymmetric advance/regress. We should formalize these exact thresholds rather than leaving "advance after passes twice" hand-wavy.
- **Hints disqualify mastery advancement** (Khan Academy rule) — using a hint on an exercise means that exercise doesn't count toward Proficient/Mastered. **Strong incentive to attempt before requesting help; mirrors self-controlled-feedback findings (Carter et al. 2014 "Self-After" pattern).** We should consider this for our spec.
- **Interval preview on the grading buttons** (Anki) — `Again 1m | Hard 6m | Good 4d | Easy 7d` shows the consequence of each judgment. Our self-report buttons ("I got it" / "Not quite" / "Skip") could expose this: "Got it → review in 3 days." Makes the SRS legible.
- **Leech detection + auto-suspend** (Anki) — items with 8+ lapses get suspended. Our equivalent: a sign that fails >5 reps across 2 sessions gets a "needs human help" flag and removed from active rotation. **Prevents grind-induced demoralization.**
- **Constrained-vocabulary classifier** (PopSignAI's headline trick) — they achieve "99.6% accuracy" by constraining classification to the 5 contextually plausible signs per level rather than the full vocabulary. **Our `evaluate(drillType, target, frames)` interface already does this**; we should re-frame our v2 trigger criteria (≥92% top-1) as *constrained against the expected drill target*, not open-vocabulary, which is a much easier ML gate.
- **Outcomes research published openly** (Khan Academy's SRI/Gates, Idaho/Albertson 1.8× effect, 2023 RCT +0.12-0.22 SD) — Khan's credibility partly comes from showing their work. Long-term: do our own retention measurement and publish.
- **Sparse 4-button grading vocabulary** (Anki's Again/Hard/Good/Easy) — small button set, instantly memorable, keyboard mapped to 1/2/3/4. Our 3-button self-report is in the same shape.
- **Annual VPATs** (Khan Academy) — accessibility conformance audited externally and published. Even if we don't commission one for the pilot, frame it as the path.

### What to be skeptical of

- **PopSignAI silently rewarding sloppy signs** — the worst failure mode (player signs sloppily but accidentally produces something the constrained classifier accepts) is left unguarded. We should ship OOD rejection from day one of v2, even if it costs accuracy.
- **PopSignAI's reference video probably hidden during recording** — they cite cognitive load. Our current spec shows reference video alongside the camera. **Decision needed**: hide reference video during active recording (toggle off at COUNTDOWN, back on at SELF_REPORT) vs always-visible. The cognitive-load tradeoff is real. Recommend testing both.
- **Khan's "hint penalizes mastery" rule** — strong incentive but risks shame spiral if learners avoid hints they need. For ASL beginners specifically, we should A/B vs no-penalty hints. Start without the penalty.

---

## ASL-specific lessons

### What the existing ASL space gets right

- **Deaf instructors on video** (Lingvano, PopSignAI's DPAN signers, ASL Bloom — though unnamed) — universal. Our spec already requires this.
- **Slow-motion reference playback** (ASL Bloom's "turtle" button, Lingvano's slow-replay) — small UX detail, high pedagogical value. Add a slow-toggle on every reference clip.
- **Per-sign dictionary pages** (ASL Bloom's `/signs/<sign>` public URLs) — discoverable by search engines, useful as quick lookups outside the practice loop. Worth adding.
- **The 5 parameters as a teaching frame** (ASL Bloom's blog post, our principles.md) — explicit naming of handshape / movement / location / palm orientation / NMM gives learners a vocabulary for self-correction. We surface this through Drill structure; ASL Bloom only does it in blog content. We do it better.

### What the existing ASL space gets wrong

- **Unnamed Deaf signers** (ASL Bloom) — using Deaf labor without crediting it is exactly the appropriation pattern Handspeak and Desai et al. (2024) document. Our spec requires individual credits.
- **English-mouthing during sign demos** (ASL Bloom reviewer-flagged) — teaches learners to associate signs with English mouth shapes rather than ASL non-manual markers. Recipe for a hearing-accented learner. Brief our Deaf signers on the difference.
- **Receptive-only learning marketed as "ASL learning"** (Lingvano, ASL Bloom) — this is the gap our spec exploits. Receptive ≠ productive (Schönström 2021, Webb 2008). Both can produce false confidence without production practice.
- **No CV grading despite user demand** (Lingvano App Store reviews explicitly ask for it) — the market has been told to wait. We can answer.
- **Constrained-but-overclaimed accuracy** (PopSignAI's 99.6% headline) — Their open-vocab is 82.9%. Honesty about constraint vs accuracy is the right framing. We should publish both numbers when v2 ships.

---

## What only we will have (in the v1 + v2 corpus)

1. **Browser-based** in-pocket ASL practice (PopSignAI is Android-only; the rest of the ASL space doesn't do CV)
2. **Parameter-level drill decomposition** (Handshape → Movement → Sign, each ×3 reps) — no competitor decomposes signs this way
3. **Side-by-side replay of the user's last attempt + reference** in a wrong-answer panel — none of the 8 do this
4. **Explicit `evaluate(drillType, target, frames)` constrained-target interface** — the architecture choice PopSignAI's results retroactively justify
5. **5-level mastery model **specific to motor learning** (vs Khan's cognitive-problem mastery) — borrowed structure, new domain
6. **Dev panel with labeled `[Dev: …]` overrides** — none of the 8 specs surface dev affordances, but ours is a build-first deliverable
7. **A seeded dev account with 75 days of varied practice data** for visual development of the dashboard heatmap — explicit affordance
8. **Sign-frequency-ordered vocab** (per Lifeprint) — Lingvano sequences by theme; we sequence by use frequency
9. **Honest scope copy**: "vocabulary practice, not ASL learning" — every ASL competitor overclaims; our spec explicitly underclaims
10. **Bring-Deaf-consultant-before-pilot** built into the spec as Open Questions — pre-empts the criticism pattern documented by Desai et al. and Glasser et al.

---

## What everyone has that we're (currently) missing

These are table-stakes features we should consider adding before launch:

1. **Per-sign public dictionary page** (`/signs/THANK_YOU`) — ASL Bloom and Lingvano both do this. SEO + quick-lookup utility. Low cost. **Add.**
2. **Slow-motion toggle on reference videos** — ASL Bloom, Lingvano, Yousician. Trivial implementation. **Add.**
3. **"Continue where you left off"** persistent state — Duolingo, Khan, Brilliant all do this. Our dashboard "Continue last lesson" CTA covers it but the state model needs to track the exact rep, not just the lesson.
4. **Recently-viewed signs strip** — Anki's "recently studied," Khan's "Recent activity." Useful for review and dashboard density. **Already in ux-spec.md but worth confirming the data model supports it.**
5. **Daily reminder time picker with informational (not punitive) copy** — Brilliant, Duolingo, Khan. Our Notification Preferences page covers it; reinforce the informational framing in microcopy.
6. **Energy points / "you earned X" feedback** — Khan Academy's energy points dominate over streaks in their UX. We don't have an equivalent. Could add: "8 mastery points this session" as a quiet alternative to streak-counting. Optional.
7. **A search box on the lesson catalog** — Duolingo (Section search), Anki (deck filter), Khan (course search). We have it in the spec; ensure implementation.
8. **Notification settings per channel** — email vs push vs in-app. Our spec covers this.
9. **An accessibility statement page** — Khan Academy publishes one with annual VPAT links. Add as the privacy-page sibling.
10. **A way to add a sign to a "needs more work" list** — Anki's "leech" auto-flag and the Khan "needs review" surfaces. Our 5-level mastery model implicitly does this (the Learning stage). Make sure the dashboard surfaces it.

---

## Anti-patterns confirmed across multiple apps

When ≥3 of the 8 confirmed the same anti-pattern, treat it as a hard "no":

- **Public leaderboards default-on** (Duolingo, Brilliant, several others by ports) — opt-in only or skip entirely
- **Punitive streak loss** (Duolingo pre-Streak-Freeze) — auto-applied freezes prevent
- **Pure-completion mastery** (Brilliant treats lesson-completion as mastery, third-party reviewers note this superficiality; Lingvano same) — we explicitly use *5-level mastery per sign*, not lesson-completion
- **Unnamed Deaf labor** (ASL Bloom; Lingvano partial — they name some) — our spec requires individual credits
- **Color-only success/fail encoding** (Duolingo on a11y axes) — pair color with icon, already spec'd
- **Hidden pricing** (ASL Bloom) — show price before sign-up
- **Aggressive mascot guilt** (Duolingo's Duo; Lingvano's Mano is milder) — adult learners
- **Hint-as-defeat framing** (none surveyed handle this well except Khan's mastery-penalty, which has its own risks) — frame as "Show me what to change," not "I give up"

---

## Concrete spec changes recommended

These are edits to make to `ux-spec.md` and `principles.md`:

### High-priority (do before any build starts)

1. **Add pretesting / productive failure to the Rep state machine.** First rep of every new sign: present target, no reference video, no hint until after one attempt. Then unlock reference video.
2. **Re-frame v2 trigger criteria as constrained-target accuracy** (per PopSignAI insight). The ≥92% top-1 / ≥98% top-3 numbers should explicitly be on the constrained-to-expected-target evaluation, not unconstrained open-vocab. This is a substantially easier ML gate.
3. **Add a slow-motion toggle to the reference video** in every appearance (Lesson Intro, Practice Screen, hint panel).
4. **Decide reference-video visibility during RECORDING state.** PopSignAI hides theirs for cognitive-load reasons. Spec a toggle defaulting to hidden during RECORDING, visible everywhere else. A/B-test post-launch.
5. **Add per-sign public dictionary pages** (`/signs/<sign-slug>`) — discoverable, useful, low-cost.
6. **Document the exact mastery thresholds.** Following Khan: 70% / 85% / 100% / 100-on-test for the 5 levels. Adapt the percentages for ASL drill semantics but pin them down.

### Medium-priority

7. **Brilliant-style interactive wrong-answer panel.** When a Rep fails: show side-by-side replay (already spec'd), plus a parameter-specific overlay (handshape diagram for handshape errors, movement arrow for movement errors). The diagram is the "manipulable explanation."
8. **Leech-style auto-suspend.** After ≥5 failed reps across 2 sessions, flag the sign as "needs human help" and remove from active rotation until the learner explicitly re-engages it.
9. **Interval preview on self-report buttons.** "I got it (review in 3 days)" instead of just "I got it." Makes the SRS scheduler legible.
10. **Energy-points-style mastery currency.** Quiet additive counter ("12 mastery points this session") as a non-streak progress signal. Optional.

### Low-priority / consider

11. **Hint-penalizes-mastery rule** (Khan's). High risk of shame spirals for ASL beginners; A/B against no-penalty hints before adopting.
12. **Daily reminder with non-punitive microcopy.** Already spec'd; reinforce the tonal guidance in the microcopy bank.
13. **Friend Streaks / co-learning** (Duolingo's +22% completion finding). Out of scope for the pilot but a documented v3 candidate.

### Explicitly REJECTED after this analysis

- **Hearts / Energy / practice-rationing** — confirmed anti-pattern, hard no
- **Public default-on leaderboards** — anti-pattern across multiple apps
- **Mascot character** — tonally wrong for our audience
- **DuoRadio-style audio without transcripts** — a11y failure
- **Hidden / deceptive paywalls** — trust failure (ASL Bloom)
- **Receptive-only practice marketed as ASL learning** — our spec explicitly inverts this

---

## Strategic positioning summary

| Dimension | Their position | Our position | Defensibility |
|---|---|---|---|
| Production grading | Receptive-only (Lingvano/Bloom) or constrained CV (PopSignAI) | Self-report v1 → constrained CV v2 | High — only browser CV-graded ASL |
| Deaf labor | Unnamed / outsourced (ASL Bloom) | Named, credited, compensated | High — table-stakes in 2026 |
| Mastery model | Lesson-completion (Brilliant) or vocab-recall (Lingvano) | 5-level per-sign motor mastery | Medium — Khan model adapted to motor |
| Engagement primary | Streaks (Duolingo) | Mastery bars; soft streak secondary | High — SDT + spaced-repetition base |
| Honest scope | Overclaims (ASL Bloom, Duolingo) | Underclaims ("vocab practice") | High — Deaf community signal |
| Browser-first | Few (Khan, Brilliant) | Yes | Medium — depends on hardware reach |
| Free during pilot | Yes (most) | Yes | Equivalent |

The defensibility column says: in the dimensions where we differ, the differences are pedagogically defensible and have either peer-reviewed evidence (mastery, motor encoding, spaced repetition) or Deaf community signal (Desai 2024, Glasser 2025, Handspeak appropriation page) backing them. We aren't gambling.

---

## Open strategic questions

1. **Do we ship slow-motion + scrub on reference videos?** Cheap. Probably yes.
2. **Hide reference video during RECORDING state?** Cognitive-load trade-off. A/B post-launch.
3. **Hint-as-mastery-penalty?** High risk for beginners. Default to no penalty; experiment later.
4. **Per-sign dictionary pages?** SEO + utility win. Add unless data-model cost is prohibitive.
5. **Leech auto-suspend threshold?** 5 failures / 2 sessions is a guess. Will need real-data calibration.
6. **Constrained vs open-vocab CV accuracy publication?** Publish both when v2 ships. PopSignAI's 99.6% headline is a credibility lesson.
7. **Friend Streaks for v3?** Out of pilot scope, but the +22% completion finding is hard to ignore long-term.

---

## Files to update based on this analysis

- `docs/ux-spec.md`: add Section "Pretesting / productive-failure pattern" to the Rep state machine; add slow-motion toggle to Reference Video sections; add `/signs/<slug>` public dictionary to Page Inventory; clarify mastery thresholds (Khan-style) in the mastery section
- `docs/principles.md`: re-frame v2 trigger criteria as constrained-target accuracy; add the PopSignAI 99.6%-vs-82.9% honesty note
- `docs/competitive/comparison.md`: this file

The synthesis is the actionable artifact. The 8 competitive teardowns are durable reference material — re-read when designing specific features.
