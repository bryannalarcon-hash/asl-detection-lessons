/**
 * Seed script — catalog (idempotent) + dev user (always wipe + reseed).
 *
 * Run: `npm run db:seed` (or `npm run db:seed -- --reset-dev-account` for explicit semantics).
 *
 * The script is split into pure data-generator functions (exported for the
 * Vitest unit spec in `frontend/tests/unit/seed.spec.ts`) and a DB I/O entry
 * point that wires them up against Drizzle. Running this file directly hits
 * the DB; importing it does not.
 */
import 'dotenv/config';
import { eq, sql as drizzleSql } from 'drizzle-orm';
import { db, sql as pgClient } from '../backend/src/db/client';
import {
  user,
  lesson,
  sign,
  drillDefinition,
  repLog,
  masteryState,
  streakState,
  notificationPref,
  type NewLesson,
  type NewSign,
  type NewDrillDefinition,
  type NewRepLog,
  type NewMasteryState,
  type MasteryLevel,
  type DrillType,
} from '../backend/src/db/schema';
import { hashPassword } from '../backend/src/lib/passwords';

// === Constants ============================================================

export const DEV_EMAIL = 'dev@asl-pilot.local';
/**
 * Known dev-account password. Re-hashed on every seed run (the plaintext is
 * stable, but each seed produces a fresh hash so we exercise the hasher).
 * Surfaced in the frontend via `frontend/src/lib/dev-credentials.ts` so the
 * sign-in form can render a "Dev account: …" hint when DEV_TOOLS is on.
 */
export const DEV_PASSWORD = 'asl-dev-password';
export const DEV_DISPLAY_NAME = 'Dev User';
export const DEV_CREATED_DAYS_AGO = 75;
export const HEATMAP_DAYS = 75;
export const TOTAL_SIGNS = 96;

// Per PRD §"Seed data shape"
export const MASTERY_BUCKETS: Record<MasteryLevel, number> = {
  mastered: 12,
  known: 9,
  familiar: 8,
  learning: 5,
  new: 4,
};

// === Seeded PRNG (LCG) =====================================================

/**
 * Deterministic seeded LCG so the dev account looks the same across runs.
 * Numerical recipes parameters. Returns [0, 1).
 */
export function makeRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 0x100000000;
  };
}

// === Catalog data ==========================================================

interface LessonSeed {
  title: string;
  category: string;
  signCount: number;
  signs: { gloss: string }[];
}

/**
 * The pilot curriculum IS the Net 4 training vocabulary: the 96 PopSign words
 * (configs/popsign_vocab.json) the classifier is trained on. Glosses are the
 * uppercased clip tokens so `slugify(gloss)` matches the reference clip
 * filename in public/videos/lessons/<slug>.mp4 — every lesson sign has a real
 * demonstration video AND is a class the model can recognize. 12 lessons,
 * 96 signs total.
 */
