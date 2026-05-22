import { describe, it, expect } from 'vitest';
import {
  LESSON_CATALOG,
  MASTERY_BUCKETS,
  TOTAL_SIGNS,
  HEATMAP_DAYS,
  distributeMastery,
  generateAllSigns,
  generateDrillTargetsForSign,
  generateRepLogData,
  makeRandom,
  repDaysDistribution,
  repDaysTotal,
} from '../../../scripts/seed-dev-user';

/**
 * Seed unit spec. Asserts the data-shape contracts produced by the pure
 * generator functions in `scripts/seed-dev-user.ts`. The DB I/O path is
 * covered by manual run + the e2e specs that consume the seeded dev
 * account.
 */
describe('seed data generators', () => {
  it('catalog has 12 lessons with 75 signs total', () => {
    expect(LESSON_CATALOG).toHaveLength(12);
    const total = LESSON_CATALOG.reduce((acc, l) => acc + l.signs.length, 0);
    expect(total).toBe(TOTAL_SIGNS);
  });

  it('each lesson declares the right signCount', () => {
    for (const l of LESSON_CATALOG) {
      expect(l.signCount).toBe(l.signs.length);
    }
  });

  it('generateAllSigns produces unique slugs for all 75 signs', () => {
    const signs = generateAllSigns();
    expect(signs).toHaveLength(TOTAL_SIGNS);
    const slugs = new Set(signs.map((s) => s.signSlug));
    expect(slugs.size).toBe(TOTAL_SIGNS);
  });

  it('generateDrillTargetsForSign returns exactly 3 drills (handshape / movement / sign)', () => {
    const drills = generateDrillTargetsForSign('HELLO', 0);
    expect(drills).toHaveLength(3);
    expect(drills.map((d) => d.drillType)).toEqual(['handshape', 'movement', 'sign']);
    expect(drills.find((d) => d.drillType === 'sign')?.targetString).toBe('HELLO');
  });

  it('distributeMastery yields the exact 12/9/8/5/4 breakdown', () => {
    const dist = distributeMastery();
    const total = dist.length;
    expect(total).toBe(
      MASTERY_BUCKETS.mastered +
        MASTERY_BUCKETS.known +
        MASTERY_BUCKETS.familiar +
        MASTERY_BUCKETS.learning +
        MASTERY_BUCKETS.new,
    );
    expect(total).toBe(38);
    const byLevel: Record<string, number> = {};
    for (const entry of dist) {
      byLevel[entry.level] = (byLevel[entry.level] ?? 0) + 1;
    }
    expect(byLevel).toEqual({
      mastered: 12,
      known: 9,
      familiar: 8,
      learning: 5,
      new: 4,
    });
  });

  it('mastery sign indices are unique within the 75-sign catalog', () => {
    const dist = distributeMastery();
    const indices = new Set(dist.map((d) => d.signGlobalIndex));
    expect(indices.size).toBe(dist.length);
    for (const idx of indices) {
      expect(idx).toBeGreaterThanOrEqual(0);
      expect(idx).toBeLessThan(TOTAL_SIGNS);
    }
  });

  it('makeRandom is deterministic across runs', () => {
    const a = makeRandom(0x1234);
    const b = makeRandom(0x1234);
    for (let i = 0; i < 20; i++) {
      expect(a()).toBe(b());
    }
  });

  it('generateRepLogData produces exactly 75 days', () => {
    const days = generateRepLogData();
    expect(days).toHaveLength(HEATMAP_DAYS);
  });

  it('rep_log day distribution matches PRD buckets (~40/25/25/10)', () => {
    const days = generateRepLogData();
    const dist = repDaysDistribution(days);
    // Loose bounds — PRD says ~, not exact.
    expect(dist.empty).toBeGreaterThanOrEqual(20);
    expect(dist.empty).toBeLessThanOrEqual(40);
    expect(dist.light + dist.moderate).toBeGreaterThanOrEqual(25);
    expect(dist.heavy).toBeGreaterThanOrEqual(5);
    expect(dist.heavy).toBeLessThanOrEqual(15);
    // Sanity: sums to 75
    expect(dist.empty + dist.light + dist.moderate + dist.heavy).toBe(HEATMAP_DAYS);
  });

  it('rep_log contains the required current 4-day streak (days 0..3 have reps)', () => {
    const days = generateRepLogData();
    for (let d = 0; d <= 3; d++) {
      const day = days.find((x) => x.daysAgo === d)!;
      expect(day.reps.length).toBeGreaterThan(0);
    }
  });

  it('rep_log contains the required 14-day streak ending 18 days ago', () => {
    const days = generateRepLogData();
    for (let d = 18; d <= 31; d++) {
      const day = days.find((x) => x.daysAgo === d)!;
      expect(day.reps.length).toBeGreaterThan(0);
    }
  });

  it('rep_log produces a reasonable total row count (~100-400 rows)', () => {
    const days = generateRepLogData();
    const total = repDaysTotal(days);
    expect(total).toBeGreaterThan(100);
    expect(total).toBeLessThan(500);
  });
});
