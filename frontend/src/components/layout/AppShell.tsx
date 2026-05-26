/**
 * Authenticated app layout providing the sticky top nav (logo, primary links,
 * and user menu) and an Outlet for the routed page below it. It exposes sign-out
 * and reflects the current user, falling back to a sign-in link when absent.
 */
import { Link, Outlet, useNavigate } from 'react-router-dom';
import { useUser, useSignOut } from '@/lib/auth';
import { Button } from '@/components/ui/button';
import { BrandMark } from '@/components/ui/brand-mark';
import { Wordmark } from '@/components/ui/wordmark';

export function AppShell() {
  const { user } = useUser();
  const navigate = useNavigate();
  const signOut = useSignOut();

  const handleSignOut = async () => {
    try {
      await signOut.mutateAsync();
    } catch {
      // ignore; the cookie will be re-checked
    }
    navigate('/signin');
  };

  return (
    <div className="flex min-h-screen flex-col bg-bg text-fg">
      <header
        className="sticky top-0 z-40 border-b border-line backdrop-blur-md"
        style={{ background: 'hsl(var(--bg) / 0.85)' }}
      >
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Link
            to="/dashboard"
            data-testid="nav-logo"
            className="flex items-center gap-2.5 text-fg"
            aria-label="ASL Pilot — home"
          >
            <BrandMark className="h-7 w-7 text-fg" />
            <Wordmark />
          </Link>
          <nav className="flex items-center gap-4 text-sm">
            <Link
              to="/lessons"
              data-testid="nav-lessons"
              className="text-fg-muted hover:text-fg"
            >
              Lessons
            </Link>
            <Link
              to="/dashboard"
              data-testid="nav-dashboard"
              className="text-fg-muted hover:text-fg"
            >
              Dashboard
            </Link>
            <Link
              to="/settings/app"
              data-testid="nav-settings"
              className="text-fg-muted hover:text-fg"
            >
              Settings
            </Link>
            <Link to="/help" data-testid="nav-help" className="text-fg-muted hover:text-fg">
              Help
            </Link>
            {user ? (
              <div className="flex items-center gap-2 border-l border-border pl-4">
                <span className="text-xs text-fg-muted">{user.displayName}</span>
                <Button
                  data-testid="nav-sign-out"
                  variant="ghost"
                  size="sm"
                  onClick={handleSignOut}
                >
                  Sign out
                </Button>
              </div>
            ) : (
              <Link
                to="/signin"
                data-testid="nav-sign-in"
                className="text-fg-muted hover:text-fg"
              >
                Sign in
              </Link>
            )}
          </nav>
        </div>
      </header>
      <div className="flex-1">
        <Outlet />
      </div>
    </div>
  );
}