export const LESSON_CATALOG: LessonSeed[] = [
  {
    title: 'Lesson 1: People',
    category: 'People',
    signCount: 9,
    signs: [
      { gloss: 'MOM' },
      { gloss: 'DAD' },
      { gloss: 'BROTHER' },
      { gloss: 'GRANDMA' },
      { gloss: 'GRANDPA' },
      { gloss: 'AUNT' },
      { gloss: 'UNCLE' },
      { gloss: 'BOY' },
      { gloss: 'GIRL' },
    ],
  },
  {
    title: 'Lesson 2: Animals — Pets & Farm',
    category: 'Animals',
    signCount: 7,
    signs: [
      { gloss: 'DOG' },
      { gloss: 'CAT' },
      { gloss: 'BIRD' },
      { gloss: 'FISH' },
      { gloss: 'HORSE' },
      { gloss: 'COW' },
      { gloss: 'PIG' },
    ],
  },
  {
    title: 'Lesson 3: Animals — Wild',
    category: 'Animals',
    signCount: 7,
    signs: [
      { gloss: 'DUCK' },
      { gloss: 'FROG' },
      { gloss: 'LION' },
      { gloss: 'ELEPHANT' },
      { gloss: 'OWL' },
      { gloss: 'BEE' },
      { gloss: 'MOUSE' },
    ],
  },
  {
    title: 'Lesson 4: Colors',
    category: 'Colors',
    signCount: 8,
    signs: [
      { gloss: 'RED' },
      { gloss: 'BLUE' },
      { gloss: 'GREEN' },
      { gloss: 'YELLOW' },
      { gloss: 'BLACK' },
      { gloss: 'WHITE' },
      { gloss: 'BROWN' },
      { gloss: 'ORANGE' },
    ],
  },
  {
    title: 'Lesson 5: Food & Drink',
    category: 'Food',
    signCount: 9,
    signs: [
      { gloss: 'APPLE' },
      { gloss: 'MILK' },
      { gloss: 'WATER' },
      { gloss: 'CARROT' },
      { gloss: 'CHOCOLATE' },
      { gloss: 'PIZZA' },
      { gloss: 'ICECREAM' },
      { gloss: 'DRINK' },
      { gloss: 'FOOD' },
    ],
  },
  {
    title: 'Lesson 6: Action Words I',
    category: 'Verbs',
    signCount: 8,
    signs: [
      { gloss: 'GO' },
      { gloss: 'GIVE' },
      { gloss: 'LOOK' },
      { gloss: 'SEE' },
      { gloss: 'READ' },
      { gloss: 'LIKE' },
      { gloss: 'HAVE' },
      { gloss: 'MAKE' },
    ],
  },
  {
    title: 'Lesson 7: Action Words II',
    category: 'Verbs',
    signCount: 7,
    signs: [
      { gloss: 'JUMP' },
      { gloss: 'DANCE' },
      { gloss: 'RIDE' },
      { gloss: 'SLEEP' },
      { gloss: 'TALK' },
      { gloss: 'HEAR' },
      { gloss: 'FIND' },
    ],
  },
  {
    title: 'Lesson 8: Feelings',
    category: 'Feelings',
    signCount: 11,
    signs: [
      { gloss: 'HAPPY' },
      { gloss: 'SAD' },
      { gloss: 'MAD' },
      { gloss: 'SICK' },
      { gloss: 'SLEEPY' },
      { gloss: 'THIRSTY' },
      { gloss: 'PRETTY' },
      { gloss: 'CUTE' },
      { gloss: 'HOT' },
      { gloss: 'DIRTY' },
      { gloss: 'FINE' },
    ],
  },
  {
    title: 'Lesson 9: Time',
    category: 'Time',
    signCount: 5,
    signs: [
      { gloss: 'NOW' },
      { gloss: 'MORNING' },
      { gloss: 'NIGHT' },
      { gloss: 'TOMORROW' },
      { gloss: 'YESTERDAY' },
    ],
  },
  {
    title: 'Lesson 10: Places',
    category: 'Places',
    signCount: 5,
    signs: [
      { gloss: 'HOME' },
      { gloss: 'STORE' },
      { gloss: 'BEDROOM' },
      { gloss: 'BATHROOM' },
      { gloss: 'OUTSIDE' },
    ],
  },
  {
    title: 'Lesson 11: Around the House',
    category: 'Household',
    signCount: 9,
    signs: [
      { gloss: 'BED' },
      { gloss: 'CHAIR' },
      { gloss: 'TABLE' },
      { gloss: 'BOOK' },
      { gloss: 'PEN' },
      { gloss: 'SHIRT' },
      { gloss: 'SHOE' },
      { gloss: 'HAT' },
      { gloss: 'TOY' },
    ],
  },
  {
    title: 'Lesson 12: Body & Everyday',
    category: 'Body & Social',
    signCount: 11,
    signs: [
      { gloss: 'EYE' },
      { gloss: 'EAR' },
      { gloss: 'NOSE' },
      { gloss: 'MOUTH' },
      { gloss: 'HEAD' },
      { gloss: 'HAIR' },
      { gloss: 'YES' },
      { gloss: 'NO' },
      { gloss: 'PLEASE' },
      { gloss: 'THANKYOU' },
      { gloss: 'WHO' },
    ],
  },
];

// Pools of plausible target strings to round-robin through.
const HANDSHAPE_POOL = [
  'flat-B',
  '1',
  '5',
  'A',
  'C',
  'O',
  'S',
  'X',
  'Y',
  'L',
  'F',
  'W',
];
const MOVEMENT_POOL = [
  'forward-arc',
  'down-tap',
  'side-sweep',
  'circular',
  'up-flick',
  'twist',
  'wave',
  'palm-shake',
  'pinch-release',
  'shoulder-tap',
];

