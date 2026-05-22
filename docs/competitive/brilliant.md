# Competitive Teardown — Brilliant.org

Reference for [`ux-spec.md`](../ux-spec.md) and [`principles.md`](../principles.md). Brilliant is the closest non-language analogue to our **effectiveness-first** goal: concept-mastery, interactive-problem-based, "learn by doing." This teardown maps what they do so we can borrow specifically for an adult / college-age audience.

All claims cite URLs. "Brilliant says" (their own copy) is distinguished from "evidence shows" (third-party reviews, design case studies). Items I could not confirm are tagged **UNVERIFIED**.

---

## 1. Naming hierarchy

Brilliant's actual ladder, reverse-engineered from their help center and marketing copy:

| Level | Brilliant's term | Example | Notes |
|---|---|---|---|
| Top container | **Learning Path** | "Foundational Math" | 10 paths exist; curated multi-course sequences ([Help](https://brilliant.org/help/using-brilliant/what-are-learning-paths/)) |
| Subject area | **Course** | "Pre-Algebra", "Visual Algebra", "Calculus" | 40–60+ courses total ([Premium page](https://brilliant.org/premium/), [myelearningworld review](https://myelearningworld.com/brilliant-review/)) |
| Group of related concepts | **Unit** | (a course contains multiple units) | **UNVERIFIED** — implied by "course → lessons" structure but not named explicitly on the marketing site |
| Single concept / ~15 min | **Lesson** | "Negative Exponents" | "lessons broken into ~15-minute segments" ([myelearningworld](https://myelearningworld.com/brilliant-review/)); review notes actual range is 15–45 min |
| One challenge inside a lesson | **Problem** | a single puzzle / quiz / drag-drop | "20+ problems per concept" per their blog ([Brilliant blog](https://blog.brilliant.org/hand-crafted-machine-made/)) |
| Atomic idea inside a problem | **Concept** | "exponent rules" | Used in pedagogy copy but not a UI level |

Hierarchy: `Learning Path > Course > Unit > Lesson > Problem`. The word **Problem** is doing the same work that **Drill** does in our spec — the smallest interactive unit. Their unit of mastery is the **Lesson** ("3 problems or a full lesson" for streak credit per [Help: streaks](https://brilliant.org/help/using-brilliant/what-is-a-streak/)).

Lesson Path naming convention is thematic and concrete (e.g., "Visual Algebra", "Solving Equations", "Probability and Chance") — not numbered ("ASL 1 Lesson 3"). Worth noting for our catalog: concrete > sequential numbering helps free-order browsing.

---

## 2. Page inventory

Distinct screens identified across web + app:

| # | Page | Source |
|---|---|---|
| 1 | Marketing landing | [brilliant.org](https://brilliant.org) |
| 2 | Courses index | [/courses/](https://brilliant.org/courses/) |
| 3 | Learning Paths overview | [Help](https://brilliant.org/help/using-brilliant/what-are-learning-paths/) |
| 4 | Subject hubs (Math, CS, Science, Data, AI) | [/ai/](https://brilliant.org/ai/), [/math/](https://brilliant.org/math/) |
| 5 | Sign-up / Sign-in | inferred standard |
| 6 | Onboarding (pretest / diagnostic) | [About](https://brilliant.org/about/) — "we pretest on the material" |
| 7 | Home / "today" screen with streak + Continue | [Rive](https://rive.app/blog/how-brilliant-org-motivates-learners-with-rive-animations) |
| 8 | Course detail / Level Gameboard | [ustwo](https://ustwo.com/work/brilliant/) |
| 9 | **Lesson screen** | [App Store](https://apps.apple.com/us/app/brilliant-learn-by-doing/id913335252) |
| 10 | Lesson complete / celebration | [ustwo](https://ustwo.com/work/brilliant/) |
| 11 | Daily Challenge | [Help index](https://brilliant.org/help/using-brilliant/) |
| 12 | Leaderboard / League | [Help: leagues](https://brilliant.org/help/using-brilliant/what-are-leagues-and-leaderboards/) |
| 13 | Profile (XP, streak, charges) | [Rive](https://rive.app/blog/how-brilliant-org-motivates-learners-with-rive-animations) |
| 14 | Subscribe / paywall | [/premium/](https://brilliant.org/premium/) |
| 15 | Settings / notifications | inferred |
| 16 | Help Center | [/help/](https://brilliant.org/help/using-brilliant/) |
| 17 | For Educators | [Help: For Educators](https://brilliant.org/help/for-educators/) |

Notably absent vs. Duolingo: no public profile browsing, no friends list, no chat. Social is contained to anonymous 30-person Leagues.

---

## 3. Per-page feature lists (load-bearing only)

**Marketing landing.** Hero: "Interactive problem solving that's effective and fun" + "Learn by doing" tagline. Dual CTA "I'm a learner" / "I'm a parent or teacher". "10 million learners" social proof. Imagery emphasizes manipulable visuals (geometry, gears), not screenshots of text. ([brilliant.org](https://brilliant.org))

**Courses index.** Organized by Learning Path (10) and by subject hub (Math, CS, Science, Data, AI). Free users must progress **sequentially**; premium unlocks jump-ahead — a monetized lever. ([Help: paths](https://brilliant.org/help/using-brilliant/what-are-learning-paths/))

**Home / today screen.** Streak counter with battery-icon streak charges, "Continue last lesson" card, League widget, Daily Challenge tile. ([Rive case study](https://rive.app/blog/how-brilliant-org-motivates-learners-with-rive-animations))

**Level Gameboard (course detail).** Branching-path visualization of lessons. Animated nodes + connecting lines, color-coded by topic. "Learning Companion" character guides to next lesson. Closest analogue to Duolingo's path, minus the punishment loop. ([ustwo](https://ustwo.com/work/brilliant/))

**Premium paywall.** Annual ~$10.83/mo ($129.96/yr); Monthly $24.99; Groups (3+) $299.88/yr; 7-day free trial. Free tier: 2 lessons/day with ads. ([myelearningworld 2025](https://myelearningworld.com/brilliant-review/), [Help index](https://brilliant.org/help/using-brilliant/))

---

## 4. Lesson screen deep dive — the problem-solving loop

This is the equivalent of our Practice Screen.

### Pedagogy as encoded in the UI

Brilliant's about page is explicit: **"We don't teach how to do something before asking questions. Instead, we pretest on the material, letting the learner try to find a solution before learning the procedure."** ([About](https://brilliant.org/about/)). This is **productive failure / pretesting** — the same Kapur-style mechanism we cite in `principles.md`. Their UI is built around it.

### Interactive problem types (evidence-backed)

- **Multiple choice with interactive wrong-answer explanation** — wrong answers spawn manipulable explorations, not static text apologies (Brilliant lesson UI summaries)
- **Drag-and-drop** ([Nibble](https://nibble-app.com/blog/is-brilliant-worth-it), [App Store](https://apps.apple.com/us/app/brilliant-learn-by-doing/id913335252))
- **Manipulable visualizations** — sliders, draggable shapes, real-time-updating curves ([Nibble](https://nibble-app.com/blog/is-brilliant-worth-it))
- **Domain-specific puzzles** — gear-train, circuit-building, grid-world, balance/mobile, logic-ordering ([Brilliant blog](https://blog.brilliant.org/hand-crafted-machine-made/))
- **Free-text / numeric input** — inferred from "instant, custom feedback based on the user's answer"
- **Drag-and-drop coding blocks** — criticized by some users as too constraining

### State machine (inferred from public descriptions)

```
LESSON_START
 └─ PROBLEM_INTRO          (concept primer — often a visual / animation, no instruction text dump)
      └─ PROBLEM_ATTEMPT   (user manipulates / picks / inputs)
           ├─ CORRECT
           │    └─ MICRO-CELEBRATION (Rive animation, +XP float)
           │         └─ next PROBLEM, or LESSON_COMPLETE
           ├─ INCORRECT
           │    └─ INTERACTIVE_EXPLANATION (not just text; manipulable)
           │         └─ RETRY same problem (or skip on some)
           └─ HINT_REQUESTED
                └─ tiered hint reveal (UNVERIFIED — confirmed conceptually, exact UI not)
 └─ LESSON_COMPLETE
      └─ celebration + XP totals + streak update
      └─ "Next lesson" CTA, or back to Level Gameboard
```

### ASCII wireframe (lesson screen, reconstructed from App Store screenshots and ustwo case study)

```
┌─────────────────────────────────────────────────────────────┐
│  ←  Visual Algebra  ·  Lesson 3 / 8        ⏸ pause      ×  │
│  [████████████░░░░░░░░░░░░░░░░░░]  42%                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Which graph matches y = 2x + 1 ?                          │
│                                                             │
│   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│   │   /     │  │     \   │  │   /     │  │  ___    │        │
│   │  /      │  │      \  │  │  /      │  │  ___    │        │
│   │ /       │  │       \ │  │ /       │  │         │        │
│   └─────────┘  └─────────┘  └─────────┘  └─────────┘        │
│      (A)          (B)          (C)          (D)             │
│                                                             │
│   [  ?  hint  ]                              [ Submit ]     │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│   On wrong:                                                 │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  Not quite. Drag the slope dot to see what happens. │   │
│   │     [interactive graph — slider for slope/intercept]│   │
│   │                                                     │   │
│   │     slope:    ●━━━━━━○━━━━━━━━  (2)                 │   │
│   │     intercept: ━━━━○━━━━━━━━━━  (1)                 │   │
│   └─────────────────────────────────────────────────────┘   │
│                                          [ Try again ]      │
└─────────────────────────────────────────────────────────────┘
```

Key differences from a Duolingo lesson screen: **the wrong-answer explanation is itself interactive**, not a static "correct answer: B" panel. This is the operational core of "learn by doing" — failure becomes a manipulable experiment.

### Feedback layering
- Per-problem: instant correct/incorrect, custom to the answer chosen ([Search summary](https://www.google.com/search?q=Brilliant.org+lesson+UI))
- Per-lesson: Rive celebration animation + XP counter that synchronizes with a numerical counter ([Rive case study](https://rive.app/blog/how-brilliant-org-motivates-learners-with-rive-animations))
- Encouragement elements for struggling learners (ustwo named this as a distinct UI component, [ustwo](https://ustwo.com/work/brilliant/)) — UNVERIFIED what exact copy/visuals these use

---

## 5. Pedagogy approach

Brilliant's explicit, repeated framing:

- **"Learn by doing"** — homepage tagline ([brilliant.org](https://brilliant.org))
- **Active over passive** — "active problem solving – a method shown to be far more effective than passive learning like videos or lectures" (Brilliant marketing copy)
- **Pretesting / productive failure** — "We don't teach how to do something before asking questions. Instead, we pretest on the material" ([About](https://brilliant.org/about/))
- **Just-enough scaffolding** — "Brilliant doesn't give you answers – it gives just enough guidance to help you reason through problems yourself"
- **Anti-LLM-tutor stance** — "Text explanations, no matter how perfect, just aren't Brilliant's goal" ([Brilliant blog](https://blog.brilliant.org/hand-crafted-machine-made/))
- **Intrinsic > utilitarian motivation** — "problem solving, like play, is a natural instinct" ([About](https://brilliant.org/about/))

Evidence matches the rhetoric: third parties confirm "Brilliant does not explain concepts at the beginning of the lesson. Starting with puzzles and games, you discover patterns and solutions along the way" ([Nibble](https://nibble-app.com/blog/is-brilliant-worth-it)).

Adult-learner translation: this lines up with `principles.md` — pretest, productive failure, immediate feedback, faded scaffolding. Dramatically closer to our goal than Duolingo's drilled-recognition loop.

---

## 6. Mastery model

Brilliant is **fuzzier than they market** here.

- **Lesson completion** is the primary mastery unit — finishing a Lesson advances the Level Gameboard and counts toward streaks ([Help: streaks](https://brilliant.org/help/using-brilliant/what-is-a-streak/))
- **Practice checkpoints** ("Regular practice checkpoints to test your understanding as you go", [Help: paths](https://brilliant.org/help/using-brilliant/what-are-learning-paths/)) — UNVERIFIED whether checkpoints gate progression
- **Adaptive difficulty** — "tracking mastered concepts and adjusting practice difficulty" ([brilliant.org](https://brilliant.org))
- **Knowledge modeling** — About page mentions "user knowledge modeling" but **no per-concept mastery state surfaces in the UI** (no "Mastered / Familiar / Learning" badges like ours plan)
- **Reset support** — users can reset per-course progress ([Help index](https://brilliant.org/help/using-brilliant/))

Critique: reviewers complain "knowledge is often superficial and doesn't transfer outside the platform" ([Nibble](https://nibble-app.com/blog/is-brilliant-worth-it)). Brilliant treats lesson-completion as a proxy for mastery. **Gap we can outperform**: explicit per-sign mastery state surfaced to the learner.

---

## 7. Engagement mechanics

### They have:
| Mechanic | Detail | Source |
|---|---|---|
| **Streaks** | 3 problems OR 1 lesson per day = +1; miss = reset to 0 | [Help](https://brilliant.org/help/using-brilliant/what-is-a-streak/) |
| **Streak Charges** | Earn 1 per completed lesson; max 2; auto-applied on miss | [Help](https://brilliant.org/help/using-brilliant/what-is-a-streak-charge/) |
| **XP** | Earned for lessons + practice | [Help](https://brilliant.org/help/using-brilliant/what-are-leagues-and-leaderboards/) |
| **Leagues** | 30 learners, 10 tiers (Hydrogen → Einsteinium), **auto-enrolled** weekly | [Help: leagues](https://brilliant.org/help/using-brilliant/what-are-leagues-and-leaderboards/) |
| **Daily Challenge** | Single fresh problem | [Help index](https://brilliant.org/help/using-brilliant/) |
| **Rive celebrations** | Correct-answer animations + XP counter | [Rive](https://rive.app/blog/how-brilliant-org-motivates-learners-with-rive-animations) |
| **Learning Companion** | Character guides to next lesson | [ustwo](https://ustwo.com/work/brilliant/) |

### They avoid:
- **No hearts / lives / failure punishment** — wrong answer has no XP cost, just retry (UNVERIFIED but consistently absent across reviews + docs)
- **No friends list / public profiles** — Leagues are anonymous-ish 30-person buckets, not a social graph
- **No confetti barf** — ustwo's "Play Thinking" balance because "STEM subjects require deep focus" ([ustwo](https://ustwo.com/work/brilliant/))

One App Store reviewer with ADHD complained Brilliant "does the bare minimum" compared to Duolingo ([App Store](https://apps.apple.com/us/app/brilliant-learn-by-doing/id913335252)) — a feature, not a bug, for adult focused learners.

**Gotcha**: Leagues are **auto-opt-in**, no documented opt-out. Their one compromise on restrained-engagement, and an AVOID for us.

---

## 8. Microcopy bank

**Value-prop / mission** — "Learn by doing." · "Interactive problem solving that's effective and fun." · "Step-by-step interactive lessons make even complex ideas feel intuitive." · "Making a world of great problem solvers." ([brilliant.org](https://brilliant.org), [About](https://brilliant.org/about/))

**Pedagogy framing** — "We don't teach how to do something before asking questions." · "Brilliant doesn't give you answers – it gives just enough guidance to help you reason through problems yourself." · "Every course is crafted by human experts – not AI." ([About](https://brilliant.org/about/))

**Streak / engagement** — "Your streak is the number of consecutive days you've learned on Brilliant." · "Streak Charges help you maintain your streak on Brilliant when you miss a day." ([Help](https://brilliant.org/help/using-brilliant/what-is-a-streak/), [Help](https://brilliant.org/help/using-brilliant/what-is-a-streak-charge/))

**Audience split (worth stealing)** — "I'm a learner" / "I'm a parent or teacher" — two big CTAs ([brilliant.org](https://brilliant.org))

---

## 9. Tech stack (inferred)

**Confirmed:** native iOS + Android apps + full web app ([App Store](https://apps.apple.com/us/app/brilliant-learn-by-doing/id913335252), [Play](https://play.google.com/store/apps/details?id=org.brilliant.android)); **Rive** for animations with conditional state machines ([Rive case study](https://rive.app/blog/how-brilliant-org-motivates-learners-with-rive-animations)); JavaScript, Python, Git/GitHub, Docker ([StackShare](https://stackshare.io/brilliant/brilliant)); Python game engine for their CS courses ([careers](https://brilliant.org/careers/)); AI used for content generation only, not learner tutoring ([Brilliant blog](https://blog.brilliant.org/hand-crafted-machine-made/)).

**UNVERIFIED:** React for web (industry standard but not confirmed in my searches); React Native vs. native Swift/Kotlin for mobile; WebGL/Canvas for interactive widgets (inferred from "calculus curves change in real-time").

Takeaway: mature React + Rive + native-mobile + Python-game-engine stack. **Rive is worth stealing** for state-machine-driven celebration animations on rep-pass / drill-complete events — aligns with our XState plan.

---

## 10. Accessibility posture

**UNVERIFIED in detail** — no published VPAT, WCAG statement, or third-party audit of Brilliant surfaced in my research. Signals:

- Interactive problems (drag-and-drop, manipulable visuals) are inherently keyboard/screen-reader-hostile unless explicitly designed for it. UNVERIFIED whether non-interactive equivalents exist.
- Heavy Rive usage — UNVERIFIED whether `prefers-reduced-motion` is honored. Rive at least architecturally allows it.

Bottom line: Brilliant is **probably not a positive accessibility reference**. Our axe-core CI gate is a defensible differentiator.

---

## 11. Patterns to STEAL vs AVOID (adult-learner framing)

### STEAL

1. **Pretesting / problem-first lesson structure.** Put the problem up before the explanation. Maps directly onto our Drill flow — the user attempts the sign before being shown the breakdown. ([About](https://brilliant.org/about/))
2. **Interactive wrong-answer explanations.** Don't say "wrong, here's why" — let the user manipulate the failure case. For us: when a rep fails, the hint panel lets the user scrub the reference video, side-by-side replay their attempt, and isolate the failing parameter.
3. **"Level Gameboard" navigation** — branching path of lessons in a course. Duolingo's path *minus* the punishment loop. Steal the visual without the streak-shame. ([ustwo](https://ustwo.com/work/brilliant/))
4. **Streak + streak charges with charges earned through real learning.** Kinder than Duolingo's streak-freezes-for-sale. Each completed lesson grants a charge (cap of 2). Forgiveness mechanism for adult learners with real lives. ([Help: streak charge](https://brilliant.org/help/using-brilliant/what-is-a-streak-charge/))
5. **One-tagline pedagogical brand** — "Learn by doing" everywhere with discipline. For us: pick our equivalent ("Practice with your camera" / "Show, don't tell") and repeat it.
6. **Restraint in celebration UX** — ustwo's "Play Thinking" framing: celebrations exist but don't break focus. No mascots, no confetti barf. ([ustwo](https://ustwo.com/work/brilliant/))
7. **Rive (or equivalent) state-machine animation tool** for the feedback layer — scales to conditional states (correct / wrong / hint-shown / retrying). Aligns with our XState practice machine.
8. **Landing-page audience split** — "I'm a learner" / "I'm a parent or teacher". For us: "I'm a student" / "I'm an instructor".
9. **AI for content generation, not learner tutoring.** Their explicit stance ([Brilliant blog](https://blog.brilliant.org/hand-crafted-machine-made/)) is defensible: no chatbot tutor in v1.
10. **~15-minute target lesson length** — right expectation for a college learner. ([myelearningworld](https://myelearningworld.com/brilliant-review/))

### AVOID

1. **Auto-enrolled Leagues with no opt-out.** Brilliant's one engagement-mechanics misstep. Our principles.md already commits to no public leaderboard — hold the line. ([Help: leagues](https://brilliant.org/help/using-brilliant/what-are-leagues-and-leaderboards/))
2. **Sequential gating as a paywall lever** (free = sequential; premium = jump). Monetization-driven, not pedagogy-driven. Free-order for everyone.
3. **Mastery model that's only lesson-completion deep.** Brilliant surfaces nothing about per-concept retention. We expose Sign-level mastery (Learning → Familiar → Known → Mastered) — credible differentiator.
4. **Daily-limit free tier (2/day).** Engagement-as-paywall. Off the table for institutional pilot.
5. **No certificates / credentials** is a real adult-learner gripe ([Nibble](https://nibble-app.com/blog/is-brilliant-worth-it)). For institutional pilots, a completion artifact (PDF or share URL) is cheap and matters.
6. **No instructor channel.** Brilliant has none ([Nibble](https://nibble-app.com/blog/is-brilliant-worth-it)). For us, "ask a Deaf instructor" — even a contact link — is meaningfully different.
7. **Learning Companion character.** Borderline. Skip the mascot — use the Level Gameboard structure without anthropomorphizing it.
8. **Heavy Rive everywhere.** Use Rive for celebration micro-animations only; don't animate the navigation. Honor `prefers-reduced-motion` with static fallbacks.

---

## 12. Open questions

1. **Free-order vs. sequential within a course.** Brilliant gates free users to sequential, premium unlocks jumping. We should commit (recommend: free-order, per ux-spec open-question #6). Brilliant's choice is monetization, not pedagogy.
2. **Pretesting at the rep level.** Brilliant pretests at the lesson level. Could we pretest at the **Sign level** — one cold attempt before the Handshape Drill starts? Imports productive-failure straight into our Drill flow.
3. **Streak-charge cap.** Brilliant caps at 2. For a college audience with mid-semester crunches, 14 days of finals eats both charges. 3–4 may be kinder. UNVERIFIED whether Brilliant has A/B-tested this.
4. **Wrong-answer interactivity at the rep level.** Translating "manipulable explanation" to a sign drill: hint panel shows user's last attempt + reference video with the failing parameter highlighted on a timeline. Needs design with ML team's keypoint outputs.
5. **Daily Challenge equivalent for ASL** — "Sign of the Day". Needs rotation logic; out of v1 scope, worth a stub.
6. **Non-mascot guide.** Could a real Deaf-instructor avatar (photo, not illustration) achieve the Learning Companion's function without anthropomorphizing?
7. **VPAT / WCAG audit on Brilliant.** I could not find one — UNVERIFIED. If absent, our axe-CI commitment is a defensible differentiator.

---

## Sources

- [Brilliant homepage](https://brilliant.org)
- [Brilliant courses](https://brilliant.org/courses/)
- [Brilliant Premium](https://brilliant.org/premium/)
- [Brilliant About](https://brilliant.org/about/)
- [Help: What is a streak?](https://brilliant.org/help/using-brilliant/what-is-a-streak/)
- [Help: What is a Streak Charge?](https://brilliant.org/help/using-brilliant/what-is-a-streak-charge/)
- [Help: What are Leagues and leaderboards?](https://brilliant.org/help/using-brilliant/what-are-leagues-and-leaderboards/)
- [Help: What are Learning Paths?](https://brilliant.org/help/using-brilliant/what-are-learning-paths/)
- [Help: Using Brilliant index](https://brilliant.org/help/using-brilliant/)
- [Brilliant blog — Hand-crafted, machine-made](https://blog.brilliant.org/hand-crafted-machine-made/)
- [App Store — Brilliant: Learn by doing](https://apps.apple.com/us/app/brilliant-learn-by-doing/id913335252)
- [Google Play — Brilliant](https://play.google.com/store/apps/details?id=org.brilliant.android)
- [ustwo case study](https://ustwo.com/work/brilliant/)
- [Rive case study](https://rive.app/blog/how-brilliant-org-motivates-learners-with-rive-animations)
- [myelearningworld 2025 review](https://myelearningworld.com/brilliant-review/)
- [Nibble 2026 review](https://nibble-app.com/blog/is-brilliant-worth-it)
- [StackShare — Brilliant tech](https://stackshare.io/brilliant/brilliant)
