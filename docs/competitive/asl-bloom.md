# Competitive Teardown — ASL Bloom

Peer comparison for our v1 build. ASL Bloom is a direct ASL competitor surfaced by the Lingvano teardown and the ethics fact-check but missed by the first competitive swarm. Sources cited inline; UNVERIFIED items flagged.

---

## Naming hierarchy

ASL Bloom uses a flatter, course-less hierarchy than ours:

| Level | Their name | Example | Our equivalent |
|---|---|---|---|
| Top container | **Module** (sometimes called "unit" in reviews) | "Module 1: Basics" | Course |
| Themed group | **Lesson** | "Greetings" — 5–10 signs/phrases | Lesson |
| Practice atom | **Sign** or **Sentence** | THANK YOU; "Nice to meet you" | Sign |
| Exercise variant | **Quiz / Flashcard / Dialogue / Fingerspelling drill** | matching, multiple choice, slow-mo replay | Drill |
| Attempt | (no exposed concept) | — | Rep |

Total claimed: **23 modules, 120+ video lessons, 1300+ signs and sentences** ([mwm.ai](https://mwm.ai/apps/asl-bloom-sign-language/1631587710); [apps.apple.com](https://apps.apple.com/us/app/asl-bloom-sign-language/id1631587710)). Their marketing site quotes "2,700 signs and sentences" / "75 modules / 250+ lessons" ([aslbloom.com](https://www.aslbloom.com)) — likely includes the dictionary or aspirational scope. UNVERIFIED which is current.

Hierarchy: `Module > Lesson > {Video + Quiz/Flashcard/Dialogue/Fingerspelling}`. No "rep" concept — user controls re-watches.

---

## Page inventory

Inferred from App Store screenshots, reviews, and the marketing site. In user-flow order:

1. Landing / Marketing ([aslbloom.com](https://www.aslbloom.com))
2. Blog hub + 12 SEO articles ([blog](https://www.aslbloom.com/blog/))
3. Per-sign public dictionary pages, e.g. `/signs/camera`
4. App Store / Play Store listing ([Apple](https://apps.apple.com/us/app/asl-bloom-sign-language/id1631587710); [Play](https://play.google.com/store/apps/details?id=com.toleio.us))
5. In-app onboarding (paid features hidden until after profile creation, per [Langoly](https://www.langoly.com/asl-bloom-review/))
6. Paywall / subscription screen
7. Home / Module list
8. Module detail (lesson list)
9. Lesson screen — video demo + slow-mo "turtle" toggle ([Educational App Store](https://www.educationalappstore.com/app/asl-bloom-sign-language); user: "I can click the turtle icon and the video slows way down")
10. Quiz exercise (multiple choice / matching, per [Cooljugator](https://cooljugator.com/blog/asl-bloom-review/))
11. Flashcard practice
12. Fingerspelling drill ([mwm.ai](https://mwm.ai/apps/asl-bloom-sign-language/1631587710))
13. Dialogue / sentence practice with caption toggle (Langoly)
14. Visual dictionary (search 1,300+ signs)
15. AI Assistant chat (text-based; see deep dive)
16. Progress dashboard (streak, weekly calendar, sign count)
17. Settings / subscription management

No camera/permission/calibration screens are documented anywhere.

---

## Per-page feature lists

**Landing** ([aslbloom.com](https://www.aslbloom.com)): hero "the easiest way to learn American Sign Language online"; five target audiences named (parents, teachers, beginners, lifelong learners, "anyone"); app store badges, no in-browser practice; public blog + per-sign dictionary open without sign-up (SEO play); "native and Deaf instructors" claim but no individual instructor named anywhere on the site.

**Blog**: 12 posts Aug–Oct 2025, "Deaf Culture" category exists; topics span 5 parameters of ASL, baby sign, Martha's Vineyard, VRS, interpreters, "Best ASL App" (self-promotional). All bylines are "ASL Bloom Team" — no named human authors.

**Onboarding & paywall**: reviews consistently cite a deceptive-pricing pattern — "implies it's free but requires a lowest upfront payment of $48; pricing not shown until after downloading, creating a profile, and entering information" ([Langoly](https://www.langoly.com/asl-bloom-review/), App Store reviews via [WebFetch](https://apps.apple.com/us/app/asl-bloom-sign-language/id1631587710)). Free tier: 3 modules + dictionary. Paid: $14.99/mo, $48/qtr, $98.99/yr (region-varying).

**Lesson screen**: Deaf signer video demo; "turtle" slow-mo icon (user-quoted as helpful); replay; English gloss caption toggle. Reviewer flagged **mouthing of English words during demos** as undermining ASL-as-its-own-language pedagogy ([Langoly](https://www.langoly.com/asl-bloom-review/)).

**Exercise variants**: multiple choice + matching ([Cooljugator](https://cooljugator.com/blog/asl-bloom-review/)); flashcards (users say repetition coverage is weak); dialogues with caption toggle for sentence-level receptive practice.

**AI Assistant**: marketed as "an AI assistant that gives you feedback and helps guide you through your lessons" ([best-asl-app post](https://www.aslbloom.com/blog/best-asl-app)). All evidence points to **text/chat-based**, not camera-based — see deep dive.

**Progress dashboard**: streak counter, weekly calendar, sign count, points. No public leaderboard or social feed surfaced (UNVERIFIED).

---

## Practice screen deep dive

### State machine — what it actually is

Based on all available sources, the "practice" screen is a **video-watch + multiple-choice/matching quiz**, not a camera-based production check.

```
LESSON
  └─ VIDEO_DEMO          (user watches Deaf signer; turtle icon → slow-mo)
        └─ REPLAY (any number of times)
  └─ QUIZ_BLOCK
        └─ EXERCISE       (multiple choice, matching, or flashcard)
              ├─ correct → next exercise
              └─ incorrect → reveal answer, retry, advance
  └─ DIALOGUE (optional, sentence-level, captions toggle)
  └─ LESSON_COMPLETE → streak/points update
```

### ASCII wireframe (inferred from App Store screenshots)

```
┌──────────────────────────────────────────────┐
│ ← Module 1 · Lesson 3            ✕ exit      │
│ [████████░░░░] 60%                           │
├──────────────────────────────────────────────┤
│                                              │
│   ┌────────────────────────────────────┐     │
│   │                                    │     │
│   │     [Deaf signer, looped video]    │     │
│   │      auto-plays, captioned         │     │
│   │                                    │     │
│   │  🐢 slow-mo     ⟲ replay           │     │
│   └────────────────────────────────────┘     │
│                                              │
│   "How do you sign THANK YOU?"               │
│                                              │
│   ┌─────────────┐  ┌─────────────┐          │
│   │ [video A]   │  │ [video B]   │          │
│   └─────────────┘  └─────────────┘          │
│   ┌─────────────┐  ┌─────────────┐          │
│   │ [video C]   │  │ [video D]   │          │
│   └─────────────┘  └─────────────┘          │
│                                              │
│            [ Continue → ]                    │
└──────────────────────────────────────────────┘
```

### CV / camera affordances

**None confirmed.** No App Store screenshot shows a viewfinder; no review (Langoly, Cooljugator, Educational App Store, App Store user reviews) mentions camera permission, framing guide, or productive-sign evaluation; the "AI assistant" is described as giving "feedback" but no source surfaces a camera path — the wording matches a text/quiz chatbot pattern. A targeted search for "ASL Bloom camera webcam practice sign recognition" returned only third-party tools (Hello Monday, HandSign, MediaPipe demos), none from ASL Bloom.

**Conclusion**: ASL Bloom is **receptive-only**. Productive practice = mirror-watch and self-judge against the reference. This is the gap our v1 targets.

---

## Pedagogy approach

**Receptive vs productive**: Almost entirely receptive — watch-and-recognize. Productive practice is unstructured ("try it yourself") with no feedback loop. Their dialogue lessons are receptive-comprehension drills with captions, not production grading.

**Deaf-led?** Mixed — leans hearing-built with Deaf talent. Founders are **Endre Olsvik Elvestad and Aileen Bui**, Norwegian, incorporated SignLab AS in Oslo Apr 3, 2017 ([Tracxn](https://tracxn.com/d/companies/aslbloom/__IfWQQKDTZQA-zaQPsVt_3kuCj1KYzsKqB-DuqUu6Kzs); [Business Norway](https://businessnorway.com/companies/signlab-as)); neither is documented as Deaf (UNVERIFIED). Marketing claims "native and Deaf instructors" with "CDI, ASLPI 4+, ASL Education Degrees" but **no individual Deaf instructor is named on the site, App Store listing, or any review** — the same anti-pattern Glasser et al. (2022) flag against. SignLab makes 10+ sign-language apps across NSL, DGS, ISL, Libras, LSF, Auslan, CSL, BSL, LIS, ASL ([signlab.co](https://www.signlab.co/)) — a tech-company-doing-many-languages posture, not a community-rooted curriculum.

**Teaching philosophy** (from [the 5-parameters blog post](https://www.aslbloom.com/blog/5-parameters-of-asl)): frames the 5 parameters as "grammar rules" (linguistically sound); explicitly addresses non-manual markers, eyebrow grammar, head shake for negation. But the lesson UI doesn't grade or prompt for non-manual markers — they're explained, shown, never tested.

**Scope**: lexical signs heavy (1,300+); sentences/dialogues yes; fingerspelling drill exists ([mwm.ai](https://mwm.ai/apps/asl-bloom-sign-language/1631587710)); grammar discussed but depth UNVERIFIED ([Langoly](https://www.langoly.com/asl-bloom-review/)); classifiers UNVERIFIED — not mentioned in any source.

**Awards**: Special Olympics Innovation Prize 2019, Zero Project Award 2021, UN SDG selection ([signlab.co](https://www.signlab.co/)).

---

## Microcopy bank

From the public site and reviews. Sparse — they don't expose much copy publicly.

- "Demolish communication barriers, giving users the power of connection through sign." ([mwm.ai](https://mwm.ai/apps/asl-bloom-sign-language/1631587710))
- "The easiest way to learn American Sign Language online." ([aslbloom.com](https://www.aslbloom.com))
- "Imagine a world in which hard of hearing children feel included every day." ([signlab.co](https://www.signlab.co/))
- "Native and Deaf instructors" (aslbloom.com — used as a category claim, no names)
- "AI assistant gives you feedback and helps guide you through your lessons" ([aslbloom.com/blog/best-asl-app](https://www.aslbloom.com/blog/best-asl-app))
- Lesson promise: "You can finish one lesson in 5 mins or less and you'll have learned between 5-10 words/phrases" (user quote from App Store reviews)

Tone: marketing-warm, gamification-light, no Duolingo-style mascot voice but no Linear-style restraint either.

---

## Tech stack (inferred)

| Layer | Inferred choice | Evidence |
|---|---|---|
| Marketing site | Webflow or similar — `/blog/` slug, dense SEO | Visible HTML pattern |
| Mobile | Native iOS (99.4 MB, iOS 15.1+, macOS 12+ AS, visionOS 1.0+) + Android (bundle id `com.toleio.us`) | [apps.apple.com](https://apps.apple.com/us/app/asl-bloom-sign-language/id1631587710); [Google Play](https://play.google.com/store/apps/details?id=com.toleio.us) |
| Video delivery | UNVERIFIED — standard CDN; videos short, looped |
| Backend | UNVERIFIED. The Android bundle id `com.toleio.us` reuses their NSL brand "Toleio" — shared backend across all 10 SignLab apps |
| AI assistant | Text/chat — likely LLM wrapper. Not on-device CV. |
| Auth | Email + subscription via App Store / Play billing |

**Notably absent**: on-device ML, MediaPipe, webcam pipeline, ONNX runtime.

---

## Accessibility posture

Weakly documented.

- Captions toggle on dialogue videos ([Langoly](https://www.langoly.com/asl-bloom-review/)) — good
- Slow-mo "turtle" playback — strong affordance for learners and low-vision users
- **English-mouthing** in sign demos flagged by reviewer ([Langoly](https://www.langoly.com/asl-bloom-review/)) — known concern from Deaf-led pedagogy literature
- No mention of reduced-motion, screen-reader semantics, high-contrast, font scaling, or keyboard nav (mobile-first)
- App Store accessibility tags: standard, no specific a11y features called out
- Reviewer complaint: "doesn't support family sharing"
- Inclusivity gap: "lacks options for users with developmental disorders, mutism, or nonverbal people" (App Store reviews via WebFetch)

---

## Notable patterns — STEAL vs AVOID

### STEAL

1. **Turtle slow-mo button on every reference video** — universal-design win; users specifically praised it.
2. **Per-sign public dictionary pages (/signs/camera)** — SEO-as-utility; gives public free access to the dictionary without sign-up. Mirror without compromising practice-tool scope.
3. **Awards & impact-mission framing** — Special Olympics + Zero Project + UN-SDG positioning is credibility done right; our equivalent is research rooting (Glasser, Bragg, Battison).
4. **Explicit blog post on the 5 parameters** including non-manual markers — they explain what they don't grade. Do the same on our Help page (already planned, ux-spec §19).
5. **Short, 5-minute lesson framing** — matches our drill cadence and principles.md spaced-practice prescription.
6. **Multi-language scaffold across 10+ sign languages from one codebase** — long-term posture, even if v1 is ASL-only.

### AVOID

1. **No camera, no productive grading** — the gap our v1 fills. Don't follow them into receptive-only land.
2. **"Native and Deaf instructors" without naming any** — direct Glasser et al. (2022) violation. Our About page must name people.
3. **English-mouthing on sign demos** — anti-pattern for ASL-as-its-own-language. Our reference videos must not mouth English. Add to Deaf-consultant brief.
4. **Deceptive free-tier UX** — paywall hidden until after profile creation, $48 minimum upfront. Our pricing must be visible pre-sign-up.
5. **Sequencing that teaches "plaid"/"polka dots" before "because"/"give"** — reviewers flag random vocab vs communicative competence. Our sign-list freeze must sequence for utility.
6. **No public list of curriculum signs** — forces download to evaluate. Our Lesson Catalog being browsable pre-sign-up would beat this.
7. **AI assistant that's a chat wrapper, not a CV feedback loop** — marketing "AI" without substance. If we say "your camera evaluates your signs," it must actually do so.
8. **Single dictionary entry per sign** with no regional/variant coverage — reviewers complain Deaf community uses variants the app omits.

---

## Open questions / could not verify

1. **Founders' (Elvestad, Bui) Deaf status** — no source states either way. Absence of disclosure is itself a signal.
2. **Named Deaf instructors inside the app** — could not verify without paid install. Worth a $14.99/mo test purchase if budget allows.
3. **AI assistant ever using the camera** — all evidence says no, but I could not log in. UNVERIFIED.
4. **Classifier coverage** — not mentioned in any source. UNVERIFIED.
5. **Reddit/Deaf community direct discussion** — search returned no r/deaf threads. The "mixed reception in the Deaf community" framing from our Lingvano teardown is plausible but unsourced; App Store negative reviews trend toward pricing-deception and curriculum-ordering, not authenticity critique.
6. **23/120 vs 75/250 module discrepancy** — App Store likely canonical; marketing site may be aspirational or include the dictionary.
7. **Video signer demographics** — single signer per sign? Diverse Deaf representation? UNVERIFIED.
8. **Whether any non-manual marker is ever graded or merely shown** — strongly suspect "merely shown."
9. **Justuseapp.com aggregator returned 403** — additional unstructured complaints likely exist there.

---

**Bottom line**: ASL Bloom is a polished, receptive-only ASL app from a Norwegian multi-language sign-tech startup. Their slow-mo affordance and per-sign public dictionary are worth borrowing. Their unnamed-instructor marketing, English-mouthing demos, hidden paywall, and absence of productive practice are the gaps that justify our v1.
