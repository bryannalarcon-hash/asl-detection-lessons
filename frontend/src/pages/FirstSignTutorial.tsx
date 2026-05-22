import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { PlaceholderLayout } from '@/components/layout/PlaceholderLayout';
import { Button } from '@/components/ui/button';

export default function FirstSignTutorialPage() {
  const navigate = useNavigate();

  useEffect(() => {
    // Auto-route to dashboard after a short pause so this page is inspectable
    // but still meets the spec's "placeholder that routes to Dashboard" requirement.
    const t = window.setTimeout(() => navigate('/dashboard'), 1200);
    return () => window.clearTimeout(t);
  }, [navigate]);

  return (
    <PlaceholderLayout
      title="First-sign tutorial"
      uxSpecSection="§9 Onboarding: First-Sign Tutorial"
    >
      <p className="mt-4 text-sm text-fg-muted">
        The tutorial-specific scaffolding (faded hint, endowed-progress tick) is feature work.
        Routing you to the dashboard now.
      </p>
      <Button
        data-testid="skip-to-dashboard"
        variant="outline"
        className="mt-4"
        onClick={() => navigate('/dashboard')}
      >
        Go to dashboard now
      </Button>
    </PlaceholderLayout>
  );
}
