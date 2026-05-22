# Competitive UX Teardown — Khan Academy

Source product: **khanacademy.org** (web) + iOS/Android apps. Snapshot as of 2025–2026. Khan Academy is the academic origin of the mastery-bar model we adopted in [`principles.md`](../principles.md); their pedagogy is Bloom's *Learning for Mastery* (1968) and they've published outcomes research. Our audience is adult college learners, not K–12 — but the "is this learner ready to advance" UX ports directly.

Citation note: every claim links a URL. `UNVERIFIED` marks anything I couldn't pin to a primary source in this pass.

---

## 1. Naming hierarchy

| Level | Name | Notes |
|---|---|---|
| Top container | **Course** | A subject + grade band — e.g., "Algebra 1", "8th grade math", "AP Biology" ([khanacademy.org](https://www.khanacademy.org/)) |
| Course bucket | **Unit** | Themed chapter inside a course — e.g., "Unit 3: Linear equations". Each unit has its own progress bar and Unit Test ([Khan Help — Course and Unit Mastery](https://support.khanacademy.org/hc/en-us/articles/115002552631-What-are-Course-and-Unit-Mastery)) |
| Unit bucket | **Lesson** | Smaller topic grouping inside a unit; contains videos, articles, exercises ([Khan Help — Learner Home](https://support.khanacademy.org/hc/en-us/articles/360030629852-What-is-my-Learner-Home-page-and-what-can-I-do-there)) |
| Atomic playable | **Exercise** ("Practice") | A set of problems on a single skill ([Khan Help — Mastery levels](https://support.khanacademy.org/hc/en-us/articles/5548760867853--How-do-Khan-Academy-s-Mastery-levels-work)) |
| Atomic skill unit | **Skill** | The thing mastery is tracked against; multiple exercises map to one skill ([same](https://support.khanacademy.org/hc/en-us/articles/5548760867853)) |
| Review surfaces | **Quiz / Unit Test / Mastery Challenge / Course Challenge** | Four distinct assessments — see §4 ([Khan Help — Mastery Challenges](https://support.khanacademy.org/hc/en-us/articles/360037494231)) |

Hierarchy: `Course > Unit > Lesson > Exercise/Quiz/Test`, with **Skill** as a cross-cutting mastery axis independent of the navigation tree. Shallower than Duolingo's six-level tree.

---

## 2. Page inventory (learner only — skipping teacher / district)

| # | Screen | Purpose |
|---|---|---|
| 1 | Marketing landing | Public; mission pitch, sign-in/up |
| 2 | Sign-up | Learner / Teacher / Parent picker; email or Google/Apple/Microsoft SSO |
| 3 | Sign-in | Returning user |
| 4 | Onboarding: role + grade | Sets recommended courses |
| 5 | Onboarding: course pick | Adds courses to home |
| 6 | **Learner Home** | Dashboard — "My courses" tiles, streak, levels, Khanmigo ([Learner Home](https://support.khanacademy.org/hc/en-us/articles/360030629852)) |
| 7 | Course Homepage | Per-course progress; Units with mastery bars; Course Challenge card pinned at bottom ([Course/Unit Mastery](https://support.khanacademy.org/hc/en-us/articles/115002552631)) |
| 8 | Unit Homepage | Per-unit lessons, Unit Test card, Quiz cards, mastery % |
| 9 | Lesson page | Stacked content cards (video, article, exercise) for one lesson |
| 10 | **Video player** | YouTube-like player + transcript, captions, speed, "Ask Khanmigo" |
| 11 | Article page | Long-form explainer with embedded checkpoints |
| 12 | **Exercise screen** | Main practice surface — see §5 |
| 13 | **Quiz screen** | Mid-unit checkpoint covering several skills |
| 14 | **Unit Test** | End-of-unit; required to reach "Mastered" |
| 15 | **Mastery Challenge** | Spaced-review across skills you've started ([Mastery Challenges](https://support.khanacademy.org/hc/en-us/articles/360037494231)) |
| 16 | **Course Challenge** | Sampling assessment across the entire course |
| 17 | Post-exercise / quiz results | Score, mastery level changes, "Next up" CTA |
| 18 | Progress / Achievements | Badges, energy points, skill grid |
| 19 | Streak detail | Day count, freeze status, milestones ([Streaks](https://support.khanacademy.org/hc/en-us/community/posts/28945393485581)) |
| 20 | Khanmigo chat | AI tutor pane (sidebar/full-screen) ([khanmigo.ai](https://www.khanmigo.ai/learners)) |
| 21 | Khanmigo specialised modes | Writing coach, debate, coding tutor |
| 22 | Profile | Avatar, points, badges, courses, public toggle |
| 23 | Search, Settings, Accessibility statement | Standard; [accessibility page](https://www.khanacademy.org/about/accessibility-statement) |

---

## 3. Per-page feature lists (selected)

### Learner Home (page 6)
- "My courses" grid — up to 9 pinnable course tiles, each showing course name, current unit, skills-in-unit counter, mastery bar ([Khan Help — Edit My Courses](https://support.khanacademy.org/hc/en-us/articles/115003342971))
- Streak flame + day count, levels widget, energy points total
- Khanmigo entry point (top-right on web; persistent for subscribers)
- 2026 redesign added a **Learner Queue** — structured Missions feed breaking work into smaller steps ([EdTech Innovation Hub — Khan classroom redesign](https://www.edtechinnovationhub.com/news/khan-academy-redesigns-classroom-platform-as-ai-tools-move-further-into-daily-teaching))
- No public leaderboard on Home (contrast Duolingo)

### Course Homepage (page 7)
- Course title + overall mastery % at top
- Vertical list of Units; each row a mastery bar (4 color bands matching mastery levels) + unit name
- **Course Challenge** card pinned at the bottom — opt-in fast-forward for prerequisite-strong learners ([Khan Help — Course and Unit Mastery](https://support.khanacademy.org/hc/en-us/articles/115002552631))
- **Mastery Challenge** card surfaces here when eligible (see §4)

### Exercise screen — see §5.

---

## 4. Mastery system deep dive

This is the load-bearing system for our project; treat as the canonical reference.

### The 5 mastery levels (per skill)

| Level | Mastery Points | How you reach it | Source |
|---|---|---|---|
| **Not started** | 0 | Default state | [Khan Help — Mastery levels](https://support.khanacademy.org/hc/en-us/articles/5548760867853) |
| **Attempted** | small partial | First attempt < 70%, OR you regressed from Familiar by scoring < 70% on an exercise or missing all questions about that skill on a quiz/test/challenge | same |
| **Familiar** | 50 / 100 | Score 70–85% on an exercise, OR answer all questions about the skill correctly on a quiz/test/challenge from Not started / Attempted | same |
| **Proficient** | 80 / 100 | From Familiar: answer all questions about the skill correctly on an exercise, quiz, test, or challenge | same |
| **Mastered** | 100 / 100 | From Proficient: get all questions about the skill correct on a **Unit Test or Course Challenge** | same |

Two pedagogical notes:
- **Asymmetric advancement / regression.** You can only advance one level at a time, but you can regress from Familiar directly to Attempted on a single bad pass — baking in spaced-retrieval pressure.
- **Top level requires a different surface.** "Mastered" is gated behind a Unit Test or Course Challenge — you cannot reach it from the practice exercise alone. Separates "I can do it warned" (Proficient) from "I retain under cold-recall" (Mastered).

### The four assessment surfaces

| Surface | What it covers | Question count | Frequency / unlock | Source |
|---|---|---|---|---|
| **Exercise** | One skill | 4–7 questions typical | Unlimited; user-driven | [Khan Help — Mastery levels](https://support.khanacademy.org/hc/en-us/articles/5548760867853) |
| **Quiz** | A handful of skills inside a Unit | ~5–10 | At lesson/unit checkpoints | same |
| **Unit Test** | All skills in a Unit | Larger set | Unlimited retakes; required to reach Mastered | [Khan Help — Course and Unit Mastery](https://support.khanacademy.org/hc/en-us/articles/115002552631) |
| **Mastery Challenge** | 3 skills × 2 questions = **6 questions** | 6 | Personalised spaced-review. Unlocks when you've reached Familiar on ≥3 skills AND Proficient on ≥1 skill AND ≥12 h since last challenge. One per 12-hour window. **Math courses only** as of last documentation. ([Khan Help — Mastery Challenges](https://support.khanacademy.org/hc/en-us/articles/360037494231)) |
| **Course Challenge** | Sampling across entire course | ~30 questions | Always available; "fast-forward" for prerequisite-strong learners ([Khan Help — Course and Unit Mastery](https://support.khanacademy.org/hc/en-us/articles/115002552631)) |

The Mastery Challenge is the most distinctive piece — it's effectively **enforced spaced retrieval** dressed as a daily challenge. Two questions per skill is enough signal to advance one level if both are right; the 12-hour cooldown prevents grinding.

**What this means for our project:** the explicit thresholds (70 / 85 / 100 / 100-on-test) are more granular than `principles.md` (`New / Learning / Familiar / Known / Mastered`, advance on "3 correct reps"). Tighten the top tier to require a cold-recall surface — an analogue Unit-Test "Lesson Review." The single-pass regression rule is too harsh for adults; A/B a gentler "two-misses-to-regress" rule.

---

## 5. Exercise screen — deep dive

### Layout (desktop, web)

```
┌───────────────────────────────────────────────────────────────┐
│ ← Algebra 1 / Unit 3 / Linear equations         [×]           │
│  ●●●○○○○   3 of 7    Skill: Solving two-step equations        │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│  Solve for x:                                                 │
│    3x + 7 = 22                                                │
│                                                               │
│  ┌─────────────────────────────────┐                          │
│  │ Your answer:  [    5    ]       │                          │
│  └─────────────────────────────────┘                          │
│                                                               │
│  [ Check ]                                                    │
│                                                               │
│  ─────────────────────────────────                            │
│   Stuck?   [ Get a hint ]    [ Watch a video ]                │
│                                                               │
│   (Khanmigo) "Want me to walk you through this?"  →           │
└───────────────────────────────────────────────────────────────┘
```

Reference image: [ResearchGate — Exercise interface at Khan Academy](https://www.researchgate.net/figure/Exercise-interface-at-Khan-Academy_fig3_262153359).

### Single-problem state machine

```
PROBLEM_READY
  └─ user types/selects an answer
PROBLEM_SUBMITTED
  ├─ correct
  │    → PROBLEM_PASS (green check, encouraging copy, "Next question" CTA)
  ├─ incorrect
  │    → PROBLEM_FAIL (red X, "Try again" OR "Show solution"; problem stays on screen)
  └─ user requested hint at any point
       → HINT_REVEALED (problem flagged: even if correct, this question does NOT count as successful)
            └─ keep tapping Hint → reveals next step → eventually full worked solution
```

### Hint system specifics

- Hints **break the problem into the next step**; pressing Hint repeatedly walks to the full solution ([Khan community thread](https://support.khanacademy.org/hc/en-us/community/posts/39370163344653)).
- **Cost of a hint:** the question gets answered but is **not counted toward mastery advancement** — explicit anti-hint-abuse mechanic ([Cult of Pedagogy](https://www.cultofpedagogy.com/khan-mastery-learning/), [educator writeup](https://mslwheeler.wordpress.com/2018/02/17/my-khan-academy-pedagogy/)).
- Hints sit beside a **"Watch a video"** affordance — one-click pivot to the lesson video without losing the problem state.
- 2024–2026: Khanmigo offers Socratic prompts instead of answers ([khanmigo.ai/learners](https://www.khanmigo.ai/learners)).

**Post-exercise:** results card shows correct/incorrect counts, mastery level change, energy points earned, "Next up" CTA (next lesson or a newly-unlocked Mastery Challenge).

---

## 6. Pedagogy approach

Khan Academy is the most explicit edtech expression of **Benjamin Bloom's mastery learning** (1968, *Learning for Mastery*; 1984, "The 2 Sigma Problem"). Sal Khan cites Bloom in *The One World Schoolhouse* and in his Help Center ([Khan Help — Why Mastery Learning, by Sal Khan](https://support.khanacademy.org/hc/en-us/articles/360030753412), [Cult of Pedagogy](https://www.cultofpedagogy.com/khan-mastery-learning/)).

**The Bloom claim:** practice to ~90% competence before advancing instead of moving on at 70%; average outcomes shift up by ~2 SD. Khan is a software approximation of one-to-one tutoring at scale.

**Outcomes research Khan cites:**
- **SRI Education / Gates, 2014:** 20-school implementation study; positive correlations between Khan use and math achievement ([Khan blog — Multiple studies show learning gains](https://blog.khanacademy.org/multiple-studies-show-khan-academy-drives-learning-gains-evidence-for-our-platforms-effectiveness/)).
- **Idaho / Albertson Foundation, 5,000+ students:** learners completing ≥60% of a course under the mastery framework grew ~1.8× as much as peers ([Big Think — Khan on AI and mastery](https://bigthink.com/the-present/khan-academy-ai/)).
- **2023 RCT, ~11,000 students, grades 3–8:** end-of-year math +0.12 to +0.22 SD vs. control with mastery-aligned use ([Khan blog](https://blog.khanacademy.org/multiple-studies-show-khan-academy-drives-learning-gains-evidence-for-our-platforms-effectiveness/)).

**Note for our project:** K–12 math; does *not* generalise to adult learners or motor-skill vocabulary. The mastery *UX pattern* ports; the outcome magnitudes do not. Do not cite "2 sigma" in marketing.

---

## 7. Engagement mechanics

| Mechanic | What it does | UX prominence | Source |
|---|---|---|---|
| **Energy points** | Measure of *effort*, explicitly not mastery. Earned for almost any activity: completing a skill, watching a video, badges, discussions, etc. | High — shown on profile, dashboard, and after every exercise | [Khan Help — Energy points, badges, avatars](https://support.khanacademy.org/hc/en-us/articles/202487710) |
| **Badges** | Five tiers (Meteorite → Moon → Earth → Sun → Black Hole) plus special "Challenge Patches" tied to course completion or events | Medium — visible on profile; surfaced after milestones | same; [Khan blog — New point badges](https://support.khanacademy.org/hc/en-us/community/posts/115004534527-Update-New-point-badges) |
| **Streaks** | Reintroduced in 2024 with new visual treatment after Khan deprecated them years earlier | Medium — flame icon on Learner Home, milestones at 7/30/100/365 days | [Khan Help — Introducing Streaks and Levels](https://support.khanacademy.org/hc/en-us/community/posts/28945393485581) |
| **Levels** | Per-account leveling tied to total energy points | Low–medium | same |
| **Avatars** | Cosmetic — earned via badges/points | Low | [Khan Help — Energy points, badges, avatars](https://support.khanacademy.org/hc/en-us/articles/202487710) |

**Energy-points vs streaks:** energy points dominate historically — every results screen, profile, and an entire community wiki on "energy point grinding" ([khanacademy.fandom.com](https://khanacademy.fandom.com/wiki/Energy_Point_Grinding)). Streaks were absent for years; reintroduced in 2024 in a deliberately lower-key form than Duolingo's. **Khan is not a streak-first product.** Mastery is the spine; effort points and streaks are reinforcement. No leagues, no public leaderboards, no hearts/energy depletion — the "fail-state shame" axis Duolingo amplifies is largely absent.

---

## 8. Microcopy bank

- "You've reached **Familiar** in *Solving two-step equations*."
- "Get a hint" / "Watch a video" / "Show solution"
- "Mastery Challenge ready — review 3 skills"
- "Course Challenge — a quick way to test out of material you already know"
- "Khanmigo is here to help — ask anything"
- "You earned 350 energy points"
- "Day 12 streak"
- (Khanmigo, Socratic) "What do you think the first step is?"

The tone is **earnest, neutral, non-game-y**. No mascot voice, no exclamation pile-ups, no "STREAK SAVER!" red banners.

---

## 9. Tech stack (inferred / reported)

| Layer | Choice | Source |
|---|---|---|
| Frontend | **React** with SSR | [Khan eng archive](https://blog.khanacademy.org/engineering/), [Quastor writeup](https://blog.quastor.org/p/khan-academy-rewrote-backend) |
| API | **GraphQL + Federation** | [Incremental rewrites with GraphQL](https://blog.khanacademy.org/incremental-rewrites-with-graphql/) |
| Backend | Was a **Python 2 monolith**; migrated to **Go services** ("Goliath"); still on **Google App Engine** | [Go + Services = One Goliath Project](https://blog.khanacademy.org/go-services-one-goliath-project/) |
| Database | **Google Cloud Datastore** | same |
| Mobile | Native iOS + Android | [Play listing](https://play.google.com/store/apps/details?id=org.khanacademy.android) |
| AI | **Khanmigo** on OpenAI GPT-class models; 2025–2026 work targeted latency (faster model, shorter outputs, tighter timeouts, smarter routing) | [Building a better AI tutor](https://blog.khanacademy.org/how-khan-academy-is-building-a-better-ai-tutor-our-most-recent-learnings/) |
| Math rendering | KaTeX-class equations; **MathPlayer / MathCAT** for screen readers | [Screen readers](https://support.khanacademy.org/hc/en-us/articles/360015349472) |

Matches the brief's "React + Python + GraphQL," with the caveat that **Python is being phased out for Go**.

---

## 10. Accessibility posture

- Public accessibility statement adopting **WCAG 2.2 AA** as the development baseline ([khanacademy.org/about/accessibility-statement](https://www.khanacademy.org/about/accessibility-statement)).
- **Annual VPATs / Accessibility Conformance Reports** plus a mid-year check-in and published roadmap to close partial-support gaps ([Khan blog — ADA Title II](https://blog.khanacademy.org/ada-title-ii-and-digital-accessibility-what-schools-and-edtech-need-to-know/)).
- Third-party audits and accessibility-focused engineering training (same).
- Screen-reader support: **NVDA + Chrome** recommended; equations require MathPlayer / MathCAT ([Khan Help — Screen readers](https://support.khanacademy.org/hc/en-us/articles/360015349472)). Captions/transcripts on instructional videos. Recent work: modal keyboard nav, color-contrast fixes, icon redesigns ([Khan Help — Accessibility section](https://support.khanacademy.org/hc/en-us/sections/4404526648845)).

Strong reference posture. Our [`ux-spec.md`](../ux-spec.md) checklist is already aligned (WCAG 2.2 AA, axe-core CI gate, prefers-reduced-motion); match their cadence (annual VPAT) once we leave pilot.

---

## 11. Patterns to STEAL vs AVOID (for adult ASL learners)

### STEAL

1. **Tiered mastery with named, transparent levels.** Learners know what advancing means and what it takes. Our `New / Learning / Familiar / Known / Mastered` is the right shape — keep the *named* taxonomy visible, not just a percentage.
2. **Higher surface required for top level.** Khan reserves "Mastered" for cold-recall mixed-context performance on a Unit Test / Course Challenge. Add an analogue **Lesson Review** that mixes signs from across the lesson and grades without hints — otherwise "Mastered" inflates.
3. **Spaced retrieval as a small, daily-ish challenge.** Mastery Challenge = 6 questions, 3 skills, 12-h cooldown. Maps cleanly to a 6-rep mixed-sign drill once a learner has ≥1 Familiar sign in N lessons. Low cost, high pedagogical value.
4. **Hints cost mastery credit, not lives.** A hint lets you finish the problem but disqualifies it from advancing. Cleaner than Duolingo's heart gate; respects adult autonomy.
5. **Energy points = effort, not skill.** Explicit separation lets learners feel rewarded for showing up without conflating effort with competence.
6. **No public leaderboards by default.** Comparative shame is a poor motivator for adults; keep our "no leaderboard" stance.

### AVOID

1. **Asymmetric one-shot regression** (Familiar → Attempted on a single bad pass). Punishing for time-pressured adults; use a gentler "two consecutive misses to regress" rule.
2. **Mastery Challenge gated to Math only.** Khan never rolled the personalised spaced-review surface to other subjects. Build ours as content-agnostic infrastructure from day one.
3. **Energy-points grinding loops.** Community wikis on "energy point grinding" prove the metric leaks into gameable behaviour. Surface effort metrics privately (own profile only), not as comparative currency.
4. **Reintroduced streaks under engagement pressure.** Khan re-added streaks in 2024 to compete; adult learners report streak-anxiety as a known harm. Keep our soft-streak (freezes, no shame state).
5. **Hint-that-walks-to-full-solution.** Works for math because the solution generalises; useless for an ASL sign where "show the answer" just replays the reference. Keep our parameter-tagged hints.

---

## 12. Open questions

1. **Exact Mastery Challenge eligibility over time.** Khan has tweaked the unlock criteria across 2018 / 2020 / later; the "≥3 Familiar AND ≥1 Proficient AND ≥12 h" rule may have shifted again. `UNVERIFIED` for the latest A/B variants.
2. **Mastery Challenge beyond Math.** Last documentation was Math-only; recent Khanmigo work may have extended it. `UNVERIFIED`.
3. **Khanmigo pricing tiers** beyond the $4/mo / $44/yr learner price ([kidsaitools — Khanmigo review 2026](https://www.kidsaitools.com/en/articles/khanmigo-review-parents-complete-2026)). District-licensed Khanmigo is free in many US districts; exact eligibility not verified here.
4. **State-management approach in Khan's frontend.** React + SSR is confirmed; exercise-state library (Redux, MobX, hand-rolled) is undocumented publicly.
5. **Per-question weighting inside a Quiz** when a Quiz spans multiple skills. Help center documents the outcomes, not the weighting math.
6. **Adult-learner share of Khan's base.** K–12-anchored, but adults use it for test prep and career switching. The mastery UX may behave differently for adults — no public segmentation found.
