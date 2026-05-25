/**
 * Offline fallback lesson content.
 *
 * Used when the backend isn't reachable so the practice flow (and the dev
 * Lesson Config editor) still have signs to work with. Previously inlined in
 * `pages/Practice.tsx`; extracted so the dev editor seeds from the SAME default
 * the practice flow falls back to — otherwise an overlay built in the editor
 * could reference signs the practice flow never loads.
 */
import type { PracticeSign } from '@/lib/machines/practice';

/** Default lesson slug the dev editor targets when the backend is unreachable. */
export const FALLBACK_LESSON_SLUG = 'lesson-1';

export const FALLBACK_SIGNS: PracticeSign[] = [
  {
    id: '00000000-0000-0000-0000-000000000001',
    slug: 'mom',
    englishGloss: 'MOM',
    drills: [{ drillType: 'sign', target: 'MOM' }],
  },
  {
    id: '00000000-0000-0000-0000-000000000002',
    slug: 'dad',
    englishGloss: 'DAD',
    drills: [{ drillType: 'sign', target: 'DAD' }],
  },
];
