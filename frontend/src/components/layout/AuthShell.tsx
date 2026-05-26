/**
 * Minimal layout for unauthenticated auth screens, showing only a centered
 * brand logo header above the routed content. It centers its Outlet for the
 * sign-in and related auth pages.
 */
import { Link, Outlet } from 'react-router-dom';
import { BrandMark } from '@/components/ui/brand-mark';
import { Wordmark } from '@/components/ui/wordmark';

export function AuthShell() {
  return (
    <div className="flex min-h-screen flex-col bg-bg text-fg">
      <header className="px-6 py-4">
        <div className="mx-auto flex max-w-6xl items-center justify-center">
          <Link
            to="/"
            data-testid="auth-logo"
            className="flex items-center gap-2 text-fg"
            aria-label="ASL Pilot — home"
          >
            <BrandMark className="h-6 w-6 text-fg" />
            <Wordmark className="text-xl" />
          </Link>
        </div>
      </header>
      <main className="flex flex-1 items-center justify-center px-6">
        <Outlet />
      </main>
    </div>
  );
}
