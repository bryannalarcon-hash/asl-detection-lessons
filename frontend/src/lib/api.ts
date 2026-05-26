// Thin fetch wrapper + typed endpoint helpers.
// All requests use credentials: 'include' so the session cookie rides along.
import { env } from './env';

export class ApiError extends Error {
  status: number;
  payload: unknown;
  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${env.API_URL}${path}`;
  return fetch(url, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });
}

async function parseJson<T>(res: Response): Promise<T> {
  let body: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!res.ok) {
    throw new ApiError(`API ${res.status} ${res.statusText}`, res.status, body);
  }
  return body as T;
}

// === Types (matching Phase 2A's planned API contract) ===

export interface UserDto {
  id: string;
  email: string;
  displayName: string;
  createdAt?: string;
  emailVerifiedAt?: string | null;
}

export interface LessonDto {
  id: string;
  slug: string;
  title: string;
  category: string;
  signCount: number;
  orderIndex: number;
}

export interface SignDto {
  id: string;
  slug: string;
  englishGloss: string;
  lessonId: string;
  orderIndex: number;
}

export interface DrillDefinitionDto {
  id: string;
  signId: string;
  drillType: 'handshape' | 'movement' | 'sign';
  targetString: string;
  orderIndex: number;
}

export interface LessonDetailDto {
  lesson: LessonDto;
  signs: SignDto[];
  drillDefinitions: DrillDefinitionDto[];
}

export type MasteryLevel = 'new' | 'learning' | 'familiar' | 'known' | 'mastered';

export interface MasteryStateDto {
  signId: string;
  level: MasteryLevel;
  lastPracticedAt?: string | null;
  advanceCount: number;
  regressCount: number;
}

export interface HeatmapCell {
  date: string; // ISO yyyy-mm-dd
  /** Total rep_log rows on this day. Backend returns this as `drillCount`. */
  drillCount: number;
  /** Pre-computed intensity 0–4 from the backend (5-tier scale; 4 = 30+ reps). */
  intensity: 0 | 1 | 2 | 3 | 4;
}

export interface RecentLessonDto {
  slug: string;
  title: string;
  category: string;
  signCount: number;
  masteredCount: number;
  lastTouchedAt?: string | null;
}

export interface StreakStateDto {
  currentStreakDays: number;
  longestStreakDays: number;
  freezesRemaining: number;
  lastPracticeDate?: string | null;
}

export interface DashboardDto {
  /** Backend returns the per-level counts flattened plus `touched` and `total`.
   *  See backend/src/routes/progress.ts for the canonical shape. */
  masterySummary: {
    total: number;
    /** Number of signs at level `mastered` only. */
    mastered: number;
    /** Number of signs in any non-zero mastery state (per PRD: 38). */
    touched: number;
    new: number;
    learning: number;
    familiar: number;
    known: number;
  };
  heatmap: HeatmapCell[];
  recentLessons: RecentLessonDto[];
  streak: StreakStateDto;
}

export interface RepInput {
  signId: string;
  drillType: 'handshape' | 'movement' | 'sign';
  outcome: 'pass' | 'fail' | 'skip';
  source: 'self-report' | 'cv' | 'dev';
  hintRequested?: boolean;
}

// === Endpoint helpers ===

export interface SignUpInput {
  email: string;
  password: string;
  displayName: string;
}

export interface SignInInput {
  email: string;
  password: string;
}

export const authApi = {
  devLogin: () =>
    apiFetch('/api/auth/dev-login', { method: 'POST', body: JSON.stringify({}) }).then(
      parseJson<{ user: UserDto }>
    ),
  signUp: (input: SignUpInput) =>
    apiFetch('/api/auth/sign-up', {
      method: 'POST',
      body: JSON.stringify(input),
    }).then(parseJson<{ user: UserDto }>),
  signIn: (input: SignInInput) =>
    apiFetch('/api/auth/sign-in', {
      method: 'POST',
      body: JSON.stringify(input),
    }).then(parseJson<{ user: UserDto }>),
  signOut: () =>
    apiFetch('/api/auth/sign-out', { method: 'POST', body: JSON.stringify({}) }).then(
      parseJson<{ ok: true }>
    ),
  me: () => apiFetch('/api/auth/me').then(parseJson<{ user: UserDto }>),
};

export const lessonsApi = {
  list: () => apiFetch('/api/lessons').then(parseJson<{ lessons: LessonDto[] }>),
  get: (slug: string) => apiFetch(`/api/lessons/${slug}`).then(parseJson<LessonDetailDto>),
};

export interface DayDetailDto {
  date: string;
  drillCount: number;
  intensity: 0 | 1 | 2 | 3 | 4;
  outcomes: { pass: number; fail: number; skip: number };
  lessons: Array<{
    slug: string;
    title: string;
    category: string;
    reps: number;
    signs: number;
  }>;
}

export const progressApi = {
  rep: (input: RepInput) =>
    apiFetch('/api/progress/rep', {
      method: 'POST',
      body: JSON.stringify(input),
    }).then(parseJson<{ masteryState: MasteryStateDto }>),
  dashboard: () => apiFetch('/api/progress/dashboard').then(parseJson<DashboardDto>),
  day: (date: string) =>
    apiFetch(`/api/progress/day/${encodeURIComponent(date)}`).then(parseJson<DayDetailDto>),
  resetLesson: (slug: string) =>
    apiFetch(`/api/progress/lesson/${encodeURIComponent(slug)}/reset`, {
      method: 'POST',
    }).then(parseJson<{ ok: boolean; signsReset: number }>),
};

export const healthApi = {
  ping: () => apiFetch('/api/health').then(parseJson<{ ok: boolean; dbReachable?: boolean }>),
};