function slugify(gloss: string): string {
  return gloss.toLowerCase().replace(/_/g, '-');
}

/** Returns a flat list of all sign seeds with their lesson context. */
export function generateAllSigns(): {
  lessonSlug: string;
  lessonOrder: number;
  signSlug: string;
  gloss: string;
  signOrder: number;
}[] {
  const out: ReturnType<typeof generateAllSigns> = [];
  LESSON_CATALOG.forEach((l, lessonIdx) => {
    l.signs.forEach((s, signIdx) => {
      out.push({
        lessonSlug: `lesson-${lessonIdx + 1}`,
        lessonOrder: lessonIdx + 1,
        signSlug: slugify(s.gloss),
        gloss: s.gloss,
        signOrder: signIdx,
      });
    });
  });
  return out;
}

/** Returns the 3 drill targets for a sign (handshape / movement / sign). */
export function generateDrillTargetsForSign(
  signGloss: string,
  globalSignIndex: number
): { drillType: DrillType; targetString: string; orderIndex: number }[] {
  return [
    {
      drillType: 'handshape',
      targetString: HANDSHAPE_POOL[globalSignIndex % HANDSHAPE_POOL.length]!,
      orderIndex: 0,
    },
    {
      drillType: 'movement',
      targetString: MOVEMENT_POOL[globalSignIndex % MOVEMENT_POOL.length]!,
      orderIndex: 1,
    },
    {
      drillType: 'sign',
      targetString: signGloss,
      orderIndex: 2,
    },
  ];
}

// === Mastery distribution ==================================================

/**
 * Assigns mastery levels to 38 of the 96 signs:
 *   12 mastered + 9 known + 8 familiar + 5 learning + 4 new = 38 rows.
 * The remaining signs are NOT in `mastery_state` (they're conceptually
 * "new" / untouched).
 */
export function distributeMastery(
  totalSigns: number = TOTAL_SIGNS
): { signGlobalIndex: number; level: MasteryLevel }[] {
  const out: { signGlobalIndex: number; level: MasteryLevel }[] = [];
  // Build the level list deterministically (no random for this — we want the
  // exact 12/9/8/5/4 split asserted by the unit spec).
  const levels: MasteryLevel[] = [];
  for (let i = 0; i < MASTERY_BUCKETS.mastered; i++) levels.push('mastered');
  for (let i = 0; i < MASTERY_BUCKETS.known; i++) levels.push('known');
  for (let i = 0; i < MASTERY_BUCKETS.familiar; i++) levels.push('familiar');
  for (let i = 0; i < MASTERY_BUCKETS.learning; i++) levels.push('learning');
  for (let i = 0; i < MASTERY_BUCKETS.new; i++) levels.push('new');

  // Spread the 38 touched signs evenly across the catalog so the distribution
  // looks realistic and the chosen indices stay unique for any catalog size.
  const indices: number[] = [];
  for (let i = 0; i < levels.length; i++) {
    indices.push(Math.floor((i * totalSigns) / levels.length));
  }

  for (let i = 0; i < levels.length; i++) {
    out.push({ signGlobalIndex: indices[i]!, level: levels[i]! });
  }
  return out;
}

// === Rep log generation ====================================================

export type RepDay = {
  daysAgo: number; // 0 = today, 74 = oldest
  reps: { signGlobalIndex: number; drillType: DrillType; outcome: 'pass' | 'fail' | 'skip' }[];
};

interface GenerateRepLogOptions {
  totalSigns?: number;
  totalDays?: number;
  rng?: () => number;
}

/**
 * Builds 75 days of varied rep_log entries.
 *
 * Distribution per PRD §"Seed data shape":
 *   - ~40% of days: 0 reps
 *   - ~25%: 1-3 reps (light)
 *   - ~25%: 4-8 reps (moderate)
 *   - ~10%: 9+ reps (heavy)
 *
 * Plus required streak windows:
 *   - 14-day continuous block ending 18 days ago (days 18..31 ago)
 *   - Current 4-day streak (days 0..3 ago)
 *   - Two single-day blips somewhere in the gap
 *
 * Recent 7 days are densest.
 */
