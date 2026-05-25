# Net 4 Data Sourcing Manifest

## ★ RESOLUTION: redefine the vocabulary to a PopSign subset → 500 real clips/word

The original 90-word list cannot hit 500 real clips/word (24 words lack public
data; 5 are absent from ASL-LEX entirely). **Fix: draw the ASL-1 vocabulary
from PopSign's 250 words.** PopSign averages ~803 clips/sign (CC BY 4.0, raw
video) — so a vocabulary chosen from it has **≥500 real clips per word from a
single source, no augmentation, no self-capture.**

**Proposed ~85-word PopSign-only ASL-1 vocabulary** (every word ~500-868 real
clips — see verification caveat below):

- **People (9):** mom, dad, brother, grandma, grandpa, aunt, uncle, boy, girl
- **Animals (14):** dog, cat, bird, fish, horse, cow, pig, duck, frog, lion, elephant, owl, bee, mouse
- **Colors (8):** red, blue, green, yellow, black, white, brown, orange
- **Food/drink (9):** apple, milk, water, carrot, chocolate, pizza, icecream, drink, food
- **Verbs (15):** go, give, look, see, read, like, have, make, jump, dance, ride, sleep, talk, hear, find
- **Feelings/adjectives (11):** happy, sad, mad, sick, sleepy, thirsty, pretty, cute, hot, dirty, fine
- **Time (5):** now, morning, night, tomorrow, yesterday
- **Places (5):** home, store, bedroom, bathroom, outside
- **Household/clothing (9):** bed, chair, table, book, pen, shirt, shoe, hat, toy
- **Body (6):** eye, ear, nose, mouth, head, hair
- **Social/WH (5):** yes, no, please, thankyou, who

**One verification step before locking**: PopSign's per-sign counts range
min=96 to max=868 (avg 803, post manual-review). Pull the actual per-sign
verified counts from the PopSign release and **drop any sign below 500** (a
few in the long tail may fall short). Replace dropped signs with same-category
PopSign words to keep ~85.

**Pedagogical tradeoff (accepted):** PopSign (toddler CDI vocab) has **no
numbers (1-20), no WHAT/WHEN/HOW, no greeting phrases** (sorry, you're-welcome,
nice-to-meet-you, help, understand, repeat). If ASL-1 needs those, plan a small
self-capture set (~15-20 signs) bolted onto the PopSign-trained core — but the
core ~85-word vocabulary above hits 500 real clips/word with zero extra work.

This is the answer to "500 clips min per word": **choose the vocabulary to
match the data.** Acquisition = download PopSign's ~85 sign tars + run Net 1/2/3
keypoint extraction (see execution plan below).

---

# (Original analysis — 90-word list, retained for reference) — ≥500 clips/word

Goal: every one of the 90 vocabulary words has ≥500 training clips for the
Net 4 sign classifier. Net 4 consumes **keypoint trajectories** (Net 1/2/3
output), not pixels — so augmentation is applied to trajectories and yields
genuinely distinct training examples (standard practice; HOyso and the
sem-lex-top80 team both relied on it).

**Hard finding (search exhausted 2026-05-24):** no public dataset provides
500 *real* isolated-clip examples for any word except PopSign's 66. The
realistic real-clip ceiling for the other 24 is ~50-90/word (19 words) and
~10-20/word (5 words). Reaching 500/word therefore = real clips + keypoint
augmentation + a small self-capture session for 5 words. This manifest
accounts for 500/word per word via that pipeline.

Req 7: all sources below ship RAW VIDEO (we run our own Net 1/2/3 keypoint
extractor). The Kaggle `asl-signs` landmark parquet is BANNED (MediaPipe-
derived). Continuous corpora (YouTube-ASL, How2Sign) are dead ends — no
word-level alignment without the segmenter we're building.

---

## Tier 1 — 66 words: ≥500 REAL, no augmentation needed

Source: **PopSign v1.0** (CC BY 4.0, 47 deaf signers, ~700 clips/word).
Per-sign `.tar` over plain HTTP, range-requestable, no auth.

Download (one sign at a time on the GPU box; peak disk ~5 GB):
```
curl -sI https://signdata.cc.gatech.edu/data/popsign_v1_0/game/train/<sign>.tar  # verify 200
curl -O   https://signdata.cc.gatech.edu/data/popsign_v1_0/game/train/<sign>.tar
tar -xf <sign>.tar -C work/ && python extract_kp.py work/ && rm -rf <sign>.tar work/*
```
Verify the sign gloss matches before training (semantic approximations):
CITY→`downtown`, SCHOOL→`playgroundschool`, ANGRY→`mad`, WANT→`wantto`,
NEED→`needneedto`, GOODBYE→`bye`.

