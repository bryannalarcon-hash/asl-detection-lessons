/**
 * Fixed bottom tab bar shown only on narrow viewports (below the `md` break),
 * giving signed-in learners one-tap reach to Home, Lessons, Settings, and Help
 * when the desktop top-nav links are hidden. It mirrors the active route via
 * aria-current and respects the iOS home-indicator safe area.
 */
import { Link, useLocation } from 'react-router-dom';
import { Home, LayoutGrid, Settings, HelpCircle, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Tab {
  to: string;
  label: string;
  testId: string;
  icon: LucideIcon;
  /** Active when the current path starts with this prefix. */
  match: string;
}

const TABS: Tab[] = [
  { to: '/dashboard', label: 'Home', testId: 'tabbar-home', icon: Home, match: '/dashboard' },
  { to: '/lessons', label: 'Lessons', testId: 'tabbar-lessons', icon: LayoutGrid, match: '/lessons' },
  { to: '/settings/app', label: 'Settings', testId: 'tabbar-settings', icon: Settings, match: '/settings' },
  { to: '/help', label: 'Help', testId: 'tabbar-help', icon: HelpCircle, match: '/help' },
];

export function MobileTabBar() {
  const { pathname } = useLocation();

  return (
    <nav
      data-testid="mobile-tabbar"
      aria-label="Primary"
      className={cn(
        'fixed inset-x-0 bottom-0 z-50 grid grid-cols-4 md:hidden',
        'border-t border-border bg-[hsl(var(--bg)/0.92)] backdrop-blur-md',
      )}
      style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
    >
      {TABS.map(({ to, label, testId, icon: Icon, match }) => {
        const active = pathname === match || pathname.startsWith(`${match}/`);
        return (
          <Link
            key={testId}
            to={to}
            data-testid={testId}
            aria-current={active ? 'page' : undefined}
            className={cn(
              'flex flex-col items-center gap-1 py-2.5 transition-colors',
              active ? 'text-accent' : 'text-fg-subtle hover:text-fg',
            )}
          >
            <Icon className="h-[22px] w-[22px]" strokeWidth={1.8} aria-hidden="true" />
            <span className="font-mono text-[0.68rem] tracking-[0.02em]">{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
