# Competitive UX Teardown — Anki

Anki is the canonical SRS app — open source, ~20 years old, desktop-first. Our app is beginner-coded; Anki is power-user-coded and ships effectively zero onboarding. Most of its surface won't translate verbatim, but the *review state machine, grade-button vocabulary, and interval-preview pattern* are directly transferable. Sources are primary: `docs.ankiweb.net` (the official manual), `apps.ankiweb.net`, and the GitHub repos.

---

## 1. Naming hierarchy

| Level | Anki term | Notes |
|---|---|---|
| Top container | **Collection** | All material for one user; one per profile. |
| Group | **Deck** | The study unit; can be nested. |
| Logical record | **Note** | A bundle of related facts (e.g. English / Spanish / audio). |
| Field | **Field** | A single slot inside a Note (`Front`, `Back`, `Audio`). |
| Visible study unit | **Card** | What you grade; a Note generates 1..N Cards via Templates. |
| Card blueprint | **Template** ("Card Type") | Which fields appear on front and back. |
| Note schema | **Note Type** ("Model") | Fields + templates a Note belongs to. |
| One grading event | **Review** | A single Show-Front → Show-Back → grade pass. |

Sources: [getting-started](https://docs.ankiweb.net/getting-started.html), [editing](https://docs.ankiweb.net/editing.html).

Key insight: in Anki, **you author Notes, but you grade Cards** — one note ("Canberra was founded in 1913") can produce two cloze cards. Central to power users, confusing to beginners; our app collapses this by treating Sign ≈ Note ≈ Card.

---

## 2. Page / surface inventory

Anki is three products sharing a sync protocol and a card schema:

| Product | Platform | Pricing | Role |
|---|---|---|---|
| **Anki (desktop)** | Win / macOS / Linux | Free, open source | Authoring + power-user tool; full surface |
| **AnkiMobile** | iOS / iPadOS | Paid ~$25, funds the project | Mobile review client |
| **AnkiDroid** | Android | Free, GPL-3.0 (community fork) | Mobile review client |
| **AnkiWeb** | Browser | Free | Cloud sync + minimal browser reviewer |

Source: [apps.ankiweb.net](https://apps.ankiweb.net).

**Desktop screens:** Deck list (root, New/Learning/Due counts), Deck overview ("Study Now"), Review screen (Section 4), Add (with `Fields…` + `Cards…` template editor), Browse (spreadsheet + bulk ops), Stats (heatmap + interval graphs), Card Templates editor (HTML/CSS), Note Types manager, Preferences, Import/Export (apkg, CSV), Get Shared Decks. **AnkiWeb** is intentionally minimal — sign-in, deck list, review-only; primarily sync + emergency reviewer. Sources: [getting-started](https://docs.ankiweb.net/getting-started.html), [studying](https://docs.ankiweb.net/studying.html), [preferences](https://docs.ankiweb.net/preferences.html).

---

## 3. Per-page feature highlights

**Deck list** — Tree of decks; per-row `New | Learning | Due` counters. Top bar: Decks / Add / Browse / Stats / Sync. Bottom: Get Shared, Create Deck, Import File. No greeting, no streak, no "continue last lesson."

**Add Note** — Note-type dropdown, target Deck, editable fields, `Fields…` + `Cards…` buttons. Bottom: Add / Close / Help. No autosave.

**Browse** — Spreadsheet of cards. Sidebar: Today / Card State / Decks / Tags / Note Types. Bulk ops: suspend, tag, reschedule, delete, change deck.

**Stats** — Forecast graph, reviews-history graph, card counts (New / Young / Mature / Suspended), and a daily-activity heatmap — visual ancestor of our dashboard month grid.

**Preferences (a11y-relevant subset)** — `Theme: light/dark/auto`, `User interface size`, `Reduce motion`, `Show next review time above answer buttons`, `Spacebar (or enter) also answers card`, `Hide the top and bottom bar during reviews`, `Enable the 'minimalist' mode`. Source: [preferences](https://docs.ankiweb.net/preferences.html).

---

## 4. Review screen — the deep dive

### State machine

```
DECK_OVERVIEW → click "Study Now"
  └─ for each card in queue:
       FRONT_SHOWN  — question + "Show Answer" button
         └─ Space/Enter/click → BACK_SHOWN
              question + answer + grade buttons (with interval previews)
              pick Again | Hard | Good | Easy → scheduler updates → next card
  empty queue → "Congratulations! You have finished this deck for now."
```

Sources: [docs.ankiweb.net/studying](https://docs.ankiweb.net/studying.html), [docs.ankiweb.net/preferences](https://docs.ankiweb.net/preferences.html).

### Button matrix

| Button | When shown | Keyboard | Effect |
|---|---|---|---|
| **Again** | All states (new, learning, review) | `1` | Card is wrong. Reset to first learning step. Counts as a lapse if card was in review state. |
| **Hard** | Learning + review; *omitted in some configurations* | `2` | Correct but slow. On first learning step shows average delay (e.g. "6m"). On review: small interval growth. |
| **Good** | Always | `3`, `Space`, `Enter` | Correct with effort. Advance step or grow interval normally. |
| **Easy** | Always | `4` | Effortless. Graduate immediately to review state, or apply Easy bonus. |

Source: [docs.ankiweb.net/studying](https://docs.ankiweb.net/studying.html). Two-button mode (Again / Good only) is explicitly supported.

### ASCII wireframe (desktop review screen, BACK_SHOWN state)

```
┌────────────────────────────────────────────────────────────┐
│  Decks   Add   Browse   Stats   Sync                       │
├────────────────────────────────────────────────────────────┤
│             What is the capital of Australia?              │
│             ─────────────────────────                      │
│                       Canberra                             │
│                                                            │
│      <10m>        <6m>        <1d>        <4d>             │
│    ┌───────┐  ┌───────┐  ┌───────┐  ┌───────┐              │
│    │ Again │  │ Hard  │  │ Good  │  │ Easy  │              │
│    └───────┘  └───────┘  └───────┘  └───────┘              │
│       1          2          3          4                   │
├────────────────────────────────────────────────────────────┤
│  New: 12   Learning: 4   Due: 87        Edit   More        │
└────────────────────────────────────────────────────────────┘
```

The angle-bracket labels above each button are the **next-interval previews** ("10 minutes", "6 minutes", "1 day", "4 days") — enabled by `Show next review time above answer buttons` (on by default in recent versions).

---

## 5. SRS algorithm UX exposure

**Two schedulers ship side by side.** SM-2 (legacy SuperMemo 2 variant) exposes Graduating interval, Easy bonus, Interval modifier, Lapse new interval, and learning steps as user-tunable knobs. **FSRS** (Free Spaced Repetition Scheduler) was integrated in Anki **23.10, 31 Oct 2023** ([Wikipedia](https://en.wikipedia.org/wiki/Anki_(software))). DSR-model (Difficulty / Stability / Retrievability); replaces most SM-2 knobs with a single **Desired Retention** slider (default `0.90`). Source: [deck-options](https://docs.ankiweb.net/deck-options.html).

**Learning steps.** Default `1m 10m`. Good advances one step; Again resets to step one. Hard on first step shows an average delay (e.g. `6m`). Cards graduate after passing final step with Good; default Graduating Interval = 1 day.

**Interval disclosure.** The `Show next review time above answer buttons` preference prints the projected next-review time directly above each grade button (`10m / 6m / 1d / 4d`). **The most copyable Anki pattern** — the algorithm is not hidden; the consequence of each grade is visible at the moment of choice. Source: [preferences](https://docs.ankiweb.net/preferences.html), [LeanAnki](https://leananki.com/best-settings/).

**Leech detection.** Lapse = failing a card in review state. Default threshold: **8 lapses**. Default action: **tag note `leech` + suspend card**. Repeat alerts fire every `threshold/2` lapses thereafter (every 4 — at 12, 16…). Source: [leeches](https://docs.ankiweb.net/leeches.html).

**Daily queue construction.** New cards drawn alphabetically per deck (cap default 20). Learning cards drawn across all decks by due time. Reviews drawn separately (cap default 200). Overdue → longest-waiting cards prioritized. Small randomized "fuzz" prevents same-day clustering. Source: [studying](https://docs.ankiweb.net/studying.html).

---

## 6. Microcopy bank (actual Anki strings)

| Surface | String |
|---|---|
| Marketing tagline | "Powerful, Intelligent Flashcards." |
| Marketing testimonial | "Anki makes memory a choice." |
| Deck list CTA | "Study Now" |
| Deck list secondary | "Get Shared", "Create Deck", "Import File" |
| Review — front | "Show Answer" |
| Review — grade buttons | "Again", "Hard", "Good", "Easy" (one word each, no hedging) |
| Review — empty queue | "Congratulations! You have finished this deck for now." |
| Manual — beginner warning (SuperMemo quote) | "Do not learn if you do not understand." |
| Manual — recommendation | "Creating your own deck is the most effective way to learn." |
| Add window | "Add", "Close", "Fields…", "Cards…" |
| Preferences | "Show next review time above answer buttons", "Reduce motion", "Enable the 'minimalist' mode" |

The button vocabulary is famously sparse — no "Try again!", no "Great job!", no adverbs. That austerity is core to the product's identity.

---

## 7. Tech stack

**Anki desktop** ([github.com/ankitects/anki](https://github.com/ankitects/anki)) — Rust ~46% (backend engine `rslib`, scheduler, sync server, FSRS), Python ~30% (app shell, add-on API), Svelte ~11% + TypeScript ~11% (web-based UI), Qt/PyQt for native desktop chrome. ~28k stars, 75 releases.

**AnkiDroid** ([github.com/ankidroid/Anki-Android](https://github.com/ankidroid/Anki-Android)) — Kotlin primary, legacy Java in `libanki/` (ported from desktop Python). GPL-3.0. Distributed via Google Play and F-Droid.

**AnkiMobile** (iOS) — closed-source, same author as desktop (Damien Elmes), paid ~$25 one-time; funds the project.

**AnkiWeb** — closed-source sync server + minimal browser reviewer.

The sync protocol is the unifying contract: every client speaks AnkiWeb sync, so schema and scheduler outputs are identical across clients.

---

## 8. Accessibility posture

**Ships:** dark mode (`Theme: Dark` or auto), `Reduce motion`, `User interface size` scaling, keyboard-first review (`Space`/`Enter` flip, `1-4` grade, `e` edit, `*` mark, `@` suspend), minimalist mode, hide-bars-during-reviews.

**Missing or weak:** no documented screen-reader testing (NVDA/JAWS/VoiceOver not mentioned); no captions standard for audio/video media (template-author dependent); default light theme is Qt-standard, not WCAG 2.2 AA audited; AnkiWeb a11y undocumented.

Source: [docs.ankiweb.net/preferences](https://docs.ankiweb.net/preferences.html). Anki gives strong keyboard control and a real motion toggle, but a11y is not a marketed priority — a gap we should treat as an opportunity, not a model.

---

## 9. Patterns to STEAL vs AVOID

### STEAL

1. **Interval previews above each grade button.** Anki's single most evidence-based UX choice. Users see "10m / 6m / 1d / 4d" before grading — the algorithm becomes legible. Apply directly: preview mastery transitions at the choice point.
2. **One-word grade buttons.** "Again / Hard / Good / Easy" beats every hedged alternative.
3. **Keyboard-first review.** `Space` to reveal, `1-4` to grade. Even beginners benefit when fingers stay on home row.
4. **The deck heatmap.** Our dashboard month-heatmap descends from this.
5. **`Reduce motion` + minimalist mode as explicit, user-overridable preferences**, not buried in OS inheritance.
6. **Leech-style auto-suspend** for items a learner repeatedly fails. For us: if a sign keeps regressing, deprioritize it and offer a "try a different approach" path.
7. **Three-counter density on the deck list** (`New | Learning | Due`). Numbers beat prose.

### AVOID

1. **Zero onboarding.** Anki drops users into an empty deck list — the manual's first instruction is essentially "read the manual." Our beginner audience cannot survive this; onboarding pages 6-9 in `ux-spec.md` are the right counter.
2. **Notes vs Cards exposed to users.** Powerful for authors, devastating for beginners. We collapse Sign ≈ Note ≈ Card.
3. **Forty user-tunable scheduler knobs.** FSRS hides about half; still too many. Ship a single fixed curve (1d → 3d → 7d → 14d) with no v1 tuning.
4. **HTML/CSS card templates.** User-editable styling produces broken decks for everyone but power users. Our lesson cards stay canonical.
5. **Two schedulers side by side.** SM-2 + FSRS is legacy debt; we have none — pick one curve.
6. **"Do not learn if you do not understand" as welcome copy.** Correct advice, terrible onboarding. Our scope-honesty statement frames the same idea as enablement.
7. **Spreadsheet-as-home, no streaks or celebration.** Works for adult intrinsically-motivated learners, hostile to first-semester students. Soft streaks and "Day 4 streak" microcopy are the counter-balance.
8. **Lapse counts surfaced as a card stat.** "You have failed this 7 times" is great data and bad pedagogy. Our mastery tiers abstract over failure counts on purpose.

---

## 10. Open questions / could not verify

1. **AnkiWeb review interface details** — fetch returned no body content. Visual style, page count, and accessibility posture of the browser reviewer unverified.
2. **Default state of `Show next review time above answer buttons`** — community guides imply on-by-default in modern versions; manual treats it as a preference. Default value unconfirmed.
3. **Exact FSRS default parameters** — ~17 parameters fitted on ~727M reviews; not surfaced in UI.
4. **AnkiMobile pricing as of 2026** — last published was ~$25 one-time; not re-verified against the App Store.
5. **Whether AnkiWeb has any onboarding** for new accounts that never used desktop. Likely not, but unverified.
6. **Accessibility conformance** — no public WCAG audit found for any client.
7. **Add-on ecosystem impact** — power-user reviews assume add-ons like "Review Heatmap" or "FSRS Helper" are installed; vanilla UX may differ from what most users see.
8. **Whether 2-button (Again/Good) mode is exposed in UI** — manual mentions it; toggle location not specified.

---

## Sources

[apps.ankiweb.net](https://apps.ankiweb.net) · [getting-started](https://docs.ankiweb.net/getting-started.html) · [studying](https://docs.ankiweb.net/studying.html) · [deck-options](https://docs.ankiweb.net/deck-options.html) · [leeches](https://docs.ankiweb.net/leeches.html) · [editing](https://docs.ankiweb.net/editing.html) · [preferences](https://docs.ankiweb.net/preferences.html) · [github.com/ankitects/anki](https://github.com/ankitects/anki) · [github.com/ankidroid/Anki-Android](https://github.com/ankidroid/Anki-Android) · [Wikipedia: Anki](https://en.wikipedia.org/wiki/Anki_(software)) (FSRS release 23.10, 31 Oct 2023) · [LeanAnki best settings](https://leananki.com/best-settings/)
