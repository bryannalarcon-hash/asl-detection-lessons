import { useState } from 'react';
import { CameraPanel } from '@/components/practice/CameraPanel';
import { BoundingBox, type BoxState } from '@/components/practice/BoundingBox';

/**
 * Advance-button label. With the full-sign-only plan a sign has one drill, so
 * a drill transition is a word transition. If reps remain in the current sign
 * the next press advances a rep -> "Next rep (X of N) →". On the last rep the
 * next press moves to a different word -> "Continue →".
 */
export function computeContinueLabel({
  repIndex,
  repTotal,
}: {
  repIndex: number;
  repTotal: number;
}): string {
  const isLastRep = repIndex >= repTotal - 1;
  if (!isLastRep) {
    return `Next rep (${repIndex + 2} of ${repTotal}) →`;
  }
  return 'Continue →';
}

export function CameraPanelWrapper({
  boxState,
  mirror,
  paused,
  matchScore,
  onVideoEl,
}: {
  boxState: BoxState;
  mirror: boolean;
  paused: boolean;
  matchScore?: number;
  onVideoEl?: (el: HTMLVideoElement | null) => void;
}) {
  const [canUseCamera] = useState<boolean>(
    typeof navigator !== 'undefined' && Boolean(navigator.mediaDevices?.getUserMedia)
  );
  if (!canUseCamera) {
    return (
      <BoundingBox state={boxState} className="aspect-[4/3] w-full">
        <div className="flex h-full w-full items-center justify-center bg-bg-deep text-center text-sm text-fg-muted">
          <p>Camera unavailable in this preview.</p>
        </div>
      </BoundingBox>
    );
  }
  return (
    <CameraPanel
      boxState={boxState}
      mirror={mirror}
      paused={paused}
      matchScore={matchScore}
      onVideoEl={onVideoEl}
    />
  );
}
