import { Hono } from 'hono';
import { and, desc, eq, inArray, max, sql } from 'drizzle-orm';
import { z } from 'zod';
import { db } from '../db/client';
import {
  drillTypeEnum,
  lesson,
  masteryState,
  repLog,
  repOutcomeEnum,
  repSourceEnum,
  sign,
  streakState,
  type MasteryLevel,
} from '../db/schema';
import { getSessionUserId } from '../lib/session';

const app = new Hono();

// PRD: total signs constant for the scaffold
const TOTAL_SIGNS = 75;

// PRD: 75-day heatmap window
const HEATMAP_DAYS = 75;

// === Schemas ===

const repBodySchema = z.object({
  signId: z.string().uuid(),
  drillType: z.enum(drillTypeEnum.enumValues),
  outcome: z.enum(repOutcomeEnum.enumValues),
  source: z.enum(repSourceEnum.enumValues),
  hintRequested: z.boolean().optional().default(false),
});

// === Mastery state machine ===

const MASTERY_ORDER: MasteryLevel[] = ['new', 'learning', 'familiar', 'known', 'mastered'];

function advance(level: MasteryLevel): MasteryLevel {
  const idx = MASTERY_ORDER.indexOf(level);
  if (idx < 0 || idx === MASTERY_ORDER.length - 1) return 'mastered';
  return MASTERY_ORDER[idx + 1]!;
}

function regress(level: MasteryLevel): MasteryLevel {
  const idx = MASTERY_ORDER.indexOf(level);
  if (idx <= 0) return 'new';
  return MASTERY_ORDER[idx - 1]!;
}

// === Helpers ===

