import { Hono } from 'hono';
import { asc, eq, inArray, sql } from 'drizzle-orm';
import { db } from '../db/client';
import { drillDefinition, lesson, sign } from '../db/schema';

const app = new Hono();

/**
 * GET /api/lessons
 *
 * Returns all lessons ordered by `order_index`, with a `signCount` computed
 * from the actual row count in `sign` (separate from the `lesson.sign_count`
 * column, which is denormalized seed metadata).
 */
app.get('/', async (c) => {
  // Re-aggregate the live sign count per lesson (source of truth in case the
  // denormalized lesson.sign_count drifts). LEFT JOIN + GROUP BY so lessons
  // with zero signs still return a row with count 0.
  const rows = await db
    .select({
      id: lesson.id,
      slug: lesson.slug,
      title: lesson.title,
      category: lesson.category,
      orderIndex: lesson.orderIndex,
      declaredSignCount: lesson.signCount,
      signCount: sql<number>`count(${sign.id})::int`,
    })
    .from(lesson)
    .leftJoin(sign, eq(sign.lessonId, lesson.id))
    .groupBy(lesson.id)
    .orderBy(asc(lesson.orderIndex));

  return c.json({ lessons: rows });
});

/**
 * GET /api/lessons/:slug
 *
 * Returns the lesson, its signs (ordered), and all drill_definition rows for
 * those signs. 404 if no lesson matches.
 */
app.get('/:slug', async (c) => {
  const slug = c.req.param('slug');

  const lessonRows = await db.select().from(lesson).where(eq(lesson.slug, slug)).limit(1);
  const lessonRow = lessonRows[0];
  if (!lessonRow) {
    return c.json({ error: 'Lesson not found' }, 404);
  }

  const signs = await db
    .select()
    .from(sign)
    .where(eq(sign.lessonId, lessonRow.id))
    .orderBy(asc(sign.orderIndex));

  const signIds = signs.map((s) => s.id);
  const drillDefinitions =
    signIds.length === 0
      ? []
      : await db
          .select()
          .from(drillDefinition)
          .where(inArray(drillDefinition.signId, signIds))
          .orderBy(asc(drillDefinition.orderIndex));

  return c.json({
    lesson: lessonRow,
    signs,
    drillDefinitions,
  });
});

export default app;
