// useUser() — TanStack Query-backed session hook.
// Returns { user, isLoading, error, isAuthenticated }. Re-fetched after sign-in/out via invalidate.
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import {
  authApi,
  ApiError,
  type UserDto,
  type SignInInput,
  type SignUpInput,
} from './api';

const ME_KEY = ['auth', 'me'] as const;

export function useUser() {
  const query = useQuery<UserDto | null, ApiError>({
    queryKey: ME_KEY,
    queryFn: async () => {
      try {
        const { user } = await authApi.me();
        return user;
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return null;
        throw err;
      }
    },
    staleTime: 60_000,
  });

  return {
    user: query.data ?? null,
    isLoading: query.isLoading,
    error: query.error,
    isAuthenticated: Boolean(query.data),
    refetch: query.refetch,
  };
}

export function useDevLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => authApi.devLogin(),
    onSuccess: ({ user }) => {
      qc.setQueryData(ME_KEY, user);
    },
  });
}

/**
 * Real password sign-in. Mirrors `useDevLogin`: on success it primes the
 * `['auth', 'me']` cache so dependent components don't have to wait for the
 * GET /me refetch, then invalidates to confirm against the server.
 */
export function useSignIn() {
  const qc = useQueryClient();
  return useMutation<{ user: UserDto }, ApiError, SignInInput>({
    mutationFn: (input) => authApi.signIn(input),
    onSuccess: ({ user }) => {
      qc.setQueryData(ME_KEY, user);
      qc.invalidateQueries({ queryKey: ME_KEY });
    },
  });
}

/**
 * Real account creation. Backend sets the session cookie and returns the
 * new user; same cache-priming + invalidate pattern as sign-in.
 */
export function useSignUp() {
  const qc = useQueryClient();
  return useMutation<{ user: UserDto }, ApiError, SignUpInput>({
    mutationFn: (input) => authApi.signUp(input),
    onSuccess: ({ user }) => {
      qc.setQueryData(ME_KEY, user);
      qc.invalidateQueries({ queryKey: ME_KEY });
    },
  });
}

export function useSignOut() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => authApi.signOut(),
    onSuccess: () => {
      qc.setQueryData(ME_KEY, null);
      qc.invalidateQueries({ queryKey: ME_KEY });
    },
  });
}