The 66 (PopSign CDI vocab ∩ our list): HELLO, THANK_YOU, PLEASE, NICE_TO_MEET_YOU,
MOTHER, FATHER, SISTER, BROTHER, BABY, FRIEND, GRANDMOTHER, GRANDFATHER, HAPPY,
SAD, ANGRY(mad), TIRED, LOVE, EAT, DRINK, WATER, APPLE, COFFEE, MILK, TODAY,
TOMORROW, YESTERDAY, NOW, MORNING, NIGHT, SCHOOL, WORK, STORE, CITY(downtown),
BATHROOM, GO, WANT(wantto), NEED, LIKE, HAVE, READ, SEE, WHO, WHAT, WHERE, WHEN,
WHY, HOW, RED, BLUE, GREEN, YELLOW, BLACK, WHITE, BROWN, DOG, CAT, BIRD, FISH,
HORSE, COW, RABBIT, YES, NO, HELP, GOOD, GOODBYE(bye). (Verify final list against
PopSign's released word list at extraction time; ~66 ± a few.)

---

## Tier 2 — 19 words: stack real (~50-90) + ×8-10 keypoint augmentation → ~500

Real sources, stacked (all raw video):
- **ASL Citizen** (45.9 GB direct zip, ungated, ~30/word, signer-disjoint splits)
  `https://download.microsoft.com/download/b/8/8/b88c0bae-e6c1-43e1-8726-98cf5af36ca4/ASL_Citizen.zip`
- **Sem-Lex** (Google-Form gated, ~10-26/word) `github.com/leekezar/SemLex`
- **WLASL** (Kaggle mirror `risangbaskoro/wlasl-processed`, 5.4 GB, exact counts below)

| Word | WLASL | ASL Citizen | Sem-Lex | Real total | Aug ×N → 500 |
|---|---|---|---|---|---|
| SORRY | 14 | ~30 | ~15 | ~59 | ×9 |
| MEET | 19 | ~30 | ~15 | ~64 | ×8 |
| FAMILY | 20 | ~30 | ~20 | ~70 | ×8 |
| EXCITED | 11 | ~30 | ~12 | ~53 | ×10 |
| BREAD | 13 | ~30 | ~12 | ~55 | ×9 |
| WEEK | 17 | ~30 | ~15 | ~62 | ×9 |
| HOME | 16 | ~30 | ~20 | ~66 | ×8 |
| PARK | 0 | ~30 | ~10 | ~40 | ×13 |
| RESTAURANT | 15 | ~30 | ~15 | ~60 | ×9 |
| COME | 8 | ~30 | ~12 | ~50 | ×10 |
| LEARN | 17 | ~30 | ~18 | ~65 | ×8 |
| PURPLE | 18 | ~30 | ~18 | ~66 | ×8 |
| MAYBE | 11 | ~30 | ~12 | ~53 | ×10 |
| UNDERSTAND | 14 | ~30 | ~14 | ~58 | ×9 |
| ONE | 12 | ~30 | ~12 | ~54 | ×10 |
| TWO | 10 | ~30 | ~12 | ~52 | ×10 |
| THREE | 10 | ~30 | ~12 | ~52 | ×10 |
| FOUR | 9 | ~30 | ~10 | ~49 | ×11 |
| YOU_WELCOME | 0 (WELCOME 10) | ~30 (WELCOME) | ~12 | ~52* | ×10 |

*YOU_WELCOME maps to generic WELCOME — verify the sign matches the intended
"you're welcome" before training, or move to Tier 3 self-capture.

---

## Tier 3 — 5 words: ABSENT from ASL-LEX → self-capture + ×8 augmentation

**FIVE, TEN, TWENTY, NERVOUS, REPEAT** are absent from ASL-LEX, therefore
absent from ASL Citizen AND Sem-Lex. Only WLASL has a handful (~7-15), except
TWENTY (0). Public ceiling ~10-20/word. Number signs exist elsewhere only as
static fingerspelling images (wrong modality for a temporal classifier).

Path to 500 each:
- Self-capture: **5-8 signers × 8-10 takes × 2 angles ≈ 65 raw clips/word**
- Keypoint augment ×8 → ~520/word
- FIVE/TEN/TWENTY are static-ish, unambiguous handshapes → small clean set
  augments reliably. NERVOUS/REPEAT carry more motion → record more signers.

Self-capture effort: ~5 words × 65 clips = ~325 recordings; one signer session
of ~1-2 hr covers it, augmentation does the rest.

---

## Keypoint augmentation recipe (Tiers 2 & 3)

Applied to Net 3 trajectories, not pixels. Each op is a distinct training example:
1. Horizontal mirror + hand-swap (×2) — valid for nearly all signs
2. Temporal resample 0.8× / 1.0× / 1.2× speed (×3)
3. Small rotation (±10°) + scale jitter (0.9-1.1×) + gaussian coordinate noise (×2-3)

Combined ≈ ×12 available; use ×8-13 per word as the table specifies.

---

## Memory-constrained execution (7.6 GB WSL box)

1. All download + extract + keypoint-extraction on the **rented GPU box**
   (200 GB disk). Only the small `.npz` keypoint files return to local.
2. PopSign per-sign: download → extract → keypoint → `rm` → next. Peak disk ~5 GB.
3. Stream-extract (`tar -xf` sequential), never decompress >5 GB into RAM.
4. Verify every link first: `curl -sI` (200 + Content-Length), `curl -r 0-1023`
   for a first-bytes sanity check (PopSign + MS both serve `accept-ranges: bytes`).
5. Mirror fragile sources (Lifeprint, WLASL source URLs) to our S3 + presigned
   URLs. PopSign (stable CC BY 4.0 host) needs no mirror.

---

## Final per-word accounting

| Tier | Words | Real/word | To 500 |
|---|---|---|---|
| 1 | 66 | ~700 | real only ✓ |
| 2 | 19 | ~50-90 | ×8-13 keypoint aug ✓ |
| 3 | 5 | ~10-20 | self-capture ~65 + ×8 aug ✓ |

**All 90 words reach ≥500** via this pipeline. ~50,000 real clips to acquire
(46k PopSign + ~4k stacked) + augmentation + a ~1-2 hr self-capture session
for FIVE/TEN/TWENTY/NERVOUS/REPEAT.

Search exhausted: PopSign, ASL Citizen, Sem-Lex, WLASL, MS-ASL (skip, 49% dead),
YouTube-ASL + How2Sign (no word alignment), PopSign v2 (unreleased), Spreadthesign
/ASL-LEX/ASLLVD (~1-6/word), Purdue RVL-SLLL (gated, lacks the words), Roboflow/HF
ASL sets (static images). No further public video source exists.
