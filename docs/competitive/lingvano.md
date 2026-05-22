# Competitive Teardown — Lingvano (ASL)

A feature-level UX map of Lingvano (lingvano.com) for apples-to-apples comparison with our `/docs/ux-spec.md`. Lingvano is a Vienna-based, self-funded Austrian startup founded in 2018; its ASL course launched 2020 and as of October 2024 the platform reports ~2.5M learners across ASL/BSL/ÖGS, with the App Store ASL listing crediting "3 million users" in copy [Source: eSchoolNews — https://www.eschoolnews.com/newsline/2024/10/08/sign-language-learning-app-reaches-2-5-million-learners-milestone/] [Source: Apple App Store — https://apps.apple.com/us/app/lingvano-learn-sign-language/id1547252782].

**Research caveat**: lingvano.com and app.lingvano.com both return HTTP 403 to scripted fetches, so direct HTML inspection was not possible. Findings below are reconstructed from Apple/Google store metadata, the public help center (`help-asl.lingvano.com`), the Lingvano blog, third-party reviews (Lingoly, Top Consumer Reviews, ASL Bloom, InnoCaption, ScreensDesign), and the Zero Project case study. Anything I could not directly verify is marked `UNVERIFIED`.

---

## 1. Naming hierarchy

| Their term | Our equivalent | Evidence |
|---|---|---|
| **Course** | Course | One per sign language (ASL course, BSL course, ÖGS course). [Source: help-asl.lingvano.com — https://help-asl.lingvano.com/support/solutions/articles/101000374785-how-much-does-lingvano-cost-] |
| **Unit** | (no exact analog — sits above Lesson) | ASL course described as "8 units and dozens of chapters and lessons" in third-party review. [Source: Lingvano Business — https://www.business.lingvano.com/] `UNVERIFIED` count exactly. |
| **Chapter** | Lesson group | Chapter ends with a "Chapter Quiz" / "end-of-chapter quiz". [Source: Apple App Store description] |
| **Lesson** | Lesson | The atomic learning unit; ~10 min target. [Source: eSchoolNews] |
| **Sign** | Sign | Atomic vocab item (e.g., HELLO, THANK YOU). [Source: ScreensDesign — https://screensdesign.com/showcase/lingvano-learn-sign-language] |
| **Exercise** | Rep / Drill | Includes multiple-choice video recognition, fill-in-the-gap, true/false, matching. [Source: Top Consumer Reviews — https://www.topconsumerreviews.com/best-sign-language-lessons/reviews/lingvano.php] |
| **Sign Mirror** | Practice Screen (no analog in our spec for camera self-view without CV grading) | Camera tool for self-comparison; see §4. |
| **Vocab Trainer** | Spaced-review / mastery refresher | Premium drill mode across previously seen vocab. [Source: Apple App Store] |

Hierarchy (inferred): `Course > Unit > Chapter > Lesson > Exercise`. The term "Sign" is the vocabulary unit each exercise references; chapter quizzes assess across signs in the chapter. Notably they do *not* use a "Drill" abstraction — exercises are typed (matching, MCQ, fill-blank, mirror), not parameter-focused (handshape/movement/sign) like our spec.

---

## 2. Page inventory

| # | Page | Purpose |
|---|---|---|
| 1 | **Marketing landing** (`lingvano.com/asl/`) | Public; pitches Deaf-taught video lessons, 10-min/day promise |
| 2 | **Sign-up / account creation** | Email or social; minimal form per ScreensDesign breakdown |
| 3 | **Onboarding: Language picker** | Choose ASL / BSL / ÖGS; introduced by "Mano" mascot |
| 4 | **Onboarding: Motivation survey** | "Why are you learning?" — options include "Family or community" |
| 5 | **Onboarding: Trial timeline** | Visual 7-day trial timeline with reminder + auto-charge dates |
| 6 | **Soft paywall** | After onboarding/before first lesson; 3 tiers (Annual / 3-mo / Monthly) |
| 7 | **First lesson (HELLO)** | Video instruction by Deaf teacher → immediate MCQ → fill-in-gap |
| 8 | **Lesson video screen** | Deaf instructor video, turtle-icon slow-mo toggle |
| 9 | **Exercise screen — MCQ** | Match sign video to English meaning, or match English to sign |
| 10 | **Exercise screen — fill-in-the-gap** | Build a phrase by selecting signs/tokens |
| 11 | **Exercise screen — true/false** | Statement + video, judge correctness |
| 12 | **Exercise screen — Sign Mirror** | Camera-on self-comparison vs. teacher video (premium) |
| 13 | **Exercise feedback overlay** | Correct/incorrect with both correct + user's wrong answer shown |
| 14 | **Learning Recap** | End-of-lesson list of every sign learned, tap-to-review |
| 15 | **Chapter Quiz** | Cumulative across the chapter's lessons |
| 16 | **Lesson Result** | Score + stars (up to 5 per milestone lesson) |
| 17 | **Continue / next-lesson modal** | Post-completion nudge to keep going |
| 18 | **Course map / progress** | Shows units → chapters → lessons completion; "1 of 6 lessons completed" pattern |
| 19 | **Streak ignition** | Animated swipe-up gesture to "ignite" the streak |
| 20 | **Streak freeze collected** | URL evidence: `/streak/freeze-collected` — modal when freeze auto-applied |
| 21 | **Awards** | Streak Guardian, Zero-Miss Wiz, Signs Collector, Rising Star achievements |
| 22 | **Curiosities** | Unlockable fun-fact cards about Deaf culture |
| 23 | **Dictionary** (premium) | Searchable sign lookup outside lessons |
| 24 | **Vocab Trainer** (premium) | Adaptive review across learned signs + fingerspelling/numbers |
| 25 | **Settings / Account** | Camera permission, subscription mgmt, language change |
| 26 | **Help center** (external subdomain) | `help-asl.lingvano.com` — articles, ticket form |
| 27 | **Share feedback** | In-app menu item linking to support ticketing |

[Source: ScreensDesign breakdown — https://screensdesign.com/showcase/lingvano-learn-sign-language] [Source: Lingvano blog "Awards & Curiosities" — https://www.lingvano.com/asl/blog/introducing-awards-curiosities-celebrate-your-learning-progress/] [Source: Top Consumer Reviews] [Source: Apple App Store]

---

## 3. Per-page feature lists

### Marketing landing (1)
- 3M-users social proof; Deaf-teacher emphasis
- Course picker (ASL/BSL/ÖGS) above the fold
- "10 minutes a day" promise (lifted across all marketing copy)
- App Store / Play Store badges + "Try on web" CTA
- B2B link to `business.lingvano.com` for enterprise
- Free trial CTA (no credit card up front per support docs)

### Onboarding flow (3–6)
- 10 onboarding steps total per ScreensDesign
- Mascot **"Mano"** (hand-shaped character) personifies the assistant role across onboarding
- Language selection: ASL / BSL / ÖGS
- Motivation survey (multiple choice): includes "Family or community" option `UNVERIFIED full option list`
- Trial timeline visualization: shows day 0 (start), day 5 (reminder), day 7 (charge) on a timeline
- Soft paywall lands *after* the survey but *before* the first lesson — i.e., they show value then ask for the card, but the user *can* skip into limited free content [Source: ScreensDesign]
- 3 plans on paywall: Annual (44% off badge), 3 Months, Monthly [Source: ScreensDesign]

### Lesson video screen (8)
- Video plays Deaf instructor signing
- **Turtle icon** = slow-mo playback toggle (consistent across exercises)
- Scrubber + replay
- No audio — app explicitly described as soundless in store metadata [Source: Apple App Store]

### Exercise types (9–12)
- **MCQ**: video → 3–4 English glosses; or English → 3–4 sign videos
- **Fill-in-the-gap**: pick signs to complete a phrase (mirrors Duolingo word-bank pattern)
- **True/False**: claim about a signed clip
- **Matching**: pair sign to picture or video
- **Right/Left hand differentiation** prompt type for two-handed signs
- **Sign Mirror**: camera-on practice (see §4)
- All exercises support the slow-mo turtle

### Exercise feedback (13)
- Shows **both** the wrong answer the user picked AND the correct answer side-by-side ("Immediate Error Correction" per ScreensDesign)
- Non-punitive framing — no life/heart loss visible in screenshots
- Auto-advance to next exercise

### Learning Recap (14) + Lesson Result (16)
- Recap = list of every sign just learned; tap a row to replay
- Result = numeric score + up to 5 stars on "milestone" lessons [Source: Apple App Store]
- "Improved Lesson Result Experience" was a v5.1.0 changelog item (Feb 2026) [Source: Apple App Store version history]
- Followed by a modal that pushes "continue" (per ScreensDesign)

### Dashboard / Course map (18)
- Progress phrasing seen: "1 of 6 lessons completed" [Source: ScreensDesign]
- Streak counter + streak freeze indicator surfaced
- Awards & Curiosities entry points
- `UNVERIFIED` — exact dashboard layout; no contributions-style heatmap observed in available screenshots

### Streak system (19–20)
- Streak ignition: animated, swipe-up "ignite" gesture (a designed-for-engagement moment, not just a number bump)
- **Streak freeze**: auto-applied protection when a day is missed; dedicated `/streak/freeze-collected` route suggests a celebratory modal
- Freezes are *collected* (vs. Duolingo's purchasable freezes) — possibly earned through play `UNVERIFIED`

### Awards & Curiosities (21–22)
Four named awards [Source: Lingvano blog — Awards & Curiosities post]:
- **Streak Guardian** — levels up with longest streak
- **Zero-Miss Wiz** — lessons completed with no mistakes
- **Signs Collector** — count of signs learned/unlocked
- **Rising Star** — milestone stars stacking toward a level-up

**Curiosities** = bite-sized unlockable facts about Deaf culture & sign language history. Functions as collectible content (Octalysis "milestone unlocks" pattern).

### Dictionary (23) — premium
- Searchable across all signs in the course
- Used outside lessons for ad-hoc lookup
- Premium-gated [Source: ASL Bloom — https://www.aslbloom.com/blog/best-asl-app]

### Vocab Trainer (24) — premium
- Adaptive across learned signs; help center calls it a "smart trainer section that adapts to individual learning progress" [Source: help-asl.lingvano.com — content overview article]
- Covers vocabulary + fingerspelling + numbers
- `UNVERIFIED` whether it uses true SRS intervals or simpler weakest-first selection

### Settings / Account (25)
- Subscription management (web + native IAP flows differ)
- Camera permission re-grant flow (detailed in help center per-platform)
- "Share feedback" menu item routes to support ticketing

### Help center (26)
- Hosted on Freshworks (`help-asl.lingvano.com` URL pattern + article structure)
- Three top categories: General / ASL / Lingvano for Business
- Premium & billing folder = 10 articles (pricing, cancellation, refunds, currency, invoices, etc.)
- No standalone "Sign Mirror" or "Practice" category — feature articles live inside General

---

## 4. Practice / Sign Mirror — deep dive

The Sign Mirror is the closest analog to our Practice Screen, but the behavior is fundamentally different: **Lingvano's mirror does not score, classify, or grade the user's sign.** It is a self-comparison tool — a live camera view next to the teacher's video. The "instant feedback" language in marketing is self-perceptual feedback, not CV-based correctness feedback.

Confirmed:
- Camera permission is required; help center includes per-OS re-enable steps [Source: help-asl.lingvano.com — "Why does the mirror not work?" — https://help-asl.lingvano.com/support/solutions/articles/101000374811-why-does-the-mirror-not-work-]
- The user watches their own movements and self-corrects ("watch their own movements and to correct them if necessary" — Zero Project case study) [Source: https://zeroproject.org/view/project/ed68f3cd-30ea-4992-9530-d0a8a3f25506]
- Available on iPhone, Android, and desktop browsers (camera permission required on all three)
- It is a **premium-gated** feature [Source: ASL Bloom]
- One App Store reviewer specifically requested "video recording capability for signing verification" — implying the mirror does *not* record or play back the user's attempt [Source: Apple App Store user reviews]

Not verified:
- Whether the mirror runs concurrently with the teacher video (split view) or as a separate "now you try" stage after the teacher clip
- Whether mirror invocation is automatic on certain exercise types or always user-initiated
- Whether the mirror frame is mirrored horizontally (per typical convention) or raw camera

### State machine (Lingvano lesson loop — reconstructed)

```
LESSON_START
  └─ for each Exercise in lesson.exercises:
       EXERCISE_PRESENT (video or prompt shown)
         └─ user input (tap MCQ / drag tokens / true-false / sign on camera)
              ├─ correct  → FEEDBACK_CORRECT (green + "next" advance)
              └─ wrong    → FEEDBACK_CORRECTIVE (shows wrong + right side-by-side)
       (no retry-in-place — incorrect answers advance forward, scored)
  └─ LEARNING_RECAP (list view, tap any sign to replay)
  └─ LESSON_RESULT (score, up to 5 stars on milestone lessons)
  └─ CONTINUE_MODAL (nudge toward next lesson)
       └─ → next LESSON_START  or  → DASHBOARD
```

For Sign Mirror specifically:
```
MIRROR_OPEN
  └─ camera permission check
       ├─ granted  → MIRROR_ACTIVE (teacher video + live self-view side by side)
       │              └─ user self-judges; taps "next" or "got it"
       │                   → advance (no scoring event recorded)
       └─ denied   → PERMISSION_HELP (per-OS instructions article)
```

No green/orange/gray bounding-box equivalent exists — there is no CV pipeline behind the mirror. This is a substantial product gap relative to our spec.

### ASCII wireframe (Sign Mirror, reconstructed from descriptions; not verified pixel-accurate)

```
┌──────────────────────────────────────────────────────────────────┐
│  ← Chapter 2 · Lesson 3            Exercise 4 of 7    [ × close ]│
│  [██████░░░░░░░░] 57%                                            │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│   "Sign: THANK YOU"                                              │
│                                                                  │
│   ┌────────────────────────┐    ┌────────────────────────┐       │
│   │                        │    │                        │       │
│   │   TEACHER VIDEO        │    │   YOUR CAMERA          │       │
│   │   (Deaf signer)        │    │   (live self-view,     │       │
│   │                        │    │    no overlay)         │       │
│   │   🐢 slow-mo toggle    │    │                        │       │
│   │                        │    │                        │       │
│   └────────────────────────┘    └────────────────────────┘       │
│                                                                  │
│        [  ▶ Replay teacher  ]      [  I got it →  ]              │
│                                                                  │
│   (No bounding box. No score. User self-judges.)                 │
└──────────────────────────────────────────────────────────────────┘
```

`UNVERIFIED` — the actual layout may use a vertical stack on mobile and side-by-side on tablet/web; ScreensDesign frames suggest portrait orientation dominates.

---

## 5. Microcopy bank (verified strings)

Strings I could confirm directly from store metadata, the help center, or third-party reviews that quoted Lingvano UI:

**Marketing / value pitch**
- "Start signing in your very first lesson" [Apple App Store]
- "Become conversational with 10 minutes a day" (paraphrased across multiple sources)
- "Bite-sized lessons" [Apple App Store]
- "All lessons are taught by passionate teachers who are Deaf and fluent in the sign languages they teach" [eSchoolNews quoting Lingvano]

**Pricing / paywall**
- "Free Trial" / "Soft Paywall" classification [ScreensDesign]
- Annual "44% saving" badge [ScreensDesign]
- "Signing up for Lingvano is completely free of charge and you can try out a few lessons without providing your payment details" [help center]
- "the premium memberships help us to continuously improve and expand the learning experience" [help center, "Why isn't Lingvano free?" article]

**Progress phrasing**
- "1 of 6 lessons completed" [ScreensDesign]
- "Learning Recap" (screen title) [Top Consumer Reviews]
- "Improved Lesson Result Experience" [Apple App Store changelog v5.1.0]

**Streak / awards**
- "Streak Guardian", "Zero-Miss Wiz", "Signs Collector", "Rising Star" (verbatim award names) [Lingvano blog]
- "Curiosities" (collectible-fact category name) [Lingvano blog]
- `/streak/freeze-collected` (route → modal) [search index]

**Help center**
- "Share feedback" (menu label that routes to ticketing) [help center: mirror troubleshooting article]
- "Why does the mirror not work?" (article title) [help center URL]

**Microcopy I could NOT verify** (would need authenticated app access):
- Exact correct/incorrect feedback strings — descriptions say "Highlights both wrong and correct answers" but the literal text is unknown
- Streak ignition copy
- "Continue" modal exact wording
- Permission-priming copy before camera prompt
- Lesson-complete celebration line

---

## 6. Tech stack (inferred)

What I can deduce from public surfaces:

| Layer | Inferred | Evidence / confidence |
|---|---|---|
| **Mobile** | Native iOS + native Android (likely Swift / Kotlin) | App Store requires iOS 15.1+/iPadOS 15.1+/macOS 12+/visionOS 1+; visionOS support is uncommon for cross-platform frameworks like RN/Flutter without extra work, which leans toward native. Android version is a single APK per Play Store. `UNVERIFIED` — could still be Flutter with native shims. |
| **Web app** | SPA at `app.lingvano.com` (separate from marketing) | Subdomain split implies different build. 403 to bots = behind a CDN/WAF. `UNVERIFIED` framework. |
| **Marketing site** | CMS-driven; both `lingvano.com` and the blog return 403 to scripted fetches → strong WAF posture (Cloudflare bot management or similar) | Confirmed 403 behavior across both `lingvano.com` and `app.lingvano.com`. |
| **Help center** | **Freshworks (Freshdesk)** | URL pattern `help-asl.lingvano.com/support/solutions/articles/...` is the Freshdesk default. Confirmed. |
| **Payments** | Apple IAP + Google Play Billing on mobile; separate web checkout (Stripe likely but unconfirmed) | Pricing differs between native IAP and web per typical setup. `UNVERIFIED` — Stripe vs. Paddle vs. other not directly shown. |
| **Auth** | Email/password; social options `UNVERIFIED` | App Store privacy declares email + name collected. |
| **Video delivery** | CDN-hosted MP4/HLS; `UNVERIFIED` provider (Cloudflare Stream / Mux / Bunny / Vimeo all plausible) | App is 88.2 MB install — too small to ship hundreds of lesson videos, so streamed-on-demand is near-certain. |
| **Analytics** | Multi-purpose tracking per App Store privacy disclosure | Data linked to identity includes "Usage Data," "Product Interaction," "Identifiers used to track across apps/websites." Suggests at minimum a product-analytics SDK + an attribution SDK. `UNVERIFIED` which (Mixpanel/Amplitude/Adjust/AppsFlyer all common). |
| **CV / ML** | **None confirmed** | The Sign Mirror does not score or classify. No public mention of on-device or server-side sign recognition. This is a competitive gap, not a parity feature. |
| **Backend hosting** | `UNVERIFIED` | Vienna-based company; no public infra disclosures. |

### Notable tech non-features
- **No on-device sign classification** — confirmed by the Sign Mirror behavior + the user review asking for "video recording for signing verification"
- **No social / multiplayer** — no leaderboards or friends list visible in any screenshot or feature description
- **No offline mode** confirmed — `UNVERIFIED` whether lesson videos are downloadable

---

## 7. Accessibility posture

What's claimed vs. observable:

| Item | Status |
|---|---|
| **WCAG conformance claim** | No explicit AA/AAA claim found in marketing, help center, or App Store metadata. `UNVERIFIED` |
| **Deaf-instructor authenticity** | Strongly emphasized; "all instructors are Deaf and fluent" [eSchoolNews]. Curriculum quality reviewed by Deaf experts [Zero Project]. This is a *deaf-cultural* accessibility win, not a WCAG-technical one. |
| **Captions on instructor video** | Not explicitly stated. Since the app is described as soundless ("no sound used during lessons" per App Store), the captioning question shifts to *text glosses for signs* — which the app does provide as the answer choices in MCQs. |
| **Adjustable playback speed** | Yes — turtle icon for slow-mo, on every exercise [Top Consumer Reviews] |
| **Multiple input modalities** | Tap-only for non-mirror exercises (no keyboard nav documented); camera-required for Sign Mirror |
| **Color + icon pairing on feedback** | Implied (correct/wrong both shown), not explicitly verified |
| **Reduced motion** | `UNVERIFIED` — streak ignition is animated; whether `prefers-reduced-motion` is honored is unknown |
| **Screen reader / VoiceOver** | `UNVERIFIED` — no claims, no third-party audits found |
| **Sign-language-as-UI** (signed UI navigation, signed onboarding) | Not implemented in available screenshots; UI is English text + mascot |
| **Zero Project recognition** | Profiled as an accessibility project in 2024 — but profile celebrates *expanding sign-language fluency in hearing learners*, not technical app a11y per se [Zero Project] |

**Net read**: Lingvano's accessibility narrative is built on Deaf-led pedagogy and Deaf-culture content rather than WCAG-technical conformance. They are clearly thoughtful about Deaf users as *teachers* but the app's UX is built primarily for hearing learners.

---

## 8. Notable differentiators

Things Lingvano does that few or no competitors do:

1. **All instruction by Deaf native signers** — consistent across ASL, BSL, ÖGS courses. Lingvano employs them on staff (not contractor-only). Marketed heavily; appears in App Store copy, blog, every review. Hard to clone without payroll commitment.
2. **Three sign languages in one app** — ASL, BSL, ÖGS in a unified product is unusual; most competitors specialize in one. (Pricing reflects this: BSL premium is $19.99/mo vs. $17.99 for ASL.)
3. **"Mano" mascot-driven onboarding** — a hand-shaped character that personifies the assistant role across language picking, motivation survey, trial timeline [ScreensDesign]. Branding+pedagogy fusion that's specific to a sign-language product (the mascot itself is a hand).
4. **Curiosities (collectible Deaf-culture facts)** — turns Deaf culture content into a gamification loop rather than separating "fun facts" into a sidebar. Reinforces cultural literacy as a first-class achievement axis.
5. **Streak freeze that you *collect* rather than buy** — versus Duolingo's purchasable freezes. Removes a friction point and a paywall, while preserving the engagement mechanic. [URL: `/streak/freeze-collected`]
6. **Trial timeline visualization on the paywall** — explicitly shows day 5 reminder + day 7 charge dates on a visual timeline. Builds trust at the point of payment friction — ScreensDesign specifically called this out as a "Clear Trial Expectations" UX highlight.
7. **Soft paywall, not hard** — credit card is not required to sign up; users can preview a few lessons before being asked to pay [help center]. Lower-friction than competitors that gate at sign-up.
8. **Mirror with no scoring is *honest*** — they don't pretend to grade you. This is conservative compared to competitors that fake feedback, but possibly defensible vs. the kind of false-positive scoring that erodes trust. (Conversely, it's also a major gap our app can claim to fill.)
9. **Self-funded, no VC** — 2.5M+ learners without outside investment [eSchoolNews]. Pricing power is real; they can hold $17.99/mo because they don't need land-grab growth.

---

## 9. Open questions / could not verify

1. **Exact unit/chapter/lesson counts** — "8 units, hundreds of lessons" is the public number but the actual ASL course structure is unclear without authenticated access.
2. **Sign Mirror layout** — split-screen vs. sequential; mirrored vs. raw camera; whether it ever appears in chapter quizzes or only in lessons.
3. **Vocab Trainer algorithm** — "smart" / "adaptive" per help center, but is it true SRS (SM-2 / FSRS) or simpler weakness-prioritized?
4. **Free tier scope** — "a few lessons" is the only public quantifier; whether free users see chapter quizzes, the dictionary preview, or the mirror at all is unconfirmed.
5. **Exact microcopy** for: correct/incorrect feedback, lesson-complete celebration, streak ignition narration, permission-priming string.
6. **Tech stack specifics**: mobile framework (native vs. RN/Flutter), web app framework, payments processor, analytics stack — all behind WAF + binary opacity.
7. **CV roadmap** — whether Lingvano has internal R&D toward camera-based sign grading. No public signals (no job postings reviewed, no engineering blog posts found).
8. **Streak freeze acquisition rules** — how freezes are earned/granted is implied but not documented.
9. **Accessibility audits** — no public VPAT, no axe/Lighthouse scores, no WCAG conformance statement found.
10. **Course completion outcome** — what happens after the last lesson? Certificate? Continuation? `UNVERIFIED`.
11. **Multi-device sync** — implied (web + iOS + Android share an account) but the exact sync model is undocumented.
12. **Sign-language input modality outside Mirror** — is there ever a moment in a quiz where the user must *sign* rather than tap? Available evidence says no. Worth a follow-up.

---

## Comparison takeaways vs. our spec (informal)

Where Lingvano is ahead:
- Native mobile presence + 3M-user brand + Deaf-instructor depth
- More exercise variety (MCQ + fill-blank + true/false + matching) than our drill-only loop
- Mature gamification (named awards, curiosities, streak freeze collection)
- Three sign languages on one product
- Refined onboarding (Mano mascot, trial timeline, soft paywall)

Where our spec wins:
- **Actual CV-graded practice** vs. their unscored self-mirror — the single largest differentiator we can claim
- Parameter-level drill decomposition (handshape/movement/sign) — pedagogically richer than their MCQ-heavy loop
- Privacy framing (frames stay on device) — defensible against their server-analytics-heavy posture
- College-targeted, ad-light, non-cutesy UI — opposite of Mano-mascot vibe
- FERPA-aware data posture if institutional pilot pursued

Where we're at parity / need to think harder:
- Lesson structure: their Unit > Chapter > Lesson > Exercise is one level deeper than our Course > Lesson > Sign > Drill > Rep. We may want a "Unit" container above Lesson for thematic grouping.
- Vocab Trainer / adaptive review: we don't have this in v1 but Lingvano clearly does
- Dictionary: we don't have an outside-of-lessons lookup; they do, premium-gated
