/**
 * Mobile-only immersive Practice layout (design mock screens 17-21): a full-bleed
 * video stage with one feed filling the viewport and the other as a tap-to-swap
 * corner PiP, a top scrim (lesson/word/stage·rep/counter/pause/exit), stage progress
 * segments, a floating control dock, an options bottom sheet, tap-to-immerse, and
 * swipe-to-advance. It reuses the page's XState-driven state + CameraPanelWrapper +
 * ReferenceVideo (forced full-bleed via the .pf-* CSS) so all CV/hint/self-report
 * behavior is identical to the desktop layout — only the presentation differs.
 */
import { useEffect, useRef, useState } from 'react';
import {
  ChevronLeft,
  Pause,
  Play,
  X as XIcon,
  Video,
  VideoOff,
  Eye,
  EyeOff,
  ArrowLeftRight,
  MoreHorizontal,
  Circle,
  CornerUpLeft,
  RotateCcw,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { DrillType } from '@/cv/types';
import type { BoxState } from '@/components/practice/BoundingBox';
import { CameraPanelWrapper } from '@/pages/practice-helpers';
import { ReferenceVideo } from '@/components/practice/ReferenceVideo';

export interface PracticeImmersiveProps {
  lessonTitle: string;
  lessonSlug: string;
  signWord: string;
  signSlug: string;
  videoSrc?: string;
  drillType?: DrillType;
  segment?: { startSec: number; endSec: number };
  /** Labels for each drill stage of the current sign, in order. */
  stageLabels: string[];
  currentStageIndex: number;
  signIndex: number;
  signTotal: number;
  repIndex: number; // 0-based
  repTotal: number;
  continueLabel: string;
  cameraOn: boolean;
  referenceOn: boolean;
  mirror: boolean;
  paused: boolean;
  boxState: BoxState;
  canBackDrill: boolean;
  canBackSign: boolean;
  // CV
  cvAvailable: boolean;
  recording: boolean;
  videoElReady: boolean;
  recordLabel: string;
  matchText: string | null;
  // Hint
  hintText: string | null;
  hintOpenSignal: number;
  // Handlers
  onVideoEl: (el: HTMLVideoElement | null) => void;
  onToggleCamera: () => void;
  onToggleReference: () => void;
  onToggleMirror: () => void;
  onContinue: () => void;
  onSkip: () => void;
  onBackDrill: () => void;
  onBackSign: () => void;
  onRestartSign: () => void;
  onPause: () => void;
  onExit: () => void;
  onRecordAttempt: () => void;
}

export function PracticeImmersive(props: PracticeImmersiveProps) {
  const {
    lessonTitle,
    signWord,
    signSlug,
    videoSrc,
    drillType,
    segment,
    stageLabels,
    currentStageIndex,
    signIndex,
    signTotal,
    repIndex,
    repTotal,
    continueLabel,
    cameraOn,
    referenceOn,
    mirror,
    paused,
    boxState,
    canBackDrill,
    canBackSign,
    cvAvailable,
    recording,
    videoElReady,
    recordLabel,
    matchText,
    hintText,
    hintOpenSignal,
    onVideoEl,
    onToggleCamera,
    onToggleReference,
    onToggleMirror,
    onContinue,
    onSkip,
    onBackDrill,
    onBackSign,
    onRestartSign,
    onPause,
    onExit,
    onRecordAttempt,
  } = props;

  const [mainView, setMainView] = useState<'reference' | 'camera'>('reference');
  const [panelOpen, setPanelOpen] = useState(false);
  const [chromeHidden, setChromeHidden] = useState(false);
  const [showHint, setShowHint] = useState(false);
  const [swipeHint, setSwipeHint] = useState('');

  // Auto-open the hint bubble when a failed recorded attempt bumps the signal.
  useEffect(() => {
    if (hintOpenSignal > 0) setShowHint(true);
  }, [hintOpenSignal]);

  // Collapse transient chrome (hint bubble, options sheet) when the word changes
  // so a previous sign's hint/sheet doesn't linger after an auto-advance.
  useEffect(() => {
    setShowHint(false);
    setPanelOpen(false);
  }, [signSlug]);

  const both = cameraOn && referenceOn;
  const effectiveMain: 'reference' | 'camera' = !referenceOn
    ? 'camera'
    : !cameraOn
      ? 'reference'
      : mainView;
  const swap = () => setMainView((v) => (v === 'reference' ? 'camera' : 'reference'));

  // Slot class for a feed that is ON (the feed is only rendered when on, so a
  // toggled-off camera unmounts and releases the hardware — matching desktop).
  const slotClass = (feed: 'reference' | 'camera') =>
    effectiveMain === feed ? 'pf-slot-main' : 'pf-slot-pip';

  // Tap-to-immerse: toggle chrome unless the tap lands on an interactive control.
  const onStageClick = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('button,a,input,select,[data-control]')) return;
    setChromeHidden((h) => !h);
  };

  // Swipe: left = advance, right = back.
  const touch = useRef({ x: 0, y: 0, active: false });
  const onTouchStart = (e: React.TouchEvent) => {
    const t = e.touches[0];
    touch.current = { x: t.clientX, y: t.clientY, active: true };
  };
  const onTouchEnd = (e: React.TouchEvent) => {
    if (!touch.current.active) return;
    const t = e.changedTouches[0];
    const dx = t.clientX - touch.current.x;
    const dy = t.clientY - touch.current.y;
    touch.current.active = false;
    if (Math.abs(dx) < 60 || Math.abs(dy) > Math.abs(dx)) return;
    if (dx < 0) {
      setSwipeHint('next →');
      onContinue();
    } else if (canBackDrill || canBackSign) {
      setSwipeHint('← back');
      onBackDrill();
    }
    window.setTimeout(() => setSwipeHint(''), 600);
  };

  const showSegments = stageLabels.length > 1;
  const stageLabel = stageLabels[currentStageIndex] ?? stageLabels[0] ?? '';
  const pipFeed: 'reference' | 'camera' | null = both
    ? effectiveMain === 'reference'
      ? 'camera'
      : 'reference'
    : null;

  return (
    <div
      data-testid="practice-immersive"
      className={cn('pf-shell', chromeHidden && 'pf-chrome-hidden')}
    >
      {/* Full-bleed video stage. Both feeds stay mounted; swap only restyles them. */}
      <div
        className="pf-viewport"
        onClick={onStageClick}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
      >
        {referenceOn && (
          <div className={cn('pf-feed-slot', slotClass('reference'))} data-feed="reference">
            <ReferenceVideo
              signSlug={signSlug}
              englishGloss={signWord}
              drillType={drillType}
              paused={paused}
              videoSrc={videoSrc}
              segmentOverride={segment}
            />
            {pipFeed === 'reference' && (
              <button className="pf-pip-cover" onClick={(e) => { e.stopPropagation(); swap(); }} aria-label="Swap to reference">
                <span className="pf-pip-swap"><ArrowLeftRight className="h-4 w-4" /></span>
              </button>
            )}
          </div>
        )}

        {cameraOn && (
          <div className={cn('pf-feed-slot', slotClass('camera'))} data-feed="camera">
            <CameraPanelWrapper
              boxState={boxState}
              mirror={mirror}
              paused={paused}
              onVideoEl={onVideoEl}
            />
            {pipFeed === 'camera' && (
              <button className="pf-pip-cover" onClick={(e) => { e.stopPropagation(); swap(); }} aria-label="Swap to your camera">
                <span className="pf-pip-swap"><ArrowLeftRight className="h-4 w-4" /></span>
              </button>
            )}
          </div>
        )}

        {!cameraOn && !referenceOn && (
          <div className="pf-empty">
            <p className="font-mono text-[0.72rem] uppercase tracking-[0.12em] text-fg-muted">
              Both feeds are off
            </p>
            <p className="mt-1.5 font-mono text-[0.8rem] text-fg-subtle">
              Turn the camera or reference back on from the controls.
            </p>
          </div>
        )}

        {/* Live match badge — only when the camera is the main feed. */}
        {effectiveMain === 'camera' && cameraOn && matchText && (
          <div className="pf-badge-match" data-testid="practice-match-badge">
            <span className="pf-dot" />
            <span className="font-mono text-[0.78rem]">{matchText}</span>
          </div>
        )}

        {swipeHint && <span className="pf-swipe-flash font-mono">{swipeHint}</span>}
      </div>

      {/* Top scrim */}
      <header className="pf-top">
        <button className="pf-top-back" data-control onClick={onExit} aria-label={`Exit ${lessonTitle}`}>
          <ChevronLeft className="h-4 w-4" />
          <span className="pf-top-back-label">{lessonTitle}</span>
        </button>
        <div className="pf-top-center">
          <span className="pf-top-word">{signWord}</span>
          <span className="pf-top-sub font-mono">
            {stageLabel ? `${stageLabel} · ` : ''}rep {repIndex + 1}/{repTotal}
          </span>
        </div>
        <div className="pf-top-right">
          <span className="pf-top-counter font-mono">
            {signIndex + 1}/{signTotal}
          </span>
          <button
            className="pf-icon-quiet"
            data-control
            data-testid="practice-pause"
            onClick={onPause}
            aria-label={paused ? 'Resume' : 'Pause'}
          >
            {paused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
          </button>
          <button
            className="pf-icon-quiet"
            data-control
            data-testid="practice-exit"
            onClick={onExit}
            aria-label="Exit to dashboard"
          >
            <XIcon className="h-4 w-4" />
          </button>
        </div>
      </header>

      {/* Stage progress segments (only for multi-stage signs) */}
      {showSegments && (
        <div className="pf-progress" aria-hidden="true">
          {stageLabels.map((s, i) => (
            <span
              key={s}
              className={cn(
                'pf-progress-seg',
                i < currentStageIndex && 'done',
                i === currentStageIndex && 'active',
              )}
            />
          ))}
        </div>
      )}

      {/* Hint bubble */}
      {showHint && hintText && (
        <div className="pf-hint-float" data-testid="practice-hint-bubble">
          <p className="font-mono text-[0.72rem] uppercase tracking-[0.12em] text-accent">
            Hint{stageLabel ? ` · ${stageLabel}` : ''}
          </p>
          <p className="mt-1.5 text-[0.92rem] leading-relaxed text-fg">{hintText}</p>
          <button
            className="pf-hint-close"
            data-control
            onClick={() => setShowHint(false)}
            aria-label="Dismiss hint"
          >
            <XIcon className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Bottom dock */}
      <div className="pf-dock">
        <div className="pf-bar">
          <button
            className="pf-icon"
            data-control
            data-testid="practice-back-drill"
            onClick={onBackDrill}
            disabled={!canBackDrill && !canBackSign}
            aria-label="Back one step"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
          <button
            className={cn('pf-icon', !cameraOn && 'muted')}
            data-control
            data-testid="practice-camera-toggle"
            data-state={cameraOn ? 'on' : 'off'}
            onClick={onToggleCamera}
            aria-label={cameraOn ? 'Turn camera off' : 'Turn camera on'}
          >
            {cameraOn ? <Video className="h-5 w-5" /> : <VideoOff className="h-5 w-5" />}
          </button>
          <button
            className={cn('pf-icon', !referenceOn && 'muted')}
            data-control
            data-testid="practice-reference-toggle"
            onClick={onToggleReference}
            aria-label={referenceOn ? 'Hide reference' : 'Show reference'}
          >
            {referenceOn ? <Eye className="h-5 w-5" /> : <EyeOff className="h-5 w-5" />}
          </button>
          <button
            className="pf-icon"
            data-control
            data-testid="practice-swap"
            onClick={swap}
            disabled={!both}
            aria-label="Swap main feed"
          >
            <ArrowLeftRight className="h-5 w-5" />
          </button>
          {cvAvailable && (
            <button
              className={cn('pf-icon pf-icon-record', recording && 'recording')}
              data-control
              data-testid="practice-record"
              onClick={onRecordAttempt}
              disabled={recording || !videoElReady}
              aria-label={recordLabel}
            >
              <Circle className="h-5 w-5" fill="currentColor" />
            </button>
          )}
          <button
            className={cn('pf-icon', panelOpen && 'active')}
            data-control
            data-testid="practice-more"
            onClick={() => setPanelOpen((o) => !o)}
            aria-label="More options"
          >
            <MoreHorizontal className="h-5 w-5" />
          </button>
          <button
            className="pf-continue"
            data-control
            data-testid="self-report-got-it"
            onClick={onContinue}
          >
            <span className="pf-continue-label">{continueLabel.replace(/\s*→\s*$/, '')}</span>
            <span aria-hidden="true">→</span>
          </button>
        </div>
      </div>

      {/* Options bottom sheet */}
      {panelOpen && (
        <>
          <div className="pf-sheet-scrim" data-control onClick={() => setPanelOpen(false)} />
          <div className="pf-sheet" data-control data-testid="practice-options-sheet">
            <div className="pf-sheet-handle" />
            <div className="pf-sheet-head">
              <div>
                <p className="font-mono text-[0.72rem] uppercase tracking-[0.12em] text-accent">
                  Options
                </p>
                <div className="pf-sheet-title">
                  {signWord}
                  {stageLabel ? ` · ${stageLabel}` : ''}
                </div>
              </div>
              <button className="pf-icon-quiet" onClick={() => setPanelOpen(false)} aria-label="Close">
                <XIcon className="h-4 w-4" />
              </button>
            </div>

            <div className="pf-opt-list">
              <SheetToggle label="Your camera" on={cameraOn} onToggle={onToggleCamera} />
              <SheetToggle label="Reference video" on={referenceOn} onToggle={onToggleReference} />
              <SheetToggle label="Mirror your camera" on={mirror} onToggle={onToggleMirror} />
            </div>

            <div className="pf-sheet-foot">
              <button
                className="pf-sheet-action"
                onClick={() => {
                  setShowHint((h) => !h);
                  setPanelOpen(false);
                }}
              >
                {showHint ? 'Hide hint' : 'Show a hint'}
              </button>
              <button
                className="pf-sheet-action"
                data-testid="practice-restart-sign"
                onClick={() => {
                  onRestartSign();
                  setPanelOpen(false);
                }}
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Restart sign
              </button>
              <button
                className="pf-sheet-action"
                data-testid="practice-back-sign"
                onClick={() => {
                  onBackSign();
                  setPanelOpen(false);
                }}
                disabled={!canBackSign}
              >
                <CornerUpLeft className="h-3.5 w-3.5" />
                Back a sign
              </button>
              <button
                className="pf-sheet-action"
                data-testid="self-report-skip"
                onClick={() => {
                  onSkip();
                  setPanelOpen(false);
                }}
              >
                Skip this sign →
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function SheetToggle({
  label,
  on,
  onToggle,
}: {
  label: string;
  on: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="pf-opt">
      <span className="pf-opt-label">{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-label={label}
        onClick={onToggle}
        className={cn('pf-switch', on && 'on')}
      >
        <span className="pf-switch-thumb" />
      </button>
    </div>
  );
}
