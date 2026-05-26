/**
 * Dev-only button that signs in via the dev-login mutation and navigates to a
 * target route, bypassing the real auth flow. It renders nothing unless dev
 * tools are enabled, and falls through to the destination even if the backend
 * is unreachable.
 */
import { useNavigate } from 'react-router-dom';
import { useDevLogin } from '@/lib/auth';
import { isDevToolsEnabled } from '@/lib/env';

interface SkipLoginButtonProps {
  /** Override label (defaults to "Dev: Skip login"). */
  label?: string;
  /** Where to navigate after sign-in. */
  redirectTo?: string;
  testId?: string;
}

export function SkipLoginButton({
  label = 'Dev: Skip login',
  redirectTo = '/dashboard',
  testId = 'dev-skip-login',
}: SkipLoginButtonProps) {
  const devLogin = useDevLogin();
  const navigate = useNavigate();

  if (!isDevToolsEnabled()) return null;

  const handleClick = async () => {
    try {
      await devLogin.mutateAsync();
    } catch {
      // Even if backend isn't reachable, fall through to the dashboard for scaffold UX.
      // Phase 3 specs assert URL change; the dashboard fetches independently.
    }
    navigate(redirectTo);
  };

  return (
    <button
      type="button"
      data-testid={testId}
      data-dev-override
      onClick={handleClick}
      disabled={devLogin.isPending}
      className="mt-3 inline-flex items-center justify-center rounded-md border border-status-warn/60 bg-status-warn/5 px-4 py-2 text-sm font-medium text-status-warn transition-colors hover:bg-status-warn/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-status-warn focus-visible:ring-offset-2 focus-visible:ring-offset-bg disabled:opacity-60"
    >
      {devLogin.isPending ? 'Signing in…' : label}
    </button>
  );
}
