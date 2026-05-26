/**
 * Stub page layout for routes that are not yet built, rendering a breadcrumb,
 * title, and a note pointing to the relevant ux-spec.md section. It accepts
 * children so dev-bypass buttons can be slotted beneath the placeholder copy.
 */
import { type ReactNode } from 'react';
import { Link } from 'react-router-dom';

interface PlaceholderLayoutProps {
  title: string;
  uxSpecSection: string; // e.g. "§15 Account Settings"
  children?: ReactNode; // for dev-bypass buttons
}

export function PlaceholderLayout({ title, uxSpecSection, children }: PlaceholderLayoutProps) {
  return (
    <main data-testid="page-placeholder" className="mx-auto max-w-3xl px-6 py-12">
      <nav aria-label="Breadcrumb" className="mb-4 text-sm text-fg-muted">
        <Link to="/dashboard" className="hover:text-fg">
          Dashboard
        </Link>{' '}
        / {title}
      </nav>
      <h1 className="text-3xl font-bold">{title}</h1>
      <p className="mt-4 text-fg-muted">
        Placeholder. See <code className="font-mono text-fg">ux-spec.md</code> {uxSpecSection} for
        the full feature spec.
      </p>
      {children}
    </main>
  );
}
