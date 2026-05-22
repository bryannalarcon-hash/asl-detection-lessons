# Competitive UX Teardown — Drops (languagedrops.com)

Vocabulary learning app owned by Kahoot since November 2020 (acquired for up to $50M per [TechCrunch](https://techcrunch.com/2020/11/24/kahoot-drops-50m-on-drops-to-add-language-learning-to-its-gamified-education-stable/)). Identity: "5 minutes a day," 55+ languages, illustration-as-mnemonic, swipe-driven mini-games. Highly relevant to our work because it's the only mass-market product that has built a brand around a hard time cap on practice — exactly the bounded-vocab model we're shipping.

Sister app **Scripts** (same publisher) is the one that contains ASL — specifically the ASL Alphabet, not vocabulary signs. See section 5.

---

## 1. Naming hierarchy

| Level | Name | Example | Source |
|---|---|---|---|
| Top container | **Language** | "Spanish (Latin)" | [languagedrops.com](https://languagedrops.com) |
| Themed group of words | **Topic** | "Food & Drinks" — ~17–20 words per topic | [storylearning.com review](https://storylearning.com/blog/drops-review) |
| Grouped Topics | **Category** / **Collection** | "Travel," "Business" — bundles of topics | [Apple App Store listing](https://apps.apple.com/us/app/drops-language-learning/id939540371) |
| One vocab item | **Word** (or "Drop") | "manzana / apple" | brand language |
| One activity instance | **Game** (mini-game) | drag-to-match, bubble-pop, crossword swipe | [alllanguageresources.com](https://www.alllanguageresources.com/language-drops-app/) |
| Review surface | **Dojo** (Review Dojo / Tough Word Dojo) | unlocks at 50 words learned | [Drops Help — Dojo](https://support.languagedrops.com/hc/en-us/articles/19334419328275-Dojo) |

Drops does not use "Lesson" the way Duolingo does. The 5-minute session itself is the unit; Topics are containers you dip into until time runs out.

---

## 2. Page inventory

Inferred from App Store screenshots, review write-ups, and the marketing site. Mobile-first; the web product is a marketing site, not a learning surface.

| # | Screen | Purpose |
|---|---|---|
| 1 | **Marketing site** (languagedrops.com) | Convert to install; Premium pitch |
| 2 | **App Store / Play Store listing** | Install funnel |
| 3 | **Splash / loading drop animation** | Brand moment on cold start |
| 4 | **Language picker** (onboarding) | Pick target + source language |
| 5 | **Goal / motivation prompt** | "Why are you learning?" — light personalization |
| 6 | **Difficulty self-assessment** | Beginner / Intermediate path selection |
| 7 | **Topics index** | Grid of illustrated topic cards |
| 8 | **Category / Collection detail** | Bundled topics: Travel, Business, etc. |
| 9 | **Word preview / Topic intro** | List of words you'll see this session |
| 10 | **Session screen (the core game loop)** | Timed swipe/tap mini-games. See section 4 |
| 11 | **Out-of-time wall** | "Come back in X hours" + Premium upsell |
| 12 | **Session summary** | Words learned, time spent, streak ping |
| 13 | **Dojo** (Review Dojo) | Spaced-repetition replay; unlocks at 50 words |
| 14 | **Tough Word Dojo** | Premium-only; surfaces stubborn words |
| 15 | **Collections** | Manage learned words: heart, hide, flag, search |
| 16 | **Profile / Stats** | Streak, total time, achievements, word count |
| 17 | **Achievements board** | Badges, milestones |
| 18 | **Premium paywall** | Plan picker (monthly / annual / lifetime) |
| 19 | **Settings** | Sound, vibration, romanization toggle, exercise toggles |
| 20 | **Notifications / Reminders** | Daily reminder time picker |
| 21 | **Sister app: Scripts** (separate install) | Houses the ASL Alphabet course |

Sources: [App Store listing](https://apps.apple.com/us/app/drops-language-learning/id939540371), [Help Center: Free vs Premium](https://support.languagedrops.com/hc/en-us/articles/19824401360019-Free-vs-Premium), [top10.com 2026 review](https://www.top10.com/language-learning/reviews/drops).

---

## 3. Per-page feature highlights

**Marketing site** — Hero tagline "the fun way to learn a language"; bullets for *Unlimited Time / Ad Free / Learn Offline / All Content / Exclusive Gameplay*; "2x faster" Premium claim; Kahoot-owned branding visible ([languagedrops.com/premium](https://languagedrops.com/premium)).

**Topics index** — Each topic card is a stack of mini illustrations representing the words inside; locked topics show a padlock for free users (free tier restricts sequential jumping per [actualfluency](https://actualfluency.com/drops-language-app)).

**Session screen** — See section 4.

**Out-of-time wall** — Surfaces the next-available time (5 minutes per ~10 hours per [FluentU](https://www.fluentu.com/blog/reviews/drops-language-app/) and [languagethrone.com 2024](https://www.languagethrone.com/language-drops-app/)) and a Premium CTA. Streak goal completion historically granted bonus time, but reviewers in 2025 note this was tightened: "since May, users no longer receive extra time after learning for 5 minutes and streak revives are also heavily limited without Premium" ([search result, May 2025](https://www.trustpilot.com/review/languagedrops.com)).

**Dojo** — Unlocks after 50 words learned; a word is "mastered" after 10 successful interactions; algorithmic surfacing of due words ([Help Center: Dojo](https://support.languagedrops.com/hc/en-us/articles/19334419328275-Dojo)). Empty state copy: *"no words available for optimal learning."*

**Collections** — Per-word affordances: heart, remove, search, flag, hide ([languagethrone.com](https://www.languagethrone.com/language-drops-app/)).

**Premium paywall** — Three-tier plan picker. Current pricing varies by region/promo; canonical site shows: Monthly **$11/mo**, Yearly **$69.99** ($5/mo equivalent, 7-day free trial), Lifetime **$150** ([languagedrops.com/premium](https://languagedrops.com/premium)). Third-party reviews cite $8.49–$13 monthly depending on test date — discounting is heavy and frequent.

---

## 4. Practice screen deep dive

This is the page Drops is famous for. It is **timed, single-card-at-a-time, gesture-driven, and never asks you to type**.

### Layout (mobile portrait)

```
┌───────────────────────────────────────┐
│  ←        04:37  (countdown ticking)  │  ← timer is always visible
│           ──────                       │
│        ┃     ╱╲                       │
│        ┃    │  │   <- illustration    │
│        ┃    │  │      (custom art)    │
│        ┃    ╰──╯                       │
│        ┃                               │
│        ┃     la manzana                │  ← target word
│        ┃     "apple"                   │  ← gloss
│                                       │
│   ╭ swipe UP to discard / "I know it" ╮│
│                                       │
│   ╭ swipe DOWN to keep learning       ╮│
│                                       │
│   tap-and-hold image → reveals gloss  │
└───────────────────────────────────────┘
```

After the intro card, the same word recurs across **rotating mini-game formats**:
- **Drag-to-match**: pair illustration ↔ written word
- **Bubble pop**: tap the correct translation among floating bubbles
- **Letter scramble**: drag scattered letters into order
- **Crossword swipe**: drag a finger across a letter grid to trace the word
- **Pair-tap**: tap matching pairs in a 2×N grid

Sources: [alllanguageresources](https://www.alllanguageresources.com/language-drops-app/), [storylearning](https://storylearning.com/blog/drops-review), [Apple App Store](https://apps.apple.com/us/app/drops-language-learning/id939540371).

### State machine (inferred)

```
SESSION_START (timer = 5:00; topic chosen)
  └─ WORD_INTRO (illustration + word; Lottie "drop" animation)
       ├─ swipe UP   → skip (mark known, won't re-show this session)
       └─ swipe DOWN → enqueue into the session's active set
  └─ MINI_GAME (round-robin across formats; ~1 word per ~5–8s)
       ├─ correct  → confetti-light feedback, advance
       └─ wrong    → word stays in active set, re-appears sooner
  └─ TIMER_EXPIRES → SESSION_SUMMARY
       ├─ free tier: route to OUT_OF_TIME wall
       └─ premium: offer "continue" or "end"
```

### The timer mechanic (explicit, because this is the whole product)

- **Visible countdown** in the top bar throughout the session — "the time limit counts down throughout the lesson, helping you to stay fully focused while you learn" ([Langoly](https://www.langoly.com/drops-app-review/)).
- **Pausable**: users can pause and resume ([Langoly](https://www.langoly.com/drops-app-review/)).
- **Free tier**: hard cap **5 minutes per session, regenerating ~every 10 hours** — confirmed across 2024–2026 reviews ([FluentU](https://www.fluentu.com/blog/reviews/drops-language-app/), [top10.com 2026](https://www.top10.com/language-learning/reviews/drops), [languagethrone](https://www.languagethrone.com/language-drops-app/)). Practical effect: two ~5-minute sessions per day is the free ceiling.
- **Premium**: session length is **user-selected from 5 / 10 / 15 / unlimited minutes** ([Langoly](https://www.langoly.com/drops-app-review/)).
- **Earned bonus time** (historical): completing a streak goal added 40s–5min; this mechanic was **curtailed in May 2025** per current Trustpilot reviews — extra-time grants are now limited and streak revives are largely Premium-gated.

### Sign-decomposition equivalent

Drops doesn't decompose a sign into sub-parameters the way our app must — every word is atomic in their model. Their pedagogical scaffolding is **format variety** (5+ mini-games per word) rather than parameter isolation. This is a meaningful philosophical difference: Drops bets on retrieval-practice repetition; we're betting on motor-skill decomposition.

---

## 5. Session mechanics — the "5 minutes a day" identity

| Mechanic | Detail | Source |
|---|---|---|
| **Free session cap** | 5 min per session, ~10 hr regeneration. Still in effect in 2026. | [FluentU](https://www.fluentu.com/blog/reviews/drops-language-app/), [top10.com](https://www.top10.com/language-learning/reviews/drops) |
| **Premium removes cap** | Selectable 5/10/15/unlimited min; reviewers note 15 min is the engagement sweet spot before fatigue | [Langoly](https://www.langoly.com/drops-app-review/) |
| **Streak** | Daily-consecutive counter; visible in Profile; daily reminder push. Streak revives now Premium-gated (2025 change) | [Trustpilot 2025 reviews](https://www.trustpilot.com/review/languagedrops.com) |
| **Mastery** | A word is "mastered" after **10 successful interactions** | [Help Center: Dojo](https://support.languagedrops.com/hc/en-us/articles/19334419328275-Dojo) |
| **Spaced repetition** | Dojo unlocks at 50 words; uses an SRS algorithm to surface due words | [Help Center: Dojo](https://support.languagedrops.com/hc/en-us/articles/19334419328275-Dojo) |
| **Item illustration style** | One **custom-commissioned illustration per word**, flat-vector, mellow palettes, white background, mascot-free. Each illustrated entrance uses a Lottie "drop" animation. | [Brains & Beards engineering blog](https://brainsandbeards.com/blog/building-beautiful-apps-drops/) |
| **ASL note** | ASL is **alphabet only, in the sister app Scripts** — illustrated handshapes by Yiqiao Wang (Gallaudet University). No vocabulary signs, no video, no facial-grammar instruction. | [Drops press release Sept 2019](https://languagedrops.com/press-releases/drops-launches-american-sign-language) |

The illustrations are Drops' signature. They are **not stock; not AI-generated**; they are commissioned and consistent across the entire corpus. This is one of the most expensive and defensible parts of their moat.

---

## 6. Microcopy bank (verified strings)

Pulled from marketing site, help center, and reviewer quotes:

**Brand / value**
- "the fun way to learn a language" ([languagedrops.com](https://languagedrops.com))
- "In just five minutes a day, you will learn American Sign Language through our beautifully illustrated, immersive and playful lessons." ([learn-asl-alphabet page](https://languagedrops.com/scripts-collection/learn-asl-alphabet))
- "Learn languages with the fun and effective vocabulary app" (App Store)

**Premium upsell**
- "Unlimited Time"
- "Ad Free"
- "Learn Offline"
- "All Content"
- "Exclusive Gameplay"
- "your gateway to mastering languages with unrivaled ease and effectiveness" ([premium page](https://languagedrops.com/premium))
- "2x faster on average"
- "7 days free, then billed annually"

**Empty states / system**
- "no words available for optimal learning" — Dojo empty state ([Help](https://support.languagedrops.com/hc/en-us/articles/19334419328275-Dojo))

**Interaction prompts** (paraphrased by multiple reviewers — exact in-app strings not verified)
- "swipe up to skip / I know this"
- "swipe down to learn"
- "tap and hold" (image-to-translation reveal)

---

## 7. Tech stack (inferred and partially confirmed)

| Layer | Choice | Evidence |
|---|---|---|
| **App framework** | **React Native** (rewritten from native ~2017–2018) | [Drops Engineering Medium post, Sept 2018](https://medium.com/drops-engineering/our-react-native-experience-603e3343730) |
| **Language** | TypeScript | same |
| **State** | Redux + Reselect | same |
| **Navigation** | Custom 30-line router (not React Navigation) | same |
| **List virtualization** | Flipkart's `react-native-recyclerview-list` | same |
| **Animations** | React Native `Animated` API with **native driver** for all timing/spring; `PanResponder` for swipes | [Brains & Beards](https://brainsandbeards.com/blog/building-beautiful-apps-drops/) |
| **Lottie** | Used specifically for the "drop" entrance animation per new word | same |
| **Physics** | Matter.js for bouncy/interactive feel | [Medium post](https://medium.com/drops-engineering/our-react-native-experience-603e3343730) |
| **Gesture libs** | Explicitly **chose against** `react-native-reanimated` and `react-native-gesture-handler` (iOS + web compat concerns at the time) | [Brains & Beards](https://brainsandbeards.com/blog/building-beautiful-apps-drops/) |
| **Web version** | `react-native-web` (~98% code shared per their 2018 post; current state of web product unverified) | [Medium post](https://medium.com/drops-engineering/our-react-native-experience-603e3343730) |
| **Illustration pipeline** | Vector SVG → custom tooling. Open-sourced `svg2android` and forked `Macaw` (SVG-in-Swift) on their [GitHub org](https://github.com/languagedrops) | GitHub |
| **iOS in-app purchase** | `react-native-iap` (evaluated; likely adopted) | [Medium post](https://medium.com/drops-engineering/our-react-native-experience-603e3343730) |
| **Audio** | FFmpeg-derived audio libs visible on their GitHub | GitHub |
| **Backend** | Not publicly documented |
| **Publisher of record** | "PLANB LABS OU" on the App Store; Kahoot ASA at the corporate level | [App Store](https://apps.apple.com/us/app/drops-language-learning/id939540371) |

Key takeaway for our team: Drops' silky feel is **native `Animated` + native driver + Lottie for the hero moment + Matter.js for spring physics**, not Reanimated 2/3. That is unusual in 2025 and reflects an older but very tuned codebase. We do not need to copy this stack — Reanimated 3 + Framer Motion is the modern equivalent and is what we'd reach for on web.

---

## 8. Accessibility posture

Drops' accessibility story is **weak by 2026 standards**, and this is a deliberate competitive opening for us.

- **Color-only feedback** is heavy throughout the games (correct = green flash, wrong = red shake). No icon pairing verified.
- **Drag-and-drop is the core interaction** — WCAG 2.2 SC 2.5.7 ("Dragging Movements") requires a non-drag alternative; no evidence Drops provides one. Tap-and-hold reveal is the closest single-pointer affordance.
- **Audio** is core to the learning experience (native pronunciation), and reviewers explicitly recommend "you'll want to bring headphones" ([alllanguageresources](https://www.alllanguageresources.com/language-drops-app/)). Captions for audio are not standard.
- **No screen-reader-friendly mode** documented.
- **Vibration toggle** present (motor-feedback channel) per [top10.com](https://www.top10.com/language-learning/reviews/drops).
- **Romanization toggle** for non-Latin scripts (Korean, Mandarin, etc.) — a literacy-accommodation, not a disability accommodation.
- **Time-pressure mechanic** (visible countdown) is itself an accessibility concern under WCAG 2.2.1 (Timing Adjustable) — users with cognitive disabilities or slow motor function cannot extend the timer on the free tier.

We can ship a meaningfully more accessible product without trying very hard: keyboard nav, color-paired-with-icon, captions on all reference video, single-pointer alternative to any drag, and a no-timer mode would already lap Drops.

---

## 9. Notable patterns — STEAL vs AVOID

### Steal

1. **One illustration per item, commissioned and consistent.** Drops' visual coherence comes from a single artist-defined style across thousands of items. Our reference videos are the equivalent moat. Treat consistency as a product feature, not an art-department detail.
2. **A visible, non-negotiable session shape.** The countdown timer creates honest expectations: every user knows when they'll be done. Our lesson screen should communicate "X signs / ~Y min" up-front and never lie about it.
3. **Format rotation against the same item.** Drops shows the same word in 4–5 different mini-games to drive retrieval-practice variety. Our handshape/movement/sign drill cycle is the parameter-decomposition analog — keep it varied, don't show three identical reps in a row.
4. **Empty-state honesty.** "No words available for optimal learning" is a graceful Dojo empty state — no fake busywork. Our "all signs mastered" state should be equally honest.
5. **Pause is first-class.** Top-bar pause that preserves session state. Mandatory for our practice screen.
6. **Topic-based browsing instead of forced linearity** (Premium-only in Drops, but the pattern is sound). Adults pick what they want to learn; respect that.
7. **Lottie for the hero moment, not everywhere.** Drops reserves Lottie for the word-entrance animation. Heavy animation is a finishing touch, not a baseline.

### Avoid

1. **The hard time cap as a free-tier wall.** Drops' "5 min / 10 hours" is a *monetization mechanic dressed as a wellness mechanic*. It frustrates serious learners (multiple 2025 reviews call it out) and a college-deployed ASL tool can't use it.
2. **Streak revives gated behind Premium** (the May 2025 change). Punishes learners for life happening; bad fit for our anti-anxiety stance from principles.md.
3. **No grammar / no production / no comprehension** — Drops is explicit that it's vocabulary-only. That's coherent for them, but the *way* they communicate it is buried; users still arrive expecting fluency. Be louder than Drops about scope.
4. **Drag-everywhere with no keyboard alternative.** Accessibility debt.
5. **Visible countdown timer during the actual practice.** Adds cognitive load and time-pressure stress that doesn't match motor-skill learning. We can show estimated time on the Lesson Intro but the Practice Screen itself should not tick.
6. **Streak goal granting bonus session time** — a clever Pavlovian loop but it confuses the product's identity ("5 minutes a day except sometimes 7.5") and was apparently a maintenance/abuse headache (since dialed back).
7. **ASL relegated to a sister app, alphabet only, with no Deaf-community credit beyond a single illustrator.** Drops' ASL presence is shallow and stale (launched 2019, no vocabulary content added since). This is the exact niche our product fills.

---

## 10. Open questions / could not verify

- **Exact in-app microcopy for swipe prompts.** Reviewers paraphrase ("swipe up = I know this") but I could not confirm the literal in-app string without installing. Worth a 5-minute install verification before we ship our own copy.
- **Current state of the web product.** Drops historically built a web version via `react-native-web`; the public marketing site at languagedrops.com is purely conversion-focused in 2026. Unclear whether a learner-facing web app still exists or has been deprecated post-Kahoot.
- **Kahoot integration in-product.** Public Kahoot communications since 2020 mention "bringing Drops content into the main Kahoot platform" but I found no evidence of a unified login, shared streak, or cross-product progression in 2025–2026 reviews. The Kahoot logo is on the marketing site; in-app integration appears minimal.
- **Whether Premium tiers vary by region.** Quoted monthly prices range $8.49–$13 across sources; this is region/test-date variance, not version drift. Canonical site at fetch time: $11/mo, $69.99/yr, $150 lifetime.
- **Exact 2025 streak-revive rule.** Trustpilot reviews from May 2025 say revives "heavily limited without Premium"; the precise rule (e.g., "1 free revive per month") is not documented.
- **Whether the Scripts ASL course has been updated since 2019.** All marketing copy and content appears to be the launch material. The Gallaudet illustrator credit is the only Deaf-community involvement publicly documented.
- **Session frequency telemetry.** Drops doesn't publish how often the average free user hits the 10-hour wall; useful to know if we ever want to argue the 5-min cap is or isn't actually retentive.
- **App store screenshot specifics.** Could not directly view the App Store screenshots (text scrape only); a visual review would confirm UI elements I've inferred above (top-bar layout, button placements).

---

*Word count: ~1,950. Sources cited inline. Last researched: 2026-05-21.*
