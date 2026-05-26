/**
 * Renders the App Settings page where the user toggles practice defaults (camera,
 * reference video, reduced motion, mirror) and playback options. Changes flow through
 * useAppSettings and persist to localStorage, prefilling the Lesson Intro toggles.
 */
import { useAppSettings } from '@/lib/settings';
import { Card, CardContent } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';

export default function AppSettingsPage() {
  const { settings, update } = useAppSettings();

  return (
    <main data-testid="page-app-settings" className="mx-auto max-w-2xl px-6 py-8">
      <header className="mb-6">
        <p className="font-mono text-xs uppercase tracking-wider text-fg-muted">Settings</p>
        <h1 className="mt-1 text-3xl font-bold tracking-tight">App settings</h1>
        <p className="mt-2 text-sm text-fg-muted">
          Defaults that prefill the Lesson Intro toggles. Stored locally in your browser.
        </p>
      </header>

      <Card>
        <CardContent className="space-y-6 p-6">
          <section className="space-y-3">
            <h2 className="font-mono text-xs uppercase tracking-wider text-fg-muted">
              Practice defaults
            </h2>
            <Row
              id="camera-default"
              label="Camera on for new lessons"
              checked={settings.cameraDefault}
              onChange={(v) => update({ cameraDefault: v })}
              testId="settings-camera-default"
            />
            <Row
              id="reference-default"
              label="Reference video shown for new lessons"
              checked={settings.referenceDefault}
              onChange={(v) => update({ referenceDefault: v })}
              testId="settings-reference-default"
            />
            <Row
              id="reduced-motion"
              label="Reduce motion"
              checked={settings.reducedMotion}
              onChange={(v) => update({ reducedMotion: v })}
              testId="settings-reduced-motion"
            />
            <Row
              id="mirror"
              label="Mirror camera preview"
              checked={settings.mirror}
              onChange={(v) => update({ mirror: v })}
              testId="settings-mirror"
            />
          </section>

          <section className="space-y-3">
            <h2 className="font-mono text-xs uppercase tracking-wider text-fg-muted">
              Playback
            </h2>
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor="playback-speed">Reference playback speed</Label>
              <select
                id="playback-speed"
                data-testid="settings-playback-speed"
                value={settings.playbackSpeed}
                onChange={(e) =>
                  update({ playbackSpeed: Number(e.target.value) as 1 | 0.75 })
                }
                className="rounded-md border border-border bg-bg-elevated px-3 py-1 text-sm"
              >
                <option value={1}>1×</option>
                <option value={0.75}>0.75×</option>
              </select>
            </div>
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor="auto-advance">Auto-advance after pass</Label>
              <select
                id="auto-advance"
                data-testid="settings-auto-advance"
                value={settings.autoAdvanceMs}
                onChange={(e) =>
                  update({ autoAdvanceMs: Number(e.target.value) as 0 | 800 | 1500 })
                }
                className="rounded-md border border-border bg-bg-elevated px-3 py-1 text-sm"
              >
                <option value={0}>Off</option>
                <option value={800}>800 ms</option>
                <option value={1500}>1.5 s</option>
              </select>
            </div>
          </section>
        </CardContent>
      </Card>
    </main>
  );
}

function Row({
  id,
  label,
  checked,
  onChange,
  testId,
}: {
  id: string;
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  testId: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <Label htmlFor={id}>{label}</Label>
      <Switch
        id={id}
        checked={checked}
        onCheckedChange={(c) => onChange(Boolean(c))}
        data-testid={testId}
      />
    </div>
  );
}
