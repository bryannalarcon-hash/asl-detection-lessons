import { useState } from 'react';
import { Link } from 'react-router-dom';
import { CameraPanel } from '@/components/practice/CameraPanel';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';

export default function OnboardingCalibrationPage() {
  const [mirror, setMirror] = useState(true);
  return (
    <main data-testid="page-onboarding-calibration" className="mx-auto max-w-3xl px-6 py-12">
      <p className="font-mono text-xs uppercase tracking-wider text-fg-muted">
        Onboarding · Step 3 of 4
      </p>
      <h1 className="mt-4 text-3xl font-bold tracking-tight">Calibration</h1>
      <p className="mt-2 max-w-xl text-base text-fg-muted">
        Frame yourself so your head, shoulders, and hands fit comfortably in the box. Toggle
        the mirror if it feels more natural reversed.
      </p>
      <div className="mt-8 grid gap-6 md:grid-cols-[1fr_auto]">
        <div className="aspect-video w-full max-w-2xl">
          <CameraPanel boxState="orange" mirror={mirror} />
        </div>
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="mirror-toggle">Mirror</Label>
            <Switch
              id="mirror-toggle"
              checked={mirror}
              onCheckedChange={(c) => setMirror(Boolean(c))}
              data-testid="calibration-mirror-toggle"
            />
          </div>
          <Link to="/onboarding/first-sign" data-testid="calibration-continue">
            <Button size="lg" className="w-full">
              Looks good — continue
            </Button>
          </Link>
        </div>
      </div>
    </main>
  );
}
