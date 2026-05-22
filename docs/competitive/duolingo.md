# Competitive UX Teardown — Duolingo

Source product: **duolingo.com** + iOS/Android apps, current as of mid-2025 / early-2026 product state. Purpose: inventory page-level features and engagement mechanics so we can borrow what works and avoid what doesn't for an ASL vocabulary app. Duolingo doesn't teach ASL, but it defines the category's engagement patterns.

Citation note: every claim links to a URL. Anything marked `UNVERIFIED` is product folklore I couldn't pin to a primary source in this pass. "Duolingo says" = first-party marketing or eng blog; "evidence shows" = third-party teardowns or aggregated user reports.

---

## 1. Naming hierarchy

| Level | Name | Notes |
|---|---|---|
| Top container | **Course** | One language pair (e.g., "Spanish for English speakers"). Spanish has ~230 units across 9 sections. ([duolingoguides.com](https://duolingoguides.com/how-many-sections-in-duolingo/)) |
| Course bucket | **Section** | 3–9 per course; typically aligned to CEFR (A1, A2, B1, B2…). English now has sections through B2. ([blog.duolingo.com — How Duolingo teaches English](https://blog.duolingo.com/how-duolingo-teaches-english/)) |
| Section bucket | **Unit** | Themed (food, travel, past tense). Each unit ends with a unit review. Legendary status is now per-unit, not per-skill. ([blog.duolingo.com — Home Screen Redesign](https://blog.duolingo.com/new-duolingo-home-screen-design/)) |
| Unit step | **Level** (the "node" on the path) | A circle on the path. Standard levels contain a series of lessons; review/story/radio/roleplay nodes contain one. ([duoplanet.com](https://duoplanet.com/duolingo-learning-path/)) |
| Atomic playable | **Lesson** | ~5–10 minutes; up to ~17 exercises. ([duoplanet.com](https://duoplanet.com/duolingo-learning-path/)) |
| Inside a lesson | **Exercise** (a.k.a. "challenge" internally) | Tap-what-you-hear, type-what-you-hear, translate, select-image, etc. ([duolingo.fandom.com — Exercise](https://duolingo.fandom.com/wiki/Exercise)) |

Hierarchy: `Course > Section > Unit > Level (node) > Lesson > Exercise`. The 2022 "Path" redesign collapsed the old free-roam skill tree into a single linear path; users can no longer pick which skill to drill next. ([blog.duolingo.com](https://blog.duolingo.com/new-duolingo-home-screen-design/))

---

## 2. Page inventory

| # | Screen | Purpose |
|---|---|---|
| 1 | Marketing landing (duolingo.com) | Public; sign-up funnel, language picker |
| 2 | Sign-up flow | Email / Google / Apple / Facebook; course-first onboarding (pick language before account) |
| 3 | Sign-in | Returning users; "Forgot password" |
| 4 | Onboarding: course picker | "I want to learn…" carousel |
| 5 | Onboarding: motivation picker | "Why are you learning?" (travel, school, family, brain training…) |
| 6 | Onboarding: daily goal picker | 5 / 10 / 15 / 20 min/day "Casual" → "Insane" |
| 7 | Onboarding: placement quiz (optional) | Skips ahead in path if you test in |
| 8 | Onboarding: notification permission | OS-level + Duolingo-styled value pitch |
| 9 | Onboarding: first lesson | One-shot, gives early XP & sets endowed-progress |
| 10 | **Home / Path** | The big one. Vertical scrolling "path" of level nodes for the current unit |
| 11 | Section overview | Shows all units in current section, jump to past units |
| 12 | Unit guidebook | Per-unit "Tips & Notes" page (grammar refs, key phrases) |
| 13 | Level start splash | "Level 1 of 5" preview before lesson begins |
| 14 | **Lesson / Practice screen** | Exercise-by-exercise gameplay (see deep dive) |
| 15 | Mid-lesson "Lesson failed" | When energy/hearts hit zero before finishing |
| 16 | Post-lesson results | XP earned + accuracy + speed + combo |
| 17 | Streak / goal celebration | Animated overlay after results |
| 18 | League tab | Weekly leaderboard, 30 users, current league badge |
| 19 | Quests tab | Today's daily quests + Friend Quests + monthly badge |
| 20 | Profile (self) | Streak, XP, achievements, friends, leagues history |
| 21 | Profile (other user) | Public profile, follow, send Friend Streak invite |
| 22 | Friends / Find friends | Contacts import, suggested, friend streak management |
| 23 | Shop | Streak Freeze, energy refills, Streak Repair, XP boost, outfits for Duo |
| 24 | Super / Max paywall | Subscription upsell |
| 25 | Settings (account, notifications, social, learning, app icon) | Standard settings tree |
| 26 | Duolingo Max: Video Call | Real-time AI character call (Lily) |
| 27 | Duolingo Max: Roleplay | Scenario chat with AI character |
| 28 | Duolingo Max: Explain My Answer | Post-exercise chatbot grammar explainer (now free as of Jan 2026, per [duoplanet.com](https://duoplanet.com/duolingo-max-review/)) |
| 29 | Stories | Bite-sized narrative reading w/ tap-to-translate |
| 30 | DuoRadio | Listening practice (podcast-style); no transcript ([applevis.com](https://www.applevis.com/forum/ios-ipados/duo-lingo-accessible-voiceover)) |
| 31 | Adventures | Choose-your-own-adventure interactive scenes |
| 32 | Chess (separate course) | Launched 2025, has its own path ([investors.duolingo.com](https://investors.duolingo.com/news-releases/news-release-details/duolingo-unveils-major-product-updates-turn-learning-real-world)) |

---

## 3. Per-page feature lists (selected — full enumeration would be 6k words)

### Home / Path (the central screen)
- Vertical scroll of "level nodes" — circular buttons connected by a snaking path
- Sticky header: streak flame (tap → streak detail), gem count, current league badge, hearts/energy icon
- Path nodes have 5 visual states: locked (gray), unlocked (colored), in-progress (partially filled), completed (checkmarked, "crown" level shown), legendary (purple/star)
- Unit headers as full-width banners between unit sections; "Jump here?" affordance for users who think they know the material
- "Character" nodes anchor key story moments (Lily, Oscar, Bea, Eddy, Junior, Falstaff, Duo, Vikram, Lin, Lucy, Zari) — drives the personality layer
- Floating mascot Duo at top-center on idle; he reacts to taps
- Bottom tab bar: Learn / Sounds (DuoRadio) / Quests / Leagues / Profile (varies by A/B and course)
- Right-rail (web only): leaderboard preview, daily quests, friend streak status

### Lesson / Practice screen
See section 4 deep dive.

### League tab
- Top: division banner (e.g., "Gold League"), week countdown ("4d 22h left"), promotion/demotion zone markers
- Ranked list of 30 users with XP, avatar, today's gain
- Tap any user → public profile + follow button
- Demoted users get a "League Repair" upsell (gem cost) to climb back ([duolingo.deconstructoroffun.com — leagues](https://duolingo.deconstructoroffun.com/mechanics/leagues))

### Quests tab
- Today's daily quests (3): bronze chest, silver chest, gold chest by escalating difficulty ([duolingoguides.com — quests](https://duolingoguides.com/what-is-a-quest-in-duolingo/))
- "Open chest" interaction → confetti + gem/XP-boost reveal
- Friend Quests (with friends; shared progress bars)
- Monthly badge progress + leaderboard

### Shop
- Streak Freeze (gem cost; max 2 owned at once; +3 bonus at 100-day streak per [duolingo.fandom.com — Streak](https://duolingo.fandom.com/wiki/Streak))
- Heart refill / Energy refill
- Streak Repair (revive a broken streak; gem or USD)
- XP Boost (15-minute 2× XP)
- Timed Boost (in-lesson power-up)
- Duo outfits, profile customizations

---

## 4. Lesson / Practice screen — deep dive

### State machine for one lesson

```
LESSON_INTRO_SPLASH
  └─ "Lesson 1 of 5" overlay + speech bubble character intro (~1.5s)
LESSON_RUNNING (energy/hearts visible top-right; progress bar top)
  └─ for each Exercise (5–17 per lesson):
       EXERCISE_PROMPT
         ├─ exercise types: translate, tap-what-you-hear, type-what-you-hear,
         │  select-image, complete-the-translation, listen-and-select,
         │  speak-this-sentence, match-pairs, story-fill-in, ...
         │  ([duolingo.fandom.com — Exercise](https://duolingo.fandom.com/wiki/Exercise))
         └─ user input (tap word bank, type, mic, drag-match)
       CHECK_BUTTON_TAPPED  ("CHECK" appears active when input is non-empty)
       RESULT_BAND          (slides up from bottom; green = correct, red = incorrect)
         ├─ correct → "Nice!" / "Amazing!" / "You're on fire!" / "Correct solution: …"
         │              + audio chime + ~600ms hold
         └─ incorrect → "Correct solution: …" + reason chip + "Continue"
            ├─ heart decrement animation (legacy) OR
            ├─ energy decrement (new system; even correct answers cost energy)
            └─ "Explain My Answer" chatbot button (Max-only originally; free since 2026)
       CONTINUE → next exercise, or out
LESSON_END_BRANCH
  ├─ if energy/hearts hit 0 mid-lesson → LESSON_FAILED screen
  │     ("Lesson failed" / "Out of energy" / "Out of hearts")
  │     Options: refill via gems, refill via rewarded ad, "Practice for free" link,
  │     Super/Max upsell card, "Try again later"
  └─ if completed → RESULTS_SEQUENCE
RESULTS_SEQUENCE (3 separate full-screen overlays in sequence — felt as one)
  1. XP earned card     (number animates up; "X XP" + base + combo bonus + boost)
  2. Accuracy / Speed   ("Amazing!" / "Good" / "Try again"; % accuracy + duration)
  3. Daily goal ring    (today's progress vs. 10/20/30/50 XP goal)
  → optional: streak increment, league rank-change, friend streak tick,
              daily quest completion chest, "open chest" interaction
HOME (back to Path; next level node now highlighted)
```

References: aggregated from [duolingoguides.com — XP](https://duolingoguides.com/what-is-xp-in-duolingo/), [duolingo.fandom.com — Combo bonus](https://duolingo.fandom.com/wiki/Combo_bonus), [duoplanet.com — XP guide](https://duoplanet.com/duolingo-xp-guide/).

### ASCII wireframe (mobile)

```
┌──────────────────────────────┐
│ [←]  ████████░░░░░░░  ♥♥♥♥♥ │  ← progress bar, hearts/energy
│       6 of 17                │
├──────────────────────────────┤
│                              │
│   Lily 🗨  Translate this:    │
│   ┌────────────────────┐     │
│   │ ¿Dónde está el     │     │
│   │  baño?             │     │
│   └────────────────────┘     │
│      🔊  (autoplay)          │
│                              │
│   ┌──────────────────────┐   │
│   │ Where is the bath… │   │   ← tap area / type input
│   └──────────────────────┘   │
│                              │
│   [where] [bathroom] [is]    │
│   [the]   [where ]  [pizza]  │   ← word bank
│                              │
├──────────────────────────────┤
│   [SKIP]            [CHECK]  │   ← CTAs always at bottom
└──────────────────────────────┘

After CHECK:
┌──────────────────────────────┐
│      (rest of lesson UI)     │
│                              │
├──────────────────────────────┤
│ ✅ Nice!                     │
│                              │
│ Why?  [Explain My Answer →]  │
│                              │
│              [CONTINUE]      │
└──────────────────────────────┘
(or red band: ❌ Correct: "Where is the bathroom?"
 with "Continue" — no retry; you just lose a heart/energy)
```

### Hearts → Energy: the 2025 switch (load-bearing)

- **Old (pre-July 2025)**: 5 hearts. Lose one per wrong answer. Refill via gems, rewarded ad, "practice to earn back" lessons, or wait ~5 hours per heart. Super removes the limit entirely. ([duolingo.fandom.com — Hearts](https://duolingo.fandom.com/wiki/Hearts))
- **New (rolling out July 2025, broader at Duocon Sept 2025)**: **Energy.** 25 units. Depletes per **exercise**, not per mistake. Regenerates faster when you get streaks of correct answers in-lesson. Reviewing mistakes at lesson end doesn't cost energy. Recharges fully "in about a day." ([blog.duolingo.com — duolingo-energy](https://blog.duolingo.com/duolingo-energy/))
- **User reaction**: overwhelmingly negative. Reddit users report running out mid-third-lesson on a clean run; framed as "punished for using the app." ([classcentral.com](https://www.classcentral.com/report/duolingo-breaks-hearts-for-energy/), [androidauthority.com](https://www.androidauthority.com/quitting-duolingo-energy-system-3599842/), [medium.com — Sam Liberty teardown](https://medium.com/design-bootcamp/how-duolingos-new-energy-system-is-failing-its-users-16738c83117b))
- **Web (desktop)**: hearts/energy historically have not been enforced on the web. Users explicitly route through desktop to get "unlimited hearts" free. ([duolingoguides.com](https://duolingoguides.com/duolingo-unlimited-hearts-guide-2025/))

### Streak system

- One streak per account, not per course. Maintained by completing at least one lesson per local day. ([duolingo.fandom.com — Streak](https://duolingo.fandom.com/wiki/Streak))
- **Streak Freeze**: auto-applies at midnight when you miss a day, IF you own one. Hold up to 2 (5 after 100-day streak). Each protects exactly one missed day. ([duoplanet.com — streak freeze](https://duoplanet.com/duolingo-streak-freeze/))
- **Super auto-apply**: Super subscribers get an auto-purchase-and-apply on missed days, provided they have gems. ([lingoly.io](https://lingoly.io/freeze-duolingo-streak-week/))
- **Streak Repair**: paid revival after the streak breaks (gems or USD).
- **Friend Streak** (launched 2024): up to 5 separate shared streaks with friends; either party missing a day breaks that specific friend streak. Users with one+ friend streak are 22% more likely to complete a daily lesson. ([blog.duolingo.com — Friend Streak](https://blog.duolingo.com/friend-streak/), [blog.duolingo.com — engineering](https://blog.duolingo.com/product-lessons-friend-streak/))
- **"10 PM Streak Saver"**: dedicated late-evening push if you haven't practiced. Categorized as a "save notif" in their two-slot model. ([duolingo.deconstructoroffun.com — notifications](https://duolingo.deconstructoroffun.com/mechanics/notifications))

---

## 5. Engagement mechanics — full inventory

| Mechanic | What it is | Source |
|---|---|---|
| **Streak (account-level)** | Daily lesson cadence | [duolingo.fandom.com](https://duolingo.fandom.com/wiki/Streak) |
| **Streak Freeze (auto)** | Skip a day, free if owned | [duoplanet.com](https://duoplanet.com/duolingo-streak-freeze/) |
| **Streak Repair** | Pay to revive | [lingoly.io](https://lingoly.io/repair-duolingo-streak/) |
| **Friend Streak (×5)** | Shared streak with each of up to 5 friends | [blog.duolingo.com](https://blog.duolingo.com/friend-streak/) |
| **Hearts (legacy)** | 5 mistakes before lockout | [duolingo.fandom.com](https://duolingo.fandom.com/wiki/Hearts) |
| **Energy (current)** | 25 units, deplete per exercise | [blog.duolingo.com](https://blog.duolingo.com/duolingo-energy/) |
| **XP** | Per lesson + combo bonus (up to +5) + XP Boost (2× for 15 min) | [duoplanet.com](https://duoplanet.com/duolingo-xp-guide/), [duolingo.fandom.com — Combo](https://duolingo.fandom.com/wiki/Combo_bonus) |
| **Gems** | Currency from chests/quests; spent on streak freeze, hearts, repair, outfits | [duolingoguides.com](https://duolingoguides.com/what-is-a-quest-in-duolingo/) |
| **Daily Quests (×3)** | Bronze/silver/gold chest; +20–50 XP per quest; complete-all bonus chest | [duolingo.deconstructoroffun.com / duolingoguides.com](https://duolingoguides.com/what-is-a-quest-in-duolingo/) |
| **Friend Quests** | Shared progress bar | [duolingoguides.com](https://duolingoguides.com/what-is-a-quest-in-duolingo/) |
| **Monthly Badges** | Earn for hitting monthly XP threshold | [duolingo.deconstructoroffun.com](https://duolingo.deconstructoroffun.com/mechanics/notifications) |
| **Leagues (10 divisions)** | Bronze → Diamond, 30-user weekly cohorts, ranked by XP | [blog.duolingo.com — leagues](https://blog.duolingo.com/duolingo-leagues-leaderboards/) |
| **Diamond Tournament** | Top-10-of-Diamond monthly bracket (QF/SF/F) | [blog.duolingo.com](https://blog.duolingo.com/duolingo-leagues-leaderboards/) |
| **Legendary level** | Mastery overlay, applied per unit since 2022 | [blog.duolingo.com — home redesign](https://blog.duolingo.com/new-duolingo-home-screen-design/) |
| **Super Duolingo** | No ads, unlimited hearts/energy, mistakes review, streak auto-repair | [alphes-corner.com](https://alphes-corner.com/2025/06/05/i-tried-super-duolingo-and-here-is-what-i-think-is-super-duolingo-worth-it/) |
| **Duolingo Max** | Super + Video Call, Roleplay, Explain My Answer (now free), ~$14/mo or $168/yr | [blog.duolingo.com — max](https://blog.duolingo.com/duolingo-max/), [duoplanet.com](https://duoplanet.com/duolingo-max-review/) |
| **Notifications (two-slot)** | Routine (habit-window) + Save (loss-imminent); max 2/day; multi-armed-bandit personality rotation | [duolingo.deconstructoroffun.com](https://duolingo.deconstructoroffun.com/mechanics/notifications) |

### CV grading — verification

They do **not** computer-vision-grade anything user-produced. Speaking exercises use ASR (Apple/Google native + their own); writing is exact-string or fuzzy-match against acceptable-answer lists; Video Call uses GPT-4 + ASR. Confirmed by absence of any CV claims across the engineering blog and product announcements; speech tooling discussed in [blog.duolingo.com — duolingo-max](https://blog.duolingo.com/duolingo-max/).

---

## 6. Microcopy bank — real strings observed

Aggregated from third-party teardowns, Duolingo blog excerpts, and notification analyses. Where a specific source captured the string, it's cited.

### Lesson result strings
- "Nice!"
- "Amazing!"
- "You got a hard one right!" — `UNVERIFIED specific wording` but referenced in countless teardowns; canonical pattern is praise on a low-success-probability exercise
- "Correct solution: …" (red band on incorrect)
- "You're on fire!" — appears on streak callouts and notifications ([duolingo.deconstructoroffun.com](https://duolingo.deconstructoroffun.com/mechanics/notifications))
- "Lesson complete" / "Practice complete"
- "Lesson failed" / "Out of hearts" / "Out of energy"

### Streak / save copy
- "You're SO close to a 75 day streak" (push) ([duolingo.deconstructoroffun.com](https://duolingo.deconstructoroffun.com/mechanics/notifications))
- "It would be a bummer to lose that 36 day streak. Just saying." — Lily, push ([same](https://duolingo.deconstructoroffun.com/mechanics/notifications))
- "Your 36 day streak ends in 10 minutes. One lesson saves it." — 10pm save push ([same](https://duolingo.deconstructoroffun.com/mechanics/notifications))
- "Streak Saver" / "Streak Repair" (shop)
- "Continue your 109-day Spanish streak on Duolingo" — habit push ([medium.com — notification algorithm](https://medium.com/@jakemazurkiewicz6/how-i-re-created-duolingos-famous-notification-algorithm-00fce580b84e))

### League copy
- "You're out of the top 5 😢 Don't give up! Keep practicing." ([duolingo.deconstructoroffun.com](https://duolingo.deconstructoroffun.com/mechanics/notifications))
- "Miller Johnson took your spot… #3 should be yours!" ([same](https://duolingo.deconstructoroffun.com/mechanics/notifications))
- "Top 10 qualify for the Tournament" ([blog.duolingo.com — leagues](https://blog.duolingo.com/duolingo-leagues-leaderboards/))
- "The next Tournament is starting soon" ([same](https://blog.duolingo.com/duolingo-leagues-leaderboards/))

### Character / brand voice (push)
- "Dear diary, my apprentice is ignoring me. AGAIN." — Oscar ([duolingo.deconstructoroffun.com](https://duolingo.deconstructoroffun.com/mechanics/notifications))
- "Hi, it's Duo. Be a lot cooler if you did…" — Duo ([same](https://duolingo.deconstructoroffun.com/mechanics/notifications))
- "asdfghjkl OUR STREAK" — Braxton ([same](https://duolingo.deconstructoroffun.com/mechanics/notifications))

### Monthly badge
- "Get back on track for your monthly badge" ([same](https://duolingo.deconstructoroffun.com/mechanics/notifications))
- "4 days left to earn September's badge. One lesson keeps it alive." ([same](https://duolingo.deconstructoroffun.com/mechanics/notifications))
- "🥉 Duo's got a prize for you. Congrats on getting bronze!" ([same](https://duolingo.deconstructoroffun.com/mechanics/notifications))

### Max upsell copy
- "AI and education make a great duo" ([blog.duolingo.com — max](https://blog.duolingo.com/duolingo-max/))
- "A new way to Max-imize your learning" ([same](https://blog.duolingo.com/duolingo-max/))

---

## 7. Tech stack (inferred)

| Layer | Choice | Evidence |
|---|---|---|
| Mobile | React Native + native bridges (Swift on iOS, Java/Kotlin on Android) | [duolingoguides.com — React Native](https://duolingoguides.com/does-duolingo-use-react-native/) |
| Web | React + TypeScript + Next.js + Tailwind + Zustand | [duolingoguides.com — React](https://duolingoguides.com/does-duolingo-use-react/) (3rd-party inference; treat as `LIKELY` not authoritative) |
| Core backend / Session Generator | Originally Python, rewritten in **Scala** on the JVM; 98% latency reduction (750ms → 14ms) | [blog.duolingo.com — Scala rewrite](https://blog.duolingo.com/rewriting-duolingos-engine-in-scala/) |
| Other backend | Python services + Java services | [duolingoguides.com](https://duolingoguides.com/does-duolingo-use-react-native/) |
| Data | PostgreSQL + DynamoDB + S3 | [duolingoguides.com](https://duolingoguides.com/does-duolingo-use-react-native/) |
| Infra | AWS (Elastic Beanstalk historically); also some EKS / SageMaker for ML pipelines `UNVERIFIED current orchestrator` | [himalayas.app](https://himalayas.app/companies/duolingo/tech-stack) |
| AI features | OpenAI GPT-4 for Max (Explain My Answer, Roleplay, Video Call) | [blog.duolingo.com — max](https://blog.duolingo.com/duolingo-max/) |
| ASR / TTS | Vendor mix; speech recognition in-app for speaking exercises, TTS for prompts | `UNVERIFIED specific vendor` |
| Pylon (note from research prompt) | I could not find a public confirmation Duolingo uses Pylon (HelpScout/Pylon support tooling). `UNVERIFIED — listing as inferred at best`. |
| Telemetry | Custom event pipeline feeding the leagues/notifications multi-armed-bandit system | Implied by [duolingo.deconstructoroffun.com — notifications](https://duolingo.deconstructoroffun.com/mechanics/notifications) but exact stack `UNVERIFIED` |
| Personalization | Birdbrain (their adaptive item-selection model) drives lesson item ordering | Frequently referenced on the blog and research site; treat as `BACKGROUND` since not directly tied to a UI page here |

---

## 8. Accessibility posture

### What Duolingo says
- They publish an [accessibility help page](https://blog.duolingo.com/) (per-feature notes scattered across blog and help center; no single public conformance statement located in this pass — `UNVERIFIED whether a formal VPAT exists publicly`).
- Speaking exercises offer skip / mic-off toggles per session.
- Listening exercises offer "🐢 slower" replay.

### What evidence shows
- Blind/low-vision users on AppleVis report inconsistent VoiceOver labeling, unlabeled images, exercise audio colliding with screen-reader narration with no mute, and a "screen after completing a lesson" specifically called out as hard to navigate. ([applevis.com](https://www.applevis.com/forum/ios-ipados/duo-lingo-accessible-voiceover))
- DuoRadio (audio podcasts) ships **without transcripts** — fully inaccessible to deaf/HoH learners and to any learner who relies on text. ([applevis.com](https://www.applevis.com/forum/ios-ipados/accessibility-duolingo))
- Recurring complaints about color-only state encoding (red/green result band carries the only signal in many places), text scaling, and contrast on heart/energy iconography. ([medium.com — Wendy Li](https://medium.com/@wndyli/reimagining-duolingo-a-non-visual-approach-to-language-learning-728e4e8733f9), [duolingoguides.com](https://duolingoguides.com/is-duolingo-accessible-features-for-all-users/))
- Reduced-motion: animation density (confetti, mascot bounces, chest opens, league reveals) is high; whether `prefers-reduced-motion` is honored end-to-end is `UNVERIFIED`.

**Bottom line**: Duolingo is broadly usable for sighted learners with motor accommodations but is not a WCAG 2.2 AA reference implementation, particularly for screen readers and audio-only content. For an ASL app whose audience explicitly includes Deaf/HoH learners, this is a non-negotiable area to **exceed**, not match.

---

## 9. Notable patterns — STEAL vs AVOID

### STEAL

- **Endowed progress on day one.** First lesson gives XP, increments streak to 1, fills the goal ring. We already mirror this with our 1/75-already-mastered tutorial — keep that. ([blog.duolingo.com — home redesign](https://blog.duolingo.com/new-duolingo-home-screen-design/))
- **Notifications as a two-slot system** — routine (habit-window) + save (loss-imminent), cap at 2/day, no broadcasts. The discipline is the design. ([duolingo.deconstructoroffun.com](https://duolingo.deconstructoroffun.com/mechanics/notifications))
- **Streak Freeze auto-apply.** Zero-friction protection of the most prized variable. Match this; don't make learners remember to "use" their freeze.
- **Friend Streak as low-overhead social.** Up to 5 separate dyadic streaks; no global feed, no comparison shame. +22% daily-lesson completion is the goal post. ([blog.duolingo.com — Friend Streak](https://blog.duolingo.com/friend-streak/))
- **30-person leagues, not global rankings.** Winnable by design; no one stares at rank 4,392,118. ([duolingo.deconstructoroffun.com — leagues](https://duolingo.deconstructoroffun.com/mechanics/leagues))
- **Bottom-anchored CHECK / CONTINUE button + result band.** Always the same shape, always the same place — predictable input pattern across every exercise type. Steal the input affordance even though our drills are camera-driven, not tap-driven.
- **Per-unit guidebook** for the why-this-grammar-rule layer. Maps onto our "Help / How It Works" — make ours per-lesson, not buried in a global help page.
- **Birdbrain-style adaptive ordering** of items within a lesson. Our analog: prioritize signs the learner has missed reps on, with spaced repetition. Worth its own architecture doc.
- **Combo bonus on a streak of correct answers in-lesson.** Cheap to implement, meaningful felt-reward. Maps to consecutive correct reps in our Sign Drill.
- **Lesson failed screen offers practice-to-recover.** Even users who fail get a non-paywalled path to continue. We should mirror: a failed lesson should always have a "practice the signs you missed for free" exit.

### AVOID

- **Energy depleting per exercise regardless of correctness.** The single biggest UX regression in Duolingo's history; user backlash is brand-shaking. ([androidauthority.com](https://www.androidauthority.com/quitting-duolingo-energy-system-3599842/), [classcentral.com](https://www.classcentral.com/report/duolingo-breaks-hearts-for-energy/)) Don't gate practice volume.
- **Color-only result encoding.** Red/green-only result band fails for color-blind users and screen-reader users. Pair every state with an icon and ARIA label. ([medium.com — Wendy Li](https://medium.com/@wndyli/reimagining-duolingo-a-non-visual-approach-to-language-learning-728e4e8733f9))
- **Mascot guilt-trips in push notifications.** "Dear diary, my apprentice is ignoring me. AGAIN." plays well in TikTok screenshots but is the exact tone college students mock. Our audience is adult learners; the push voice should be informational, not parasocial.
- **Confetti / chest-open / league-reveal animation density.** College/adult-learner audience reads it as condescending. Our spec already calls out "no confetti barf" — hold that line.
- **Bell-curve XP boosts and chest gambling loops.** Manufactured loss aversion and variable-ratio reward design that drives session counts but not learning quality.
- **Audio content without transcripts.** DuoRadio without transcripts is a category fail. For us: caption every reference video, always.
- **Linear-only path with no free-order browse.** The 2022 redesign helped beginners and frustrated power users. ([duoplanet.com — path review](https://duoplanet.com/duolingo-new-learning-path-review/)) Our catalog with free order + sequence hint is the right hybrid.
- **Auto-applied streak freeze with hidden inventory.** Auto-apply is good; what's bad is users not knowing they had a freeze and being confused about why the streak survived. Always show the freeze inventory explicitly.
- **Heart/energy systems on a learning app at all.** We should explicitly ship with no fail-currency. Mistakes are practice. The spec already commits to this.
- **Public leaderboards by default.** Even Duolingo lets you opt out via "Make My Profile Public" toggle — but it's opt-out, not opt-in. Default to off.

---

## 10. Open questions / could not verify

1. **Exact wording of the "You got a hard one right!" string.** Third-party teardowns describe the pattern; I couldn't find a current-app screenshot in this pass. `UNVERIFIED`.
2. **Whether Pylon (the customer-support platform) is part of Duolingo's stack.** Research prompt mentioned it; no public confirmation found. `UNVERIFIED — likely a misattribution`.
3. **Whether `prefers-reduced-motion` is honored across the full app.** No accessibility statement located. `UNVERIFIED`.
4. **Exact promotion thresholds at each league tier.** Multiple third-party sources give slightly different numbers (top-7-of-30, top-10-of-30, top-third); Duolingo's own blog gives ranges. ([blog.duolingo.com](https://blog.duolingo.com/duolingo-leagues-leaderboards/))
5. **Current energy "earn back" mechanics in detail.** Blog post says "regenerates when you answer multiple questions correctly in succession" but doesn't quantify. `UNVERIFIED specifics`.
6. **Whether the desktop web really still bypasses the energy/heart system in 2026.** Sources say yes ([duolingoguides.com](https://duolingoguides.com/duolingo-unlimited-hearts-guide-2025/)) but Duolingo has been closing the gap; status as of mid-2026 is `UNVERIFIED`.
7. **Whether Super still auto-purchases streak freezes for users without gems.** All sources require sufficient gem balance. `UNVERIFIED edge case`.
8. **Per-platform feature parity for Duolingo Max** (Roleplay availability beyond Spanish/French has expanded but exact list per language is fluid). ([duoplanet.com — max review](https://duoplanet.com/duolingo-max-review/))
9. **Whether the lesson-failure screen consistently shows a rewarded-ad path on all platforms** (some users report Super-only refill flows). `UNVERIFIED`.
10. **Whether Friend Streak adoption pattern (57% had ≥1 friend at launch) holds for our likely audience** (a campus pilot with no pre-existing social graph). Mentioned only to flag: don't assume social features carry the same lift outside an existing network. ([blog.duolingo.com — engineering](https://blog.duolingo.com/product-lessons-friend-streak/))

---

## Sources (cumulative)

- [Duolingo Blog — Energy](https://blog.duolingo.com/duolingo-energy/)
- [Duolingo Blog — Leagues & Leaderboards](https://blog.duolingo.com/duolingo-leagues-leaderboards/)
- [Duolingo Blog — Friend Streak (product)](https://blog.duolingo.com/friend-streak/)
- [Duolingo Blog — Friend Streak (engineering)](https://blog.duolingo.com/product-lessons-friend-streak/)
- [Duolingo Blog — Home Screen Redesign](https://blog.duolingo.com/new-duolingo-home-screen-design/)
- [Duolingo Blog — Max launch](https://blog.duolingo.com/duolingo-max/)
- [Duolingo Blog — How Duolingo Teaches English](https://blog.duolingo.com/how-duolingo-teaches-english/)
- [Duolingo Blog — Scala rewrite](https://blog.duolingo.com/rewriting-duolingos-engine-in-scala/)
- [Duolingo Investors — Duocon 2025](https://investors.duolingo.com/news-releases/news-release-details/duolingo-unveils-major-product-updates-turn-learning-real-world)
- [Duolingo Wiki — Streak](https://duolingo.fandom.com/wiki/Streak), [Hearts](https://duolingo.fandom.com/wiki/Hearts), [Energy](https://duolingo.fandom.com/wiki/Energy), [Exercise](https://duolingo.fandom.com/wiki/Exercise), [Combo bonus](https://duolingo.fandom.com/wiki/Combo_bonus), [Streak Freeze](https://duolingo.fandom.com/wiki/Shop/Streak_freeze)
- [Class Central — energy hearts breakdown](https://www.classcentral.com/report/duolingo-breaks-hearts-for-energy/)
- [Android Authority — quitting Duolingo](https://www.androidauthority.com/quitting-duolingo-energy-system-3599842/)
- [Medium — Sam Liberty on energy](https://medium.com/design-bootcamp/how-duolingos-new-energy-system-is-failing-its-users-16738c83117b)
- [Medium — notification algorithm](https://medium.com/@jakemazurkiewicz6/how-i-re-created-duolingos-famous-notification-algorithm-00fce580b84e)
- [Medium — Wendy Li, non-visual Duolingo](https://medium.com/@wndyli/reimagining-duolingo-a-non-visual-approach-to-language-learning-728e4e8733f9)
- [Deconstructor of Fun — Duolingo notifications](https://duolingo.deconstructoroffun.com/mechanics/notifications)
- [Deconstructor of Fun — Duolingo leagues](https://duolingo.deconstructoroffun.com/mechanics/leagues)
- [duoplanet — Learning Path](https://duoplanet.com/duolingo-learning-path/), [streak freeze](https://duoplanet.com/duolingo-streak-freeze/), [Max review](https://duoplanet.com/duolingo-max-review/), [XP guide](https://duoplanet.com/duolingo-xp-guide/), [path review](https://duoplanet.com/duolingo-new-learning-path-review/), [Friend Streaks](https://duoplanet.com/duolingo-friend-streaks/)
- [duolingoguides.com — quests](https://duolingoguides.com/what-is-a-quest-in-duolingo/), [sections](https://duolingoguides.com/how-many-sections-in-duolingo/), [accessibility](https://duolingoguides.com/is-duolingo-accessible-features-for-all-users/), [React Native](https://duolingoguides.com/does-duolingo-use-react-native/), [React](https://duolingoguides.com/does-duolingo-use-react/), [unlimited hearts](https://duolingoguides.com/duolingo-unlimited-hearts-guide-2025/), [XP](https://duolingoguides.com/what-is-xp-in-duolingo/)
- [Lingoly — freeze for a week](https://lingoly.io/freeze-duolingo-streak-week/), [repair streak](https://lingoly.io/repair-duolingo-streak/)
- [AppleVis — VoiceOver thread](https://www.applevis.com/forum/ios-ipados/duo-lingo-accessible-voiceover), [accessibility thread](https://www.applevis.com/forum/ios-ipados/accessibility-duolingo)
- [Himalayas — Duolingo tech stack](https://himalayas.app/companies/duolingo/tech-stack)
- [alphes-corner — Super review](https://alphes-corner.com/2025/06/05/i-tried-super-duolingo-and-here-is-what-i-think-is-super-duolingo-worth-it/)