export function generateRepLogData(opts: GenerateRepLogOptions = {}): RepDay[] {
  const totalSigns = opts.totalSigns ?? TOTAL_SIGNS;
  const totalDays = opts.totalDays ?? HEATMAP_DAYS;
  const rng = opts.rng ?? makeRandom(0xa51c0ded);

  // Bucket pre-assignment. Build a target distribution per the PRD:
  //   ~40% empty, ~25% light, ~25% moderate, ~10% heavy.
  // We anchor the required streak windows first, then fill the rest.
  type Bucket = 'empty' | 'light' | 'moderate' | 'heavy';
  const buckets: Bucket[] = new Array(totalDays).fill('empty');

  // Required: 14-day streak ending 18 days ago = daysAgo 18..31.
  for (let d = 18; d <= 31; d++) {
    // Mix light/moderate/heavy across the block. Heavy on days 25..28 (mid-block).
    const bucket: Bucket = d >= 25 && d <= 28 ? 'heavy' : d % 2 === 0 ? 'moderate' : 'light';
    buckets[d] = bucket;
  }

  // Required: current 4-day streak ending today = daysAgo 0..3. Densest.
  for (let d = 0; d <= 3; d++) {
    buckets[d] = d <= 1 ? 'heavy' : 'moderate';
  }

  // Required: two single-day blips between the two streak windows.
  // Pick day 10 and day 15 ago.
  buckets[10] = 'light';
  buckets[15] = 'light';

  // Recent 7 days densest: ensure days 4..6 have at least light activity.
  for (let d = 4; d <= 6; d++) {
    if (buckets[d] === 'empty') buckets[d] = 'moderate';
  }

  // Fill remaining empty days with the bulk distribution.
  // Target counts across the full 75 days: empty ≈ 30, light ≈ 19, moderate ≈ 19, heavy ≈ 7.
  // After the required assignments above we've already used ≈
  // heavy: 4 (days 25..28) + 2 (days 0..1) = 6
  // moderate: 7 (days 18..31 odd-evens approx) + 2 (days 2..3) + 3 (days 4..6) ~= 12
  // light: ~7 within 18..31 + 2 blips = 9
  // empty: ~57 remaining
  // We'll randomly upgrade some of those empty days to hit the right totals.
  const targetEmpty = Math.floor(totalDays * 0.4); // 30
  const targetLight = Math.floor(totalDays * 0.25); // 18 (so we round nicely)
  const targetModerate = Math.floor(totalDays * 0.25); // 18
  const targetHeavy = totalDays - targetEmpty - targetLight - targetModerate; // 9

  const counts = { empty: 0, light: 0, moderate: 0, heavy: 0 } as Record<Bucket, number>;
  for (const b of buckets) counts[b]++;

  const targets = {
    empty: targetEmpty,
    light: targetLight,
    moderate: targetModerate,
    heavy: targetHeavy,
  } as Record<Bucket, number>;

  // Walk days in random order and re-bucket empty days until we hit targets.
  const emptyIndices: number[] = [];
  for (let i = 0; i < totalDays; i++) if (buckets[i] === 'empty') emptyIndices.push(i);
  // Fisher-Yates shuffle with our RNG
  for (let i = emptyIndices.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    const t = emptyIndices[i]!;
    emptyIndices[i] = emptyIndices[j]!;
    emptyIndices[j] = t;
  }

  for (const idx of emptyIndices) {
    if (counts.heavy < targets.heavy) {
      buckets[idx] = 'heavy';
      counts.heavy++;
      counts.empty--;
      continue;
    }
    if (counts.moderate < targets.moderate) {
      buckets[idx] = 'moderate';
      counts.moderate++;
      counts.empty--;
      continue;
    }
    if (counts.light < targets.light) {
      buckets[idx] = 'light';
      counts.light++;
      counts.empty--;
      continue;
    }
    // else keep as empty
  }

  // Now turn buckets into rep counts and emit RepDay[].
  const drillTypes: DrillType[] = ['handshape', 'movement', 'sign'];
  const result: RepDay[] = [];
  for (let d = 0; d < totalDays; d++) {
    const bucket = buckets[d]!;
    let nReps = 0;
    switch (bucket) {
      case 'empty':
        nReps = 0;
        break;
      case 'light':
        nReps = 1 + Math.floor(rng() * 3); // 1..3
        break;
      case 'moderate':
        nReps = 4 + Math.floor(rng() * 5); // 4..8
        break;
      case 'heavy':
        nReps = 9 + Math.floor(rng() * 6); // 9..14
        break;
    }
    const reps: RepDay['reps'] = [];
    for (let r = 0; r < nReps; r++) {
      const signGlobalIndex = Math.floor(rng() * totalSigns);
      const drillType = drillTypes[Math.floor(rng() * drillTypes.length)]!;
      // 70% pass, 20% fail, 10% skip
      const roll = rng();
      const outcome: 'pass' | 'fail' | 'skip' =
        roll < 0.7 ? 'pass' : roll < 0.9 ? 'fail' : 'skip';
      reps.push({ signGlobalIndex, drillType, outcome });
    }
    result.push({ daysAgo: d, reps });
  }
  return result;
}