function todayDateString(): string {
  // YYYY-MM-DD in UTC. The dev DB and frontend both treat dates as wall-clock-naive
  // for now; per the PRD, no timezone story exists yet.
  const d = new Date();
  const yyyy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(d.getUTCDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

/**
 * Heatmap intensity bucket. Calibrated to the seed distribution and the
 * "30+ reps = highest tier" rule: a busy day should cap out, casual days
 * should be visibly mid-range, very sparse days should still register as
 * non-empty. Five tiers (0 = no practice) so the visual scale matches
 * GitHub-style ramps.
 */
function intensityForCount(count: number): 0 | 1 | 2 | 3 | 4 {
  if (count <= 0) return 0;
  if (count <= 9) return 1;
  if (count <= 19) return 2;
  if (count <= 29) return 3;
  return 4;
}

// === POST /api/progress/rep ===

app.post('/rep', async (c) => {
  const userId = getSessionUserId(c);
  if (!userId) return c.json({ error: 'Unauthorized' }, 401);

  let body: unknown;
  try {
    body = await c.req.json();
  } catch {
    return c.json({ error: 'Invalid JSON body' }, 400);
  }

  const parsed = repBodySchema.safeParse(body);
  if (!parsed.success) {
    return c.json({ error: 'Invalid body', details: parsed.error.flatten() }, 400);
  }

  const { signId, drillType, outcome, source, hintRequested } = parsed.data;

  // 1. Insert the rep_log row.
  await db.insert(repLog).values({
    userId,
    signId,
    drillType,
    outcome,
    source,
    hintRequested,
  });

  // 2. Read current mastery_state row (or default to 'new').
  const existingRows = await db
    .select()
    .from(masteryState)
    .where(and(eq(masteryState.userId, userId), eq(masteryState.signId, signId)))
    .limit(1);
  const existing = existingRows[0];
  const currentLevel: MasteryLevel = existing?.level ?? 'new';
  const currentAdvance = existing?.advanceCount ?? 0;
  const currentRegress = existing?.regressCount ?? 0;

  // 3. Compute next state.
  let nextLevel: MasteryLevel = currentLevel;
  let nextAdvance = currentAdvance;
  let nextRegress = currentRegress;
  if (outcome === 'pass') {
    nextLevel = advance(currentLevel);
    nextAdvance = currentAdvance + 1;
  } else if (outcome === 'fail') {
    nextLevel = regress(currentLevel);
    nextRegress = currentRegress + 1;
  }
  // 'skip' is a no-op on level/counts but still updates last_practiced_at below.

  const now = new Date();

  // 4. Upsert mastery_state.
  const upserted = await db
    .insert(masteryState)
    .values({
      userId,
      signId,
      level: nextLevel,
      lastPracticedAt: now,
      advanceCount: nextAdvance,
      regressCount: nextRegress,
    })
    .onConflictDoUpdate({
      target: [masteryState.userId, masteryState.signId],
      set: {
        level: nextLevel,
        lastPracticedAt: now,
        advanceCount: nextAdvance,
        regressCount: nextRegress,
      },
    })
    .returning();

  // 5. Streak update: only on `pass`, and only if last_practice_date != today.
  if (outcome === 'pass') {
    const today = todayDateString();
    const existingStreakRows = await db
      .select()
      .from(streakState)
      .where(eq(streakState.userId, userId))
      .limit(1);
    const existingStreak = existingStreakRows[0];

    if (!existingStreak) {
      await db.insert(streakState).values({
        userId,
        currentStreakDays: 1,
        longestStreakDays: 1,
        freezesRemaining: 2,
        lastPracticeDate: today,
      });
    } else if (existingStreak.lastPracticeDate !== today) {
      // Determine if today extends the streak (yesterday was last) or resets it.
      const yesterday = new Date();
      yesterday.setUTCDate(yesterday.getUTCDate() - 1);
      const yyyy = yesterday.getUTCFullYear();
      const mm = String(yesterday.getUTCMonth() + 1).padStart(2, '0');
      const dd = String(yesterday.getUTCDate()).padStart(2, '0');
      const yesterdayStr = `${yyyy}-${mm}-${dd}`;

      const continues = existingStreak.lastPracticeDate === yesterdayStr;
      const nextCurrent = continues ? existingStreak.currentStreakDays + 1 : 1;
      const nextLongest = Math.max(existingStreak.longestStreakDays, nextCurrent);

      await db
        .update(streakState)
        .set({
          currentStreakDays: nextCurrent,
          longestStreakDays: nextLongest,
          lastPracticeDate: today,
        })
        .where(eq(streakState.userId, userId));
    }
  }

  return c.json({ masteryState: upserted[0] });
});

// === GET /api/progress/dashboard ===

app.get('/dashboard', async (c) => {
  const userId = getSessionUserId(c);
  if (!userId) return c.json({ error: 'Unauthorized' }, 401);

  // --- masterySummary ---
  const masteryByLevelRows = await db
    .select({
      level: masteryState.level,
      count: sql<number>`COUNT(*)::int`,
    })
    .from(masteryState)
    .where(eq(masteryState.userId, userId))
    .groupBy(masteryState.level);

  const summaryCounts = {
    new: 0,
    learning: 0,
    familiar: 0,
    known: 0,
    mastered: 0,
  } as Record<MasteryLevel, number>;
  for (const row of masteryByLevelRows) {
    summaryCounts[row.level] = row.count;
  }
  const touched =
    summaryCounts.new +
    summaryCounts.learning +
    summaryCounts.familiar +
    summaryCounts.known +
    summaryCounts.mastered;
  // PRD: any unstarted signs (total - touched) are conceptually "new" for the
  // mastery bar; rather than fold them in here, we expose the touched
  // breakdown and a total so the frontend can compute "X / 75 mastered" or
  // similar from explicit fields.
  const masterySummary = {
    ...summaryCounts,
    touched,
    total: TOTAL_SIGNS,
  };

  // --- heatmap (last HEATMAP_DAYS days, inclusive of today) ---
  // Build YYYY-MM-DD buckets in UTC. Empty days get drillCount: 0.
  const today = new Date();
  today.setUTCHours(0, 0, 0, 0);
  const startDate = new Date(today);
  startDate.setUTCDate(startDate.getUTCDate() - (HEATMAP_DAYS - 1));

  const repCountsRows = await db
    .select({
      day: sql<string>`to_char(${repLog.createdAt} AT TIME ZONE 'UTC', 'YYYY-MM-DD')`,
      count: sql<number>`COUNT(*)::int`,
    })
    .from(repLog)
    .where(
      and(
        eq(repLog.userId, userId),
        sql`${repLog.createdAt} >= ${startDate.toISOString()}`,
      ),
    )
    .groupBy(sql`to_char(${repLog.createdAt} AT TIME ZONE 'UTC', 'YYYY-MM-DD')`);

  const countByDay = new Map<string, number>();
  for (const row of repCountsRows) {
    countByDay.set(row.day, row.count);
  }

  const heatmap: { date: string; drillCount: number; intensity: 0 | 1 | 2 | 3 | 4 }[] = [];
  for (let i = 0; i < HEATMAP_DAYS; i++) {
    const d = new Date(startDate);
    d.setUTCDate(startDate.getUTCDate() + i);
    const yyyy = d.getUTCFullYear();
    const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
    const dd = String(d.getUTCDate()).padStart(2, '0');
    const key = `${yyyy}-${mm}-${dd}`;
    const drillCount = countByDay.get(key) ?? 0;
    heatmap.push({ date: key, drillCount, intensity: intensityForCount(drillCount) });
  }

  // --- recentLessons (top 5 by most-recent rep, with mastered counts) ---
  const recentLessonRows = await db
    .select({
      lessonId: lesson.id,
      slug: lesson.slug,
      title: lesson.title,
      signCount: lesson.signCount,
      lastPracticedAt: max(repLog.createdAt),
    })
    .from(repLog)
    .innerJoin(sign, eq(sign.id, repLog.signId))
    .innerJoin(lesson, eq(lesson.id, sign.lessonId))
    .where(eq(repLog.userId, userId))
    .groupBy(lesson.id, lesson.slug, lesson.title, lesson.signCount)
    .orderBy(desc(max(repLog.createdAt)))
    .limit(5);

  // For each, count how many signs in that lesson are at level 'mastered'.
  const recentLessons = await Promise.all(
    recentLessonRows.map(async (row) => {
      const masteredRows = await db
        .select({ count: sql<number>`COUNT(*)::int` })
        .from(masteryState)
        .innerJoin(sign, eq(sign.id, masteryState.signId))
        .where(
          and(
            eq(masteryState.userId, userId),
            eq(sign.lessonId, row.lessonId),
            eq(masteryState.level, 'mastered'),
          ),
        );
      const masteredCount = masteredRows[0]?.count ?? 0;
      return {
        slug: row.slug,
        title: row.title,
        signCount: row.signCount,
        masteredCount,
        lastPracticedAt: row.lastPracticedAt,
      };
    }),
  );

  // --- streak ---
  const streakRows = await db
    .select()
    .from(streakState)
    .where(eq(streakState.userId, userId))
    .limit(1);
  const streakRow = streakRows[0];
  const streak = streakRow
    ? {
        currentStreakDays: streakRow.currentStreakDays,
        longestStreakDays: streakRow.longestStreakDays,
        freezesRemaining: streakRow.freezesRemaining,
      }
    : {
        currentStreakDays: 0,
        longestStreakDays: 0,
        freezesRemaining: 2,
      };

  return c.json({
    masterySummary,
    heatmap,
    recentLessons,
    streak,
  });
});

// === GET /api/progress/day/:date ===

const dateParamSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);

app.get('/day/:date', async (c) => {
  const userId = getSessionUserId(c);
  if (!userId) return c.json({ error: 'Unauthorized' }, 401);

  const date = c.req.param('date');
  if (!dateParamSchema.safeParse(date).success) {
    return c.json({ error: 'Invalid date — expected YYYY-MM-DD' }, 400);
  }

  // Total reps that day, by outcome.
  const outcomeRows = await db
    .select({
      outcome: repLog.outcome,
      count: sql<number>`COUNT(*)::int`,
    })
    .from(repLog)
    .where(
      and(
        eq(repLog.userId, userId),
        sql`to_char(${repLog.createdAt} AT TIME ZONE 'UTC', 'YYYY-MM-DD') = ${date}`,
      ),
    )
    .groupBy(repLog.outcome);

  const outcomeCounts = { pass: 0, fail: 0, skip: 0 };
  for (const row of outcomeRows) {
    outcomeCounts[row.outcome] = row.count;
  }
  const drillCount = outcomeCounts.pass + outcomeCounts.fail + outcomeCounts.skip;

  // Distinct lessons touched on this day, ordered by most reps.
  const lessonRows = await db
    .select({
      slug: lesson.slug,
      title: lesson.title,
      category: lesson.category,
      reps: sql<number>`COUNT(*)::int`,
      signs: sql<number>`COUNT(DISTINCT ${repLog.signId})::int`,
    })
    .from(repLog)
    .innerJoin(sign, eq(sign.id, repLog.signId))
    .innerJoin(lesson, eq(lesson.id, sign.lessonId))
    .where(
      and(
        eq(repLog.userId, userId),
        sql`to_char(${repLog.createdAt} AT TIME ZONE 'UTC', 'YYYY-MM-DD') = ${date}`,
      ),
    )
    .groupBy(lesson.slug, lesson.title, lesson.category)
    .orderBy(desc(sql`COUNT(*)`));

  return c.json({
    date,
    drillCount,
    intensity: intensityForCount(drillCount),
    outcomes: outcomeCounts,
    lessons: lessonRows,
  });
});

// === POST /api/progress/lesson/:slug/reset ===

app.post('/lesson/:slug/reset', async (c) => {
  const userId = getSessionUserId(c);
  if (!userId) return c.json({ error: 'Unauthorized' }, 401);

  const slug = c.req.param('slug');

  const lessonRows = await db
    .select({ id: lesson.id })
    .from(lesson)
    .where(eq(lesson.slug, slug))
    .limit(1);
  const lessonRow = lessonRows[0];
  if (!lessonRow) return c.json({ error: 'Lesson not found' }, 404);

  const signRows = await db
    .select({ id: sign.id })
    .from(sign)
    .where(eq(sign.lessonId, lessonRow.id));
  const signIds = signRows.map((s) => s.id);

  if (signIds.length === 0) {
    return c.json({ ok: true, signsReset: 0 });
  }

  await db
    .delete(masteryState)
    .where(and(eq(masteryState.userId, userId), inArray(masteryState.signId, signIds)));
  await db
    .delete(repLog)
    .where(and(eq(repLog.userId, userId), inArray(repLog.signId, signIds)));

  return c.json({ ok: true, signsReset: signIds.length });
});

export default app;
