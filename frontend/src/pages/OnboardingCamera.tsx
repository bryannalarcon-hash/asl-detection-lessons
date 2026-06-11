/**
 * Renders onboarding step 2, the camera permission request screen. It drives the
 * getUserMedia prompt via useCameraPermission, advancing to calibration on grant and
 * to the camera-denied page on denial, with a dev toolbox for forcing permission states.
 */
import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Camera } from 'lucide-react';
import { useCameraPermission } from '@/hooks/useCameraPermission';
import { CameraDevToolbox } from '@/components/practice/CameraDevToolbox';

export default function OnboardingCameraPage() {
  const navigate = useNavigate();
  const { state, request, stop, forceState } = useCameraPermission();
  // Track whether we've already navigated for the current grant, so a re-grant
  // (e.g. dev "Force allow" tapped twice) doesn't push twice.
  const navigatedRef = useRef(false);

  // When permission lands (real or dev-forced), advance the onboarding flow.
  useEffect(() => {
    if (state.kind === 'granted' && !navigatedRef.current) {
      navigatedRef.current = true;
      // Release the stream — onboarding only needs the permission ack.
      stop();
      navigate('/onboarding/calibration');
      return;
    }
    if (state.kind === 'denied') {
      navigate('/errors/camera-denied');
    }
  }, [state, navigate, stop]);

  // Stop any in-flight stream on unmount.
  useEffect(() => () => stop(), [stop]);

  const pending = state.kind === 'requesting';
  const unsupportedMsg =
    state.kind === 'unsupported'
      ? state.reason === 'in-use'
        ? 'Your camera is busy — another app or tab is using it. Close it and press "Turn on camera" again, or continue without it.'
        : state.reason === 'insecure-context'
          ? 'Camera access needs a secure connection — reload this page over https://. You can continue without it for now.'
          : state.reason === 'no-device'
            ? 'No camera found on this device. You can continue without it.'
            : 'Camera not available on this device or browser. You can continue without it.'
      : null;

  return (
    <main data-testid="page-onboarding-camera" className="mx-auto max-w-2xl px-6 py-16">
      <p className="font-mono text-xs uppercase tracking-wider text-fg-muted">
        Onboarding · Step 2 of 4
      </p>
      <h1 className="mt-4 text-4xl font-bold tracking-tight">Camera setup</h1>
      <p className="mt-4 max-w-lg text-base text-fg-muted">
        We need your camera so you can practice signs against a Deaf instructor's example.
        Your video stays on your device — nothing is uploaded.
      </p>
      <div className="mt-10 flex items-center gap-3">
        <Button
          size="lg"
          data-testid="camera-allow"
          onClick={() => void request()}
          disabled={pending}
        >
          <Camera className="h-4 w-4" />
          {pending ? 'Requesting…' : 'Turn on camera'}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          data-testid="camera-skip"
          onClick={() => navigate('/onboarding/calibration')}
        >
          Skip — set up later
        </Button>
      </div>
      {unsupportedMsg && (
        <p className="mt-4 text-sm text-status-warn" role="status">
          {unsupportedMsg}
        </p>
      )}
      <div className="mt-6">
        <CameraDevToolbox forceState={forceState} />
      </div>
    </main>
  );
}