/** Total rep_log row count (sum of reps across all days). */
export function repDaysTotal(days: RepDay[]): number {
  return days.reduce((acc, d) => acc + d.reps.length, 0);
}

/** Distribution buckets for the rep log days (used by the unit spec). */
export function repDaysDistribution(days: RepDay[]): {
  empty: number;
  light: number;
  moderate: number;
  heavy: number;
} {
  let empty = 0,
    light = 0,
    moderate = 0,
    heavy = 0;
  for (const d of days) {
    const n = d.reps.length;
    if (n === 0) empty++;
    else if (n <= 3) light++;
    else if (n <= 8) moderate++;
    else heavy++;
  }
  return { empty, light, moderate, heavy };
}

// === DB writers ============================================================

function utcDateNDaysAgo(n: number): Date {
  const d = new Date();
  d.setUTCHours(0, 0, 0, 0);
  d.setUTCDate(d.getUTCDate() - n);
  return d;
}

function todayYMD(): string {
  const d = new Date();
  const yyyy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(d.getUTCDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

async function upsertCatalog(): Promise<{
  lessonIdBySlug: Map<string, string>;
  signIdByGlobalIdx: Map<number, string>;
  drillCount: number;
}> {
  const lessonIdBySlug = new Map<string, string>();
  const signIdByGlobalIdx = new Map<number, string>();
  let drillCount = 0;

  // 1. Lessons
  for (let i = 0; i < LESSON_CATALOG.length; i++) {
    const l = LESSON_CATALOG[i]!;
    const slug = `lesson-${i + 1}`;
    const values: NewLesson = {
      slug,
      title: l.title,
      category: l.category,
      signCount: l.signCount,
      orderIndex: i + 1,
    };
    const existing = await db.select().from(lesson).where(eq(lesson.slug, slug)).limit(1);
    if (existing.length === 0) {
      const inserted = await db.insert(lesson).values(values).returning();
      lessonIdBySlug.set(slug, inserted[0]!.id);
    } else {
      // Update title/category/order/signCount in case the catalog changed.
      await db
        .update(lesson)
        .set({
          title: values.title,
          category: values.category,
          signCount: values.signCount,
          orderIndex: values.orderIndex,
        })
        .where(eq(lesson.slug, slug));
      lessonIdBySlug.set(slug, existing[0]!.id);
    }
  }

  // 2. Signs — wipe first so signs dropped from the catalog don't linger
  // (a prior catalog's signs would otherwise stay attached to their lesson).
  // drillDefinition, masteryState and repLog all cascade-delete off sign, so
  // this clears the whole sign graph; mastery/rep are reseeded below.
  await db.delete(sign);
  const allSigns = generateAllSigns();
  for (let g = 0; g < allSigns.length; g++) {
    const s = allSigns[g]!;
    const lessonId = lessonIdBySlug.get(s.lessonSlug);
    if (!lessonId) throw new Error(`Missing lesson id for ${s.lessonSlug}`);
    const values: NewSign = {
      slug: s.signSlug,
      englishGloss: s.gloss,
      lessonId,
      orderIndex: s.signOrder,
    };
    const existing = await db.select().from(sign).where(eq(sign.slug, s.signSlug)).limit(1);
    if (existing.length === 0) {
      const inserted = await db.insert(sign).values(values).returning();
      signIdByGlobalIdx.set(g, inserted[0]!.id);
    } else {
      await db
        .update(sign)
        .set({
          englishGloss: values.englishGloss,
          lessonId: values.lessonId,
          orderIndex: values.orderIndex,
        })
        .where(eq(sign.slug, s.signSlug));
      signIdByGlobalIdx.set(g, existing[0]!.id);
    }
  }

  // 3. Drill definitions — wipe + reinsert for each sign so target pools stay in sync.
  for (let g = 0; g < allSigns.length; g++) {
    const s = allSigns[g]!;
    const signId = signIdByGlobalIdx.get(g);
    if (!signId) throw new Error(`Missing sign id at index ${g}`);
    await db.delete(drillDefinition).where(eq(drillDefinition.signId, signId));
    const drills = generateDrillTargetsForSign(s.gloss, g);
    const rows: NewDrillDefinition[] = drills.map((d) => ({
      signId,
      drillType: d.drillType,
      targetString: d.targetString,
      orderIndex: d.orderIndex,
    }));
    if (rows.length > 0) {
      await db.insert(drillDefinition).values(rows);
      drillCount += rows.length;
    }
  }

  return { lessonIdBySlug, signIdByGlobalIdx, drillCount };
}

async function upsertDevUser(): Promise<string> {
  const createdAt = utcDateNDaysAgo(DEV_CREATED_DAYS_AGO);
  // Always re-hash on each seed run. The plaintext is fixed (DEV_PASSWORD),
  // but each run produces a fresh hash — exercises the hasher and ensures
  // the stored hash stays in sync with the current password-lib implementation.
  const passwordHash = await hashPassword(DEV_PASSWORD);
  const existing = await db
    .select()
    .from(user)
    .where(drizzleSql`lower(${user.email}) = ${DEV_EMAIL.toLowerCase()}`)
    .limit(1);
  if (existing.length > 0) {
    const id = existing[0]!.id;
    // Reset created_at + verified_at to keep the dev user looking 75 days old.
    await db
      .update(user)
      .set({
        displayName: DEV_DISPLAY_NAME,
        passwordHash,
        createdAt,
        emailVerifiedAt: createdAt,
      })
      .where(eq(user.id, id));
    return id;
  }
  const inserted = await db
    .insert(user)
    .values({
      email: DEV_EMAIL,
      displayName: DEV_DISPLAY_NAME,
      passwordHash,
      createdAt,
      emailVerifiedAt: createdAt,
    })
    .returning();
  return inserted[0]!.id;
}

async function wipeDevUserState(userId: string): Promise<void> {
  await db.delete(repLog).where(eq(repLog.userId, userId));
  await db.delete(masteryState).where(eq(masteryState.userId, userId));
  await db.delete(streakState).where(eq(streakState.userId, userId));
  await db.delete(notificationPref).where(eq(notificationPref.userId, userId));
}

async function seedMasteryForDevUser(
  userId: string,
  signIdByGlobalIdx: Map<number, string>
): Promise<number> {
  const dist = distributeMastery(TOTAL_SIGNS);
  const rows: NewMasteryState[] = [];
  for (const entry of dist) {
    const signId = signIdByGlobalIdx.get(entry.signGlobalIndex);
    if (!signId) continue;
    // last_practiced_at: between 1 and 30 days ago, scaled by level (mastered = recent).
    const ageDays =
      entry.level === 'mastered'
        ? 2
        : entry.level === 'known'
          ? 5
          : entry.level === 'familiar'
            ? 10
            : entry.level === 'learning'
              ? 18
              : 30;
    rows.push({
      userId,
      signId,
      level: entry.level,
      lastPracticedAt: utcDateNDaysAgo(ageDays),
      advanceCount:
        entry.level === 'mastered'
          ? 6
          : entry.level === 'known'
            ? 4
            : entry.level === 'familiar'
              ? 2
              : entry.level === 'learning'
                ? 1
                : 0,
      regressCount: 0,
    });
  }
  if (rows.length > 0) {
    await db.insert(masteryState).values(rows);
  }
  return rows.length;
}

async function seedRepLogForDevUser(
  userId: string,
  signIdByGlobalIdx: Map<number, string>
): Promise<number> {
  const days = generateRepLogData();
  const allRows: NewRepLog[] = [];
  for (const day of days) {
    if (day.reps.length === 0) continue;
    const baseDay = utcDateNDaysAgo(day.daysAgo);
    day.reps.forEach((rep, idx) => {
      const signId = signIdByGlobalIdx.get(rep.signGlobalIndex);
      if (!signId) return;
      // Spread reps across the day so they're not all at midnight UTC.
      const ts = new Date(baseDay);
      ts.setUTCHours(8 + Math.floor(idx % 12), (idx * 7) % 60, (idx * 13) % 60, 0);
      allRows.push({
        userId,
        signId,
        drillType: rep.drillType,
        outcome: rep.outcome,
        source: 'self-report',
        hintRequested: false,
        createdAt: ts,
      });
    });
  }
  // Batch insert (chunked to avoid query-size issues)
  const chunkSize = 200;
  for (let i = 0; i < allRows.length; i += chunkSize) {
    const chunk = allRows.slice(i, i + chunkSize);
    if (chunk.length > 0) await db.insert(repLog).values(chunk);
  }
  return allRows.length;
}

async function seedStreakAndPrefs(userId: string): Promise<void> {
  await db.insert(streakState).values({
    userId,
    currentStreakDays: 4,
    longestStreakDays: 14,
    freezesRemaining: 2,
    lastPracticeDate: todayYMD(),
  });
  await db.insert(notificationPref).values({
    userId,
    dailyReminderTime: '19:00:00',
    weeklySummaryEnabled: true,
    streakAtRiskEnabled: false,
  });
}

// === Entry point ===========================================================

export async function runSeed(): Promise<{
  lessons: number;
  signs: number;
  drills: number;
  masteryRows: number;
  repLogRows: number;
}> {
  // The --reset-dev-account flag is documented for explicit semantics, but
  // resetting the dev user is the DEFAULT behaviour of this script.
  const args = process.argv.slice(2);
  const hasFlag = args.includes('--reset-dev-account');
  if (hasFlag) {
    console.log('[seed] --reset-dev-account flag detected (default behaviour anyway)');
  }

  console.log('[seed] upserting catalog...');
  const { lessonIdBySlug, signIdByGlobalIdx, drillCount } = await upsertCatalog();
  console.log(`[seed]   ${lessonIdBySlug.size} lessons, ${signIdByGlobalIdx.size} signs, ${drillCount} drill definitions`);

  console.log('[seed] upserting dev user...');
  const devUserId = await upsertDevUser();

  console.log('[seed] wiping dev user state (rep_log, mastery_state, streak_state, notification_pref)...');
  await wipeDevUserState(devUserId);

  console.log('[seed] seeding mastery_state...');
  const masteryRows = await seedMasteryForDevUser(devUserId, signIdByGlobalIdx);

  console.log('[seed] seeding rep_log...');
  const repLogRows = await seedRepLogForDevUser(devUserId, signIdByGlobalIdx);

  console.log('[seed] seeding streak_state + notification_pref...');
  await seedStreakAndPrefs(devUserId);

  return {
    lessons: lessonIdBySlug.size,
    signs: signIdByGlobalIdx.size,
    drills: drillCount,
    masteryRows,
    repLogRows,
  };
}

const isMainModule = (() => {
  try {
    // ESM main detection (works with tsx/node)
    if (typeof process !== 'undefined' && process.argv[1]) {
      // Always run when invoked directly via `tsx scripts/seed-dev-user.ts`.
      return process.argv[1].includes('seed-dev-user');
    }
  } catch {
    /* ignore */
  }
  return false;
})();

if (isMainModule) {
  runSeed()
    .then(async (summary) => {
      console.log('\n[seed] === summary ===');
      console.log(`[seed]   lessons:      ${summary.lessons}`);
      console.log(`[seed]   signs:        ${summary.signs}`);
      console.log(`[seed]   drills:       ${summary.drills}`);
      console.log(`[seed]   mastery rows: ${summary.masteryRows}`);
      console.log(`[seed]   rep_log rows: ${summary.repLogRows}`);
      await pgClient.end({ timeout: 5 });
      process.exit(0);
    })
    .catch(async (err) => {
      console.error('[seed] failed:', err);
      try {
        await pgClient.end({ timeout: 5 });
      } catch {
        /* ignore */
      }
      process.exit(1);
    });
}
