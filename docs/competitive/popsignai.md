# Competitive Teardown — PopSignAI

PopSignAI is the closest shipping precedent to what we're building: a peer-reviewed, CV-graded ASL lexical-sign recognizer inside a learning game, from Georgia Tech's Contextual Computing Group (Thad Starner) with RIT/NTID and the Deaf Professional Arts Network (DPAN), dataset funded via a Google/Kaggle competition. Pedagogy differs (parents-of-Deaf-infants vs. our college vocabulary practice) but the CV/UX seam is the closest match in the world. UNVERIFIED tags mark unconfirmed claims.

---

## 1. Naming hierarchy

PopSign's hierarchy is flatter than ours: **Game → Level → Bubble → Sign → Shot**. "The first seven level are available" in PopSignAI preview ([APKPure](https://apkpure.net/popsignai-preview/edu.gatech.popsignai)); each level pairs ~5 signs with ~5 bubble colors; one Shot is one aim-and-sign action. There is **no equivalent to our Drill** — PopSignAI grades whole-sign only. No parameter-focused (Handshape / Movement) breakdown ships. UNVERIFIED whether the in-game tutorial introduces any sub-sign scaffolding.

---

## 2. Page inventory

Best-effort reconstruction; we don't have authenticated access to in-app navigation.

| # | Page | Source |
|---|---|---|
| 1 | Marketing site (popsign.org) | [popsign.org](https://www.popsign.org) |
| 2 | Start screen | popsign.org asset `popsign screens start-1.png` |
| 3 | Tutorial / pre-game intro | "Pre-game tutorials included" ([Devpost](https://devpost.com/software/pop-sign-learning)) |
| 4 | Vocabulary intro (reference video) | [RIT release](https://www.rit.edu/news/parents-deaf-children-can-more-easily-learn-sign-language-thanks-powerful-tech-collaboration) |
| 5 | Gameplay (bubble shooter) | core loop |
| 6 | Level-complete / advance | implied; UNVERIFIED |
| 7 | Customization / word picker | [Devpost](https://devpost.com/software/pop-sign-learning); UNVERIFIED in current preview |
| 8 | Credits / Thanks | popsign.org asset `popsign screens thanks.png` |
| 9 | Camera permission prompt | required; pre-prompt UNVERIFIED |
| 10 | Settings | UNVERIFIED |

**Absent vs. our spec:** no account/auth flow (App Store: "the developer does not collect any data"), no dashboard/heatmap/streaks, no lesson catalog with filtering, no dedicated privacy or help pages beyond the marketing site.

---

## 3. Per-page feature lists

**Marketing site (popsign.org)** — Headline "Learn American Sign Language with PopSign"; CTAs include "Play and Learn", "Improve together", "Help us make PopSignAI even better!", "Start learning today"; app-store badges; audience pitch on "95% of deaf infants born to hearing parents"; credits page lists divisions (Sign Language Recognition, PopSign Game Development, SignData Pipeline & QA, SLR-GTK, VIP Team Leads, NTID), with DPAN signers **Sean Forbes, Michaela Jitaru, Erin Lafave, Nathan Qualls** named ([popsign.org](https://www.popsign.org)).

**Tutorial / pre-game intro** — "Pre-game tutorials included before gameplay" ([Devpost](https://devpost.com/software/pop-sign-learning)); content UNVERIFIED.

**Vocabulary intro** — "The app displays a video of a person signing to introduce new vocabulary" ([RIT release](https://www.rit.edu/news/parents-deaf-children-can-more-easily-learn-sign-language-thanks-powerful-tech-collaboration)). All signers are Deaf ASL natives from DPAN. Slow / captions / rewind controls UNVERIFIED.

**Level-complete** — Bubble-shooter genre convention (score + next-level); explicit summary UNVERIFIED.

**Customization** — "Can customize words you want to focus on learning" ([Devpost](https://devpost.com/software/pop-sign-learning)). UNVERIFIED whether present in current PopSignAI preview.

**Gameplay screen** — see §4.

---

## 4. Gameplay screen — the bubble-shooter loop

Two distinct games ship under the PopSign brand:

**PopSign (legacy, receptive-only):** "The app displays a video of a person signing to introduce new vocabulary, and then the user's memory is tested. To advance to the next level, the user drags and shoots a ball to hit bubbles with written words that match the sign" ([RIT release](https://www.rit.edu/news/parents-deaf-children-can-more-easily-learn-sign-language-thanks-powerful-tech-collaboration)). Touch-input aiming, no camera, standard match-3+ mechanic.

**PopSignAI (preview, productive):** Replaces touch-aim with sign production via selfie camera. Per IUI 2026: PopSignAI "allows the user to aim at a colored bubble they would like to clear from the board, then produce the sign associated with that colored bubble" ([IUI 2026](https://dl.acm.org/doi/10.1145/3742413.3789164)). Per APKPure: "the selfie camera to sign one of five signs to aim and shoot" ([APKPure](https://apkpure.net/popsignai-preview/edu.gatech.popsignai)).

The loop:
1. Board shows bubbles in **up to 5 distinct colors**.
2. Each color maps to **one ASL sign** for that level.
3. Player signs on camera.
4. CV classifies → the matching color's bubble at the cursor position pops if a 3+ match exists.
5. Repeat until cleared.

### ASCII wireframe (reconstructed; portrait phone)

```
┌───────────────────────────────────────┐
│  Level 3 / 7         Score: 1240      │
├───────────────────────────────────────┤
│         ○ ○ ● ● ○ ○ ◐ ◐ ●            │
│        ● ● ○ ○ ◐ ● ● ◐ ◐             │
│         ○ ◐ ● ● ○ ◐ ○ ●              │
│                                       │
│   (board of colored bubbles — up to   │
│    5 colors per level)                │
│                                       │
├───────────────────────────────────────┤
│   ╭────── REFERENCE STRIP ──────╮     │
│   │ [vid: HAPPY] [vid: MORE]    │     │
│   │ [vid: EAT]  [vid: DOG] ...  │     │
│   ╰─────────────────────────────╯     │
├───────────────────────────────────────┤
│  ┌─────────────────────────────────┐  │
│  │  SELFIE CAMERA PREVIEW          │  │
│  │  (mirrored, mediapipe overlay   │  │
│  │   UNVERIFIED whether shown)     │  │
│  │                                 │  │
│  │           ●                     │  │
│  └─────────────────────────────────┘  │
│                                       │
│  Recognized: HAPPY  (color → orange)  │
└───────────────────────────────────────┘
```

The reference-strip and exact layout is reconstructed and partially UNVERIFIED — popsign.org's screenshot assets exist but we couldn't directly render them. The crucial confirmed elements are: **selfie camera is on during play**, **at most 5 signs per level**, **signs map to bubble colors**.

### State machine (reconstructed)

```
LEVEL_INTRO
  └─ show vocabulary videos for the level's 5 signs
LEVEL_PLAY
  └─ READY_FOR_SHOT (board visible, camera active)
       ├─ user signs → CV inference (~7ms per IUI 2026 paper)
       │    └─ ARGMAX class with confidence threshold
       │         ├─ above threshold → SHOT (matching-color bubble pops)
       │         └─ below threshold → RETRY (UNVERIFIED visual)
       └─ user signs incorrectly (recognized but wrong sign)
            → SHOT FIRES at wrong color
              (this is the false-positive failure mode — see §5)
LEVEL_COMPLETE (board cleared)
LEVEL_FAIL (UNVERIFIED — bubble shooters usually fail when bubbles reach a line)
```

**Per IUI 2026, the in-game recognizer averages 99.6% accuracy because the level constrains the classification to a 5-class problem rather than the full 250+ vocabulary** ([IUI 2026](https://dl.acm.org/doi/10.1145/3742413.3789164)). The 82.9% test-set number is the open-vocabulary case; the 99.6% is what the player experiences. This is the single most important architectural insight in their UX.

---

## 5. CV integration UX — the seam we care most about

This is the most academically-precedented seam, and also where public sources are thinnest. What we can confirm:

**"AI is watching" affordance.** Selfie camera preview is visible during gameplay ([APKPure](https://apkpure.net/popsignai-preview/edu.gatech.popsignai); [RIT](https://www.rit.edu/news/parents-deaf-children-can-more-easily-learn-sign-language-thanks-powerful-tech-collaboration)). The CHI 2025 abstract explicitly names cognitive load as a design challenge ("addressing challenges related to cognitive load, gameplay intuitiveness, and the technical demands of gesture recognition" — [CHI 2025](https://dl.acm.org/doi/full/10.1145/3706599.3720321)). Recording indicator / hand-skeleton overlay / framing guide — UNVERIFIED.

**Confidence handling.** No evidence that a confidence value or meter is exposed to the player. The 5-class restriction makes confidence margins huge, so the player rarely sees disagreement. Below-threshold inferences likely produce no shot (silent no-op) rather than an explicit "try again" — UNVERIFIED.

**False negatives** (correct sign, wrong recognition) happen ~1 in 250 shots. UNVERIFIED what the user sees; likely no shot fires and the player re-signs.

**False positives** (wrong sign, classified as one of the 5) are the worst-case learning failure — the game rewards the wrong sign. Argmax with no "none-of-the-above" exacerbates this. No documented guard.

**Mirror / self-view.** Preview on-screen during play. Mirrored vs. non-mirrored, hand-keypoint overlay (MediaPipe supports it), reference-video persistence during shooting — all UNVERIFIED. The CHI 2025 cognitive-load emphasis suggests the reference video probably *isn't* visible during shooting, to avoid attention split.

**Implication for our spec.** Closed-set classification at the moment of use translates directly: a Drill evaluates against the *expected* sign for the current rep — a thresholded binary verification — not a 75-class argmax. Better-conditioned ML problem, same UX win.

---

## 6. Dataset / training story exposed in UX

Surprisingly little of the dataset story leaks into the app itself. The popsign.org credits page names the four DPAN signers and the NTID contributors ([popsign.org](https://www.popsign.org)); UNVERIFIED whether this surfaces in-app or only on the web. The PopSign ASL v1.0 NeurIPS 2023 paper — 250 signs, ~210K examples at 1944×2592 from Pixel 4A selfie cams, 47 Deaf adult signers (31/8/8 split), described as "the largest publicly available, isolated sign dataset by number of examples" ([OpenReview](https://openreview.net/forum?id=yEf8NSqTPu)) — does not get mentioned in app-facing copy. No explicit scope statement ("vocabulary practice, not ASL fluency") appears anywhere we could find. **Verdict:** PopSignAI underuses the Deaf-signer story in-product; we should foreground it.

---

## 7. Microcopy bank

Confirmed strings, all quoted from primary sources:

**Marketing (popsign.org):**
- "Learn American Sign Language with PopSign"
- "Play and Learn"
- "Improve together"
- "Help us make PopSignAI even better!"
- "Start learning today"
- "95% of deaf infants are born to hearing parents, who often do not know sign."

**App Store / APKPure description:**
- "PopSignAI is an educational game app that uses sign language recognition, powered by AI, to make learning American Sign Language fun, interactive, and accessible." ([App Store](https://apps.apple.com/us/app/popsignai/id6741191786))
- "PopSign is an educational bubble shooter game that provides a fun and accessible way to learn American Sign Language vocabulary on-the-go!" ([App Store](https://apps.apple.com/us/app/popsignai/id6741191786))
- "Preview of a game that uses sign recognition to make learning ASL fun!" ([APKPure](https://apkpure.net/popsignai-preview/edu.gatech.popsignai))
- "PopSignAI is in preview mode! The first seven level are available." (sic, missing 's') ([APKPure](https://apkpure.net/popsignai-preview/edu.gatech.popsignai))
- "Testing is performed on the Pixel 7 and 7Pro. Other phones are not officially supported yet." ([APKPure](https://apkpure.net/popsignai-preview/edu.gatech.popsignai))

**In-game microcopy (rep feedback, retries, error states):** UNVERIFIED. None of the published sources directly quote in-app strings, and we couldn't get authenticated access to the APK or IPA. This is the single biggest gap in our research.

---

## 8. Tech stack

| Layer | What ships |
|---|---|
| **Platforms** | Native Android (`edu.gatech.popsign`, `edu.gatech.popsignai`) and iOS (App Store, also compatible with M1+ Mac, Apple Vision) |
| **Engine** | Unity (per [Devpost](https://devpost.com/software/pop-sign-learning), "Powered by the Unity game engine for cross-platform capabilities"); UNVERIFIED whether current PopSignAI is still Unity or rebuilt natively |
| **Pose / keypoints** | Google MediaPipe (hand tracking; likely Holistic) ([APKPure](https://apkpure.net/popsignai-preview/edu.gatech.popsignai)) |
| **Inference runtime** | TensorFlow Lite ([APKPure](https://apkpure.net/popsignai-preview/edu.gatech.popsignai)) |
| **Paper baseline** | LSTM over MediaPipe keypoints — 82.1% val / 84.2% test on 250-sign set ([OpenReview](https://openreview.net/forum?id=yEf8NSqTPu)) |
| **Production model** | "User-independent LSTM recognizer… 82.9% accuracy on an independent test set, and for gameplay, the recognizer averages 99.6% accuracy with a 7ms inference time using a 2.5MB model" ([IUI 2026](https://dl.acm.org/doi/10.1145/3742413.3789164)) |
| **Vocabulary** | 250 signs in open dataset; CHI 2025 abstract references a **560-sign SLR model** — likely next-gen, UNVERIFIED |
| **Dataset-collection app** | Separate Android app [`RecordTheseHands`](https://github.com/Accessible-Technology-in-Sign/RecordTheseHands) |

**Implication for our browser app.** PopSignAI is native mobile, not browser. Their TFLite + MediaPipe stack does not translate directly to our deployment target, but the architectural pattern (MediaPipe keypoints + small recurrent model + closed-set classification at the moment of use) does. The 2.5 MB / 7 ms envelope is reachable on the web with ONNX Runtime Web on a college laptop.

---

## 9. Accessibility posture

Almost nothing is documented publicly. Confirmed: reference videos are signed by Deaf native signers (DPAN) ([popsign.org](https://www.popsign.org)); App Store is 4+ rated; "the developer does not collect any data from this app" ([App Store](https://apps.apple.com/us/app/popsignai/id6741191786)) — strong privacy posture. UNVERIFIED: caption presence on reference videos, reduced-motion option, audio-feedback toggle, font sizing, screen-reader compatibility. The "other phones are not officially supported yet" caveat implies device-fragmentation gating users with older Android hardware. We hold ourselves to WCAG 2.2 AA per `principles.md`.

---

## 10. Patterns to STEAL vs AVOID

**STEAL:**

1. **Closed-set CV at the moment of use.** Classifier picks from 1–5 contextually-plausible signs, not the full vocabulary. The 99.6% in-game accuracy is mostly a consequence of this. Maps directly onto our Drill abstraction.
2. **Named Deaf signers in credits.** popsign.org names Sean Forbes, Michaela Jitaru, Erin Lafave, Nathan Qualls. We should do the same plus compensation notes (Glasser et al.).
3. **Preview-mode framing.** "PopSignAI is in preview mode! The first seven level are available" sets honest expectations.
4. **Always-on selfie camera during play.** No per-rep permission re-flow.
5. **Native Deaf reference videos** for vocabulary, not avatars.
6. **Open dataset + pipeline release.** PopSign ASL v1.0 and SLR-GTK are public — reduces credibility debt.

**AVOID:**

1. **Infantilizing gamification.** Bubble-shooter framing fits parents/infants; would feel wrong for adult learners. We hold our Linear/Notion-restrained tone.
2. **Hidden confidence and failure UX.** The 5-class constraint hides real classifier behavior. If a player signs sloppily and accidentally hits a valid class, the game silently rewards them. For learning, that's the worst failure mode. We need explicit "almost — try again" microcopy.
3. **Single-sign-level granularity.** PopSignAI grades whole-sign only. Our Handshape → Movement → Sign decomposition is a real pedagogical advance.
4. **Buried dataset story.** PopSignAI hides the 47-signer / 220K-example backstory in academic papers. Foreground it.
5. **Device-fragmentation lock-in.** "Tested on Pixel 7 and 7Pro" is a real shipping constraint of native Android; our browser-only choice avoids it.
6. **No accounts, no sync.** Privacy-positive but blocks cross-device continuity and pilot measurement. We store mastery + timestamps only, never video.

---

## 11. Open questions / could not verify

1. **Exact in-game microcopy** — retry / failure / level-complete / hint strings. Biggest gap.
2. **Confidence display.** Strongly suspect not exposed; not confirmed.
3. **Reference video during play.** Whether the Deaf-signer reference clip remains visible during shooting or only during vocabulary intro.
4. **Hand-keypoint overlay on the selfie preview.** MediaPipe supports it; UX choice UNVERIFIED.
5. **Current engine.** Unity per 2022 Devpost; CHI/IUI papers don't disclose whether the shipping PopSignAI is still Unity.
6. **560 vs. 250 signs.** CHI 2025 abstract: 560-sign SLR model. IUI 2026 abstract: 250-sign LSTM. Likely 560 is the next-gen recognizer not yet shipped, but UNVERIFIED.
7. **Out-of-distribution rejection.** No documented mechanism for "signed nothing" or "signed a non-vocab gesture."
8. **Mirror toggle / framing guide / calibration.** Not documented.
9. **iOS feature parity.** App Store listing is much sparser than Android APKPure description; UNVERIFIED whether iOS has the same 7 preview levels.
10. **Tutorial scaffolding depth.** "Pre-game tutorials included" but content unknown.
11. **20-person user study details.** Only the high-level finding from the IUI 2026 abstract was retrievable; full design / retention deltas UNVERIFIED.
12. **CHI 2025 competition outcome.** Whether PopSignAI won an award or was an accepted entry only.

---

## Sources

- [popsign.org](https://www.popsign.org) — official project site
- [RIT press release](https://www.rit.edu/news/parents-deaf-children-can-more-easily-learn-sign-language-thanks-powerful-tech-collaboration)
- [PopSign ASL v1.0 — OpenReview / NeurIPS 2023](https://openreview.net/forum?id=yEf8NSqTPu)
- [PopSignAI CHI 2025 abstract — ACM (paywalled)](https://dl.acm.org/doi/full/10.1145/3706599.3720321)
- [PopSignAI IUI 2026 paper — ACM (paywalled)](https://dl.acm.org/doi/10.1145/3742413.3789164)
- [Interaction Mechanics for SLR Games — IUI 2025 (paywalled)](https://dl.acm.org/doi/10.1145/3708557.3716339)
- [iOS App Store listing](https://apps.apple.com/us/app/popsignai/id6741191786)
- [APKPure Android listing](https://apkpure.net/popsignai-preview/edu.gatech.popsignai)
- [Devpost (2022 Unity iOS port)](https://devpost.com/software/pop-sign-learning)
- [RecordTheseHands data-collection app](https://github.com/Accessible-Technology-in-Sign/RecordTheseHands)
- [CHI 2025 Student Game Competition](https://chi2025.acm.org/for-authors/student-game-competition/)
