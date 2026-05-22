import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';

export default function OnboardingWelcomePage() {
  return (
    <main data-testid="page-onboarding-welcome" className="mx-auto max-w-2xl px-6 py-16">
      <p className="font-mono text-xs uppercase tracking-wider text-fg-muted">
        Onboarding · Step 1 of 4
      </p>
      <h1 className="mt-4 text-4xl font-bold tracking-tight">
        You're going to learn 75 essential ASL signs.
      </h1>
      <ul className="mt-8 space-y-4 text-base text-fg-muted">
        <li>· This app checks your hands. We won't grade facial grammar in v1.</li>
        <li>· For full ASL, practice with a Deaf instructor.</li>
        <li>· Your video stays on your device. Nothing is uploaded.</li>
      </ul>
      <div className="mt-10 flex items-center gap-3">
        <Link to="/onboarding/camera" data-testid="onboarding-continue">
          <Button size="lg">Let's set up your camera</Button>
        </Link>
        <Link to="/dashboard" data-testid="onboarding-skip">
          <Button variant="ghost" size="sm">
            Skip for now
          </Button>
        </Link>
      </div>
    </main>
  );
}
