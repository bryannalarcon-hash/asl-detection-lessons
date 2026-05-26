/**
 * Drizzle schema defining the ASL Pilot Postgres tables, enums, and inferred
 * row types. Covers users, lessons, signs, drill definitions, rep logs, mastery
 * state, streaks, and notification preferences for the practice app.
 */
import { sql } from 'drizzle-orm';
import {
  pgTable,
  pgEnum,
  uuid,
  text,
  timestamp,
  integer,
  boolean,
  date,
  time,
  index,
  uniqueIndex,
  primaryKey,
} from 'drizzle-orm/pg-core';

// === Enums ===
export const masteryLevelEnum = pgEnum('mastery_level', [
  'new',
  'learning',
  'familiar',
  'known',
  'mastered',
]);
export const repOutcomeEnum = pgEnum('rep_outcome', ['pass', 'fail', 'skip']);
export const repSourceEnum = pgEnum('rep_source', ['cv', 'self-report', 'dev']);
export const drillTypeEnum = pgEnum('drill_type', ['handshape', 'movement', 'sign']);

// === Tables ===
export const user = pgTable(
  'user',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    email: text('email').notNull(),
    displayName: text('display_name').notNull(),
    passwordHash: text('password_hash'),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
    emailVerifiedAt: timestamp('email_verified_at', { withTimezone: true }),
  },
  (t) => ({
    emailLowerUnique: uniqueIndex('user_email_lower_unique').on(sql`lower(${t.email})`),
  }),
);

export const lesson = pgTable('lesson', {
  id: uuid('id').primaryKey().defaultRandom(),
  slug: text('slug').notNull().unique(),
  title: text('title').notNull(),
  category: text('category').notNull(),
  signCount: integer('sign_count').notNull(),
  orderIndex: integer('order_index').notNull(),
});

export const sign = pgTable('sign', {
  id: uuid('id').primaryKey().defaultRandom(),
  slug: text('slug').notNull().unique(),
  englishGloss: text('english_gloss').notNull(),
  lessonId: uuid('lesson_id')
    .notNull()
    .references(() => lesson.id, { onDelete: 'cascade' }),
  orderIndex: integer('order_index').notNull(),
});

export const drillDefinition = pgTable('drill_definition', {
  id: uuid('id').primaryKey().defaultRandom(),
  signId: uuid('sign_id')
    .notNull()
    .references(() => sign.id, { onDelete: 'cascade' }),
  drillType: drillTypeEnum('drill_type').notNull(),
  targetString: text('target_string').notNull(),
  orderIndex: integer('order_index').notNull(),
});

export const repLog = pgTable(
  'rep_log',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    userId: uuid('user_id')
      .notNull()
      .references(() => user.id, { onDelete: 'cascade' }),
    signId: uuid('sign_id')
      .notNull()
      .references(() => sign.id, { onDelete: 'cascade' }),
    drillType: drillTypeEnum('drill_type').notNull(),
    outcome: repOutcomeEnum('outcome').notNull(),
    source: repSourceEnum('source').notNull(),
    hintRequested: boolean('hint_requested').notNull().default(false),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => ({
    userDateIdx: index('rep_log_user_date_idx').on(t.userId, t.createdAt),
  }),
);

export const masteryState = pgTable(
  'mastery_state',
  {
    userId: uuid('user_id')
      .notNull()
      .references(() => user.id, { onDelete: 'cascade' }),
    signId: uuid('sign_id')
      .notNull()
      .references(() => sign.id, { onDelete: 'cascade' }),
    level: masteryLevelEnum('level').notNull().default('new'),
    lastPracticedAt: timestamp('last_practiced_at', { withTimezone: true }),
    advanceCount: integer('advance_count').notNull().default(0),
    regressCount: integer('regress_count').notNull().default(0),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.userId, t.signId] }),
  }),
);

export const streakState = pgTable('streak_state', {
  userId: uuid('user_id')
    .primaryKey()
    .references(() => user.id, { onDelete: 'cascade' }),
  currentStreakDays: integer('current_streak_days').notNull().default(0),
  longestStreakDays: integer('longest_streak_days').notNull().default(0),
  freezesRemaining: integer('freezes_remaining').notNull().default(2),
  lastPracticeDate: date('last_practice_date'),
});

export const notificationPref = pgTable('notification_pref', {
  userId: uuid('user_id')
    .primaryKey()
    .references(() => user.id, { onDelete: 'cascade' }),
  dailyReminderTime: time('daily_reminder_time'),
  weeklySummaryEnabled: boolean('weekly_summary_enabled').notNull().default(true),
  streakAtRiskEnabled: boolean('streak_at_risk_enabled').notNull().default(false),
});

// Type exports for convenience in route handlers / seed script
export type User = typeof user.$inferSelect;
export type NewUser = typeof user.$inferInsert;
export type Lesson = typeof lesson.$inferSelect;
export type NewLesson = typeof lesson.$inferInsert;
export type Sign = typeof sign.$inferSelect;
export type NewSign = typeof sign.$inferInsert;
export type DrillDefinition = typeof drillDefinition.$inferSelect;
export type NewDrillDefinition = typeof drillDefinition.$inferInsert;
export type RepLog = typeof repLog.$inferSelect;
export type NewRepLog = typeof repLog.$inferInsert;
export type MasteryState = typeof masteryState.$inferSelect;
export type NewMasteryState = typeof masteryState.$inferInsert;
export type StreakState = typeof streakState.$inferSelect;
export type NewStreakState = typeof streakState.$inferInsert;
export type NotificationPref = typeof notificationPref.$inferSelect;
export type NewNotificationPref = typeof notificationPref.$inferInsert;

export type MasteryLevel = (typeof masteryLevelEnum.enumValues)[number];
export type RepOutcome = (typeof repOutcomeEnum.enumValues)[number];
export type RepSource = (typeof repSourceEnum.enumValues)[number];
export type DrillType = (typeof drillTypeEnum.enumValues)[number];
