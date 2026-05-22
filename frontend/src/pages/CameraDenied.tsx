import { useNavigate } from 'react-router-dom';
import { CameraOff, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

export default function CameraDeniedPage() {
  const navigate = useNavigate();

  const detectBrowser = () => {
    if (typeof navigator === 'undefined') return 'browser';
    const ua = navigator.userAgent;
    if (/Edg\//.test(ua)) return 'edge';
    if (/Chrome\//.test(ua) && !/Edg\//.test(ua)) return 'chrome';
    if (/Safari\//.test(ua) && !/Chrome\//.test(ua)) return 'safari';
    if (/Firefox\//.test(ua)) return 'firefox';
    return 'browser';
  };

  const browser = detectBrowser();

  const instructions = {
    chrome: 'Click the camera icon in the address bar, then choose Allow.',
    edge: 'Click the camera icon in the address bar, then choose Allow.',
    safari: 'Open Safari → Settings for this website → Camera: Allow.',
    firefox: 'Click the camera icon in the address bar, then remove the block.',
    browser: 'Open your browser site settings and re-enable the camera for this site.',
  }[browser];

  const retry = async () => {
    if (!navigator.mediaDevices?.getUserMedia) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      stream.getTracks().forEach((t) => t.stop());
      navigate('/onboarding/calibration');
    } catch {
      // Stay on this page; UI already explains how to re-enable.
    }
  };

  return (
    <main data-testid="page-camera-denied" className="mx-auto max-w-2xl px-6 py-16">
      <Card>
        <CardContent className="space-y-4 p-8">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-bg-elevated text-fg-muted">
            <CameraOff className="h-5 w-5" />
          </span>
          <h1 className="text-3xl font-bold tracking-tight">Camera access is blocked.</h1>
          <p className="text-sm text-fg-muted">{instructions}</p>
          <div className="flex flex-wrap gap-3 pt-2">
            <Button onClick={retry} data-testid="camera-retry">
              <RotateCcw className="h-4 w-4" />
              I've re-enabled it
            </Button>
            <Button
              variant="outline"
              onClick={() => navigate('/dashboard')}
              data-testid="camera-skip-to-dashboard"
            >
              Continue without camera
            </Button>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
