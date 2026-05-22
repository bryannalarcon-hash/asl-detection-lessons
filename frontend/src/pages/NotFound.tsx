import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';

export default function NotFoundPage() {
  return (
    <main data-testid="page-not-found" className="mx-auto max-w-2xl px-6 py-24 text-center">
      <p className="font-mono text-xs uppercase tracking-wider text-fg-muted">404</p>
      <h1 className="mt-2 text-4xl font-bold tracking-tight">We couldn't find that page.</h1>
      <p className="mt-3 text-sm text-fg-muted">
        It may have moved, or the lesson slug may be wrong.
      </p>
      <div className="mt-6 flex justify-center gap-3">
        <Link to="/dashboard" data-testid="notfound-dashboard">
          <Button>Back to dashboard</Button>
        </Link>
        <Link to="/lessons" data-testid="notfound-lessons">
          <Button variant="outline">Browse lessons</Button>
        </Link>
      </div>
    </main>
  );
}
