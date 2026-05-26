import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMachine } from '@xstate/react';
import { useQuery } from '@tanstack/react-query';
import { RotateCcw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { isDevToolsEnabled } from '@/lib/env';
import { lessonsApi } from '@/lib/api';
import { useAppSettings } from '@/lib/settings';
import {
  practiceMachine,
  selectCurrentDrill,
  selectCurrentSign,
  effectiveReps,
  type PracticeSign,
} from '@/lib/machines/practice';
import { readLessonConfig } from '@/lib/lesson-config';
import { FALLBACK_SIGNS } from '@/lib/fallback-lesson';
import {
  buildSignsFromBackend,
  applyLessonConfig,
} from '@/lib/practice-signs';
import { ReferenceVideo } from '@/components/practice/ReferenceVideo';
import { DrillIndicator } from '@/components/practice/DrillIndicator';
import { RepCounter } from '@/components/practice/RepCounter';
import { SelfReportRow } from '@/components/practice/SelfReportRow';
import { RecordAttemptRow } from '@/components/practice/RecordAttemptRow';
import { DevPanel } from '@/components/practice/DevPanel';
import {
  CvReadout,
  readCvReadoutPref,
  writeCvReadoutPref,
} from '@/components/practice/CvReadout';
import { HintButton } from '@/components/practice/HintButton';
import { type BoxState } from '@/components/practice/BoundingBox';
import { PracticeHeader } from '@/components/practice/PracticeHeader';
import { PauseOverlay } from '@/components/practice/PauseOverlay';
import { SignCompleteToast } from '@/components/practice/SignCompleteToast';
import {
  readResume,
  writeResume,
  clearResume,
} from '@/lib/practice-resume';
import { useCaptureRep } from '@/hooks/useCaptureRep';
import { CameraPanelWrapper, computeContinueLabel } from './practice-helpers';
import { getSignHint } from '@/data/sign-hints';
import { diagnoseAttempt } from '@/lib/hint-diagnosis';
import type { DrillType } from '@/cv/types';

export default function PracticePage() {
  const { slug = '' } = useParams<{ slug: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { settings } = useAppSettings();

  // URL state controls camera/reference visibility — supports mid-lesson toggles.
  const cameraOn = (searchParams.get('camera') ?? (settings.cameraDefault ? '1' : '0')) === '1';
  const referenceOn =
    (searchParams.get('reference') ?? (settings.referenceDefault ? '1' : '0')) === '1';

  const setSearchParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    next.set(key, value);
    navigate({ search: next.toString() }, { replace: true });
  };

  const lessonQuery = useQuery({
    queryKey: ['lessons', 'get', slug],
    queryFn: () => lessonsApi.get(slug),
    retry: 0,
    refetchOnWindowFocus: false,
    enabled: Boolean(slug),
  });

  const signs = useMemo<PracticeSign[]>(() => {
    let base = FALLBACK_SIGNS;
    if (lessonQuery.data) {
      const built = buildSignsFromBackend(
        lessonQuery.data.signs,
        lessonQuery.data.drillDefinitions
      );
      base = built.length > 0 ? built : FALLBACK_SIGNS;
    }
    // Dev-only overlay. Gated so prod (VITE_DEV_TOOLS=0) never reads or applies
    // it — `isDevToolsEnabled()` collapses to `false` and DCE drops this branch.
    if (isDevToolsEnabled()) {
      const config = readLessonConfig(slug);
      if (config) return applyLessonConfig(base, config);
    }
    return base;
  }, [lessonQuery.data, slug]);

  // Resume cursor — restored from localStorage if recent (<7 days).
  const restored = useMemo(() => readResume(slug), [slug]);

  const [state, send] = useMachine(practiceMachine, {
    input: {
      signs,
      repsPerDrill: 3,
      initialSignIndex: restored?.signIndex,
      initialDrillIndex: restored?.drillIndex,
      initialRepIndex: restored?.repIndex,
    },
  });

  // Persist on every cursor change.
  useEffect(() => {
    if (!slug) return;
    if (state.matches('LESSON_COMPLETE')) {
      clearResume(slug);
      return;
    }
    writeResume(slug, {
      signIndex: state.context.signIndex,
      drillIndex: state.context.drillIndex,
      repIndex: state.context.repIndex,
    });
  }, [
    slug,
    state,
    state.context.signIndex,
    state.context.drillIndex,
    state.context.repIndex,
  ]);

  // Kick off the machine on mount.
  useEffect(() => {
    if (state.matches('IDLE')) {
      send({ type: 'START' });
      send({ type: 'PROMPT_READY' });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [boxState, setBoxState] = useState<BoxState>('gray');

  // In-browser CV capture. Degrades to self-report when init fails (notReady).
  const capture = useCaptureRep();
  const { resetVerdict } = capture;
  const videoElRef = useRef<HTMLVideoElement | null>(null);
  const [showRetry, setShowRetry] = useState(false);
  // Dev-only CV diagnostics overlay, toggled from the dev panel (persisted).
  const [cvReadoutOn, setCvReadoutOn] = useState(readCvReadoutPref);
  // Bumped once per fresh failed recorded attempt to auto-open the targeted hint.
  const [hintOpenSignal, setHintOpenSignal] = useState(0);

  // Auto-advance: a single green box advances exactly one rep, then drops
  // back to orange. The next rep needs its own green trigger — the box must
  // leave green and re-enter green before another PASS fires. Without the
  // ref-guard, the fast-forward effect can chain through several SELF_REPORT
  // entries while boxState is still 'green' and rip through the whole lesson.
  const greenFiredRef = useRef(false);
  useEffect(() => {
    if (boxState !== 'green') {
      // Reset the latch so the next green can fire.
      greenFiredRef.current = false;
      return;
    }
    if (greenFiredRef.current) return;
    if (state.matches('SELF_REPORT')) {
      greenFiredRef.current = true;
      // Hold the green result for ~3s so the learner sees the pass before we
      // advance (auto-pass still fires, just not instantly).
      const t = window.setTimeout(() => {
        // Flip the box BEFORE sending PASS so the post-advance SELF_REPORT
        // re-render doesn't see a still-green box and chain-fire.
        setBoxState('orange');
        send({ type: 'PASS' });
      }, 3000);
      return () => window.clearTimeout(t);
    }
    // Green outside SELF_REPORT (between reps) — just flash back to orange.
    const t = window.setTimeout(() => setBoxState('orange'), 600);
    return () => window.clearTimeout(t);
  }, [boxState, state, send]);

  const currentSign = selectCurrentSign(state.context);
  const currentDrill = selectCurrentDrill(state.context);
  // Per-sign reps from the dev overlay (falls back to the machine default).
  const repsForCurrentSign = effectiveReps(state.context);
  const drillTypes = useMemo<DrillType[]>(
    () => currentSign?.drills.map((d) => d.drillType) ?? ['sign'],
    [currentSign]
  );

  // Fast-forward PROMPT_SHOWN → SELF_REPORT in mock-CV mode. Three events needed.
  useEffect(() => {
    if (state.matches('PROMPT_SHOWN')) {
      send({ type: 'COUNTDOWN_DONE' });
      send({ type: 'REC_DONE' });
      send({ type: 'REC_DONE' });
    }
  }, [state, send]);

  const isComplete = state.matches('LESSON_COMPLETE');
  useEffect(() => {
    if (isComplete) navigate(`/lessons/${slug}/complete`);
  }, [isComplete, navigate, slug]);

  const showCamera = cameraOn;
  const showReference = referenceOn;

  // Pause modal
  const [paused, setPaused] = useState(false);

  // Back-navigation enable flags
  const canBackDrill = state.context.drillIndex > 0;
  const canBackSign = state.context.signIndex > 0;

  // Track whether the current sign has had any skip — controls the congrats popup.
  const signSkippedRef = useRef(false);
  useEffect(() => {
    if (state.context.lastOutcome === 'skip') {
      signSkippedRef.current = true;
    }
  }, [state.context.lastOutcome]);

  // Detect sign advance — when signIndex increments while still in the lesson,
  // and the just-completed sign was NOT skipped at any rep, pop the congrats toast.
  const prevSignIndexRef = useRef(state.context.signIndex);
  const prevSignGlossRef = useRef<string | null>(currentSign?.englishGloss ?? null);
  const [congratsSign, setCongratsSign] = useState<string | null>(null);
  useEffect(() => {
    const prev = prevSignIndexRef.current;
    const next = state.context.signIndex;
    if (next > prev) {
      if (!signSkippedRef.current && prevSignGlossRef.current) {
        setCongratsSign(prevSignGlossRef.current);
      }
      signSkippedRef.current = false;
      // Clear CV feedback so it doesn't bleed into the next sign.
      setShowRetry(false);
      setBoxState('gray');
      // Drop the last verdict too, so manually opening the hint on the new
      // sign can't surface the previous sign's targeted diagnosis.
      resetVerdict();
    }
    prevSignIndexRef.current = next;
    prevSignGlossRef.current = currentSign?.englishGloss ?? null;
  }, [state.context.signIndex, currentSign, resetVerdict]);

  // CTA label: within-sign rep advances read "Next rep (X of N) →"; the last
  // rep of a sign (next press starts a new word) reads "Continue →".
  const continueLabel = computeContinueLabel({
    repIndex: state.context.repIndex,
    repTotal: repsForCurrentSign,
  });

  // Target gloss for the CV model — sign's gloss uppercased (gloss_to_idx keys
  // are like 'MOM','DAD'). CV is offered only when the model knows this gloss.
  const targetGloss = currentSign?.englishGloss.toUpperCase() ?? '';
  const cvAvailable =
    capture.ready && !capture.notReady && targetGloss.length > 0 && capture.hasGloss(targetGloss);

  // Run one in-browser CV rep. On pass: green box + match score + PASS event
  // (the auto-advance effect picks up green-in-SELF_REPORT). On fail: orange +
  // a brief "try again". Any null verdict (skipped/empty/error) leaves the
  // self-report flow untouched.
  const onRecordAttempt = async () => {
    const videoEl = videoElRef.current;
    if (!videoEl || !cvAvailable) return;
    setShowRetry(false);
    setBoxState('orange');
    const verdict = await capture.recordAttempt(videoEl, targetGloss);
    if (!verdict) {
      setBoxState('orange');
      return;
    }
    if (verdict.pass) {
      setBoxState('green');
    } else {
      setBoxState('red');
      setShowRetry(true);
      // Surface the targeted hint for this failed attempt (debounced via the
      // monotonic signal — HintButton opens once per bump, not per render).
      setHintOpenSignal((n) => n + 1);
    }
  };

  // Hint copy: an unprompted open shows the word-tied default; a failed recorded
  // attempt swaps in a targeted, parameter-specific diagnosis of what went wrong.
  const signHint = useMemo(
    () => (currentSign ? getSignHint(currentSign.englishGloss) : null),
    [currentSign]
  );
  const { lastVerdict } = capture;
  const attemptHint = useMemo(
    () => (lastVerdict && !lastVerdict.pass ? diagnoseAttempt(lastVerdict, signHint) : null),
    [lastVerdict, signHint]
  );

  // Restart sign — clear progress on the current sign without losing position.
  const restartSign = () => {
    // Walk the machine back to drill 0 / rep 0 of the current sign by sending
    // BACK_DRILL repeatedly. Cheaper than introducing a new machine event.
    for (let i = 0; i < drillTypes.length; i++) send({ type: 'BACK_DRILL' });
  };

  return (
    <div
      data-testid="page-practice"
      data-mode={`${cameraOn ? 'cam' : 'nocam'}-${referenceOn ? 'ref' : 'noref'}`}
      className="flex min-h-screen flex-col bg-bg text-fg"
    >
      {paused && (
        <PauseOverlay
          onResume={() => setPaused(false)}
          onExit={() => navigate('/dashboard')}
        />
      )}

      <PracticeHeader
        lessonTitle={lessonQuery.data?.lesson?.title ?? slug}
        lessonSlug={slug}
        signIndex={state.context.signIndex}
        signTotal={state.context.signs.length}
        canBackDrill={canBackDrill}
        canBackSign={canBackSign}
        cameraOn={cameraOn}
        onBackDrill={() => send({ type: 'BACK_DRILL' })}
        onBackSign={() => send({ type: 'BACK_SIGN' })}
        onToggleCamera={() => setSearchParam('camera', cameraOn ? '0' : '1')}
        onPause={() => setPaused(true)}
        onExit={() => navigate('/dashboard')}
      />

      <main className="mx-auto w-full max-w-[1240px] flex-1 px-6 pb-16 pt-8">
        {/* Hero row — title (gloss) + rep counter */}
        {currentSign && (
          <section className="mb-7 flex flex-wrap items-end justify-between gap-8">
            <div className="min-w-0 flex-1">
              <p className="font-mono text-[0.72rem] uppercase tracking-[0.12em] text-fg-muted">
                Now signing
              </p>
              <h1
                className="font-display mt-2 text-[clamp(2.6rem,6vw,5rem)] font-extrabold leading-[0.95] tracking-tight text-fg"
              >
                {currentSign.englishGloss}
              </h1>
            </div>
            <RepCounter
              current={state.context.repIndex}
              total={repsForCurrentSign}
            />
          </section>
        )}

        {/* Stage pill tabs — hidden when a sign has a single (full-sign) stage. */}
        {currentDrill && drillTypes.length > 1 && (
          <section className="mb-7">
            <DrillIndicator current={currentDrill.drillType} drills={drillTypes} />
          </section>
        )}

        {/* Side-by-side media cells */}
        <section
          className={cn(
            'mb-6 grid gap-4',
            showCamera && showReference ? 'md:grid-cols-2' : 'md:grid-cols-1'
          )}
        >
          {showCamera && (
            <CameraPanelWrapper
              boxState={boxState}
              mirror={settings.mirror}
              paused={paused}
              onVideoEl={(el) => {
                videoElRef.current = el;
              }}
            />
          )}
          {showReference && currentSign && (
            <ReferenceVideo
              signSlug={currentSign.slug}
              englishGloss={currentSign.englishGloss}
              drillType={currentDrill?.drillType}
              paused={paused}
              videoSrc={currentSign.videoSrc}
              segmentOverride={currentDrill?.segment}
            />
          )}
          {!showCamera && !showReference && currentSign && (
            <div className="rounded-[12px] border border-border bg-bg-paper p-8 text-center">
              <p className="font-mono text-[0.72rem] uppercase tracking-[0.12em] text-fg-muted">
                Quiz mode
              </p>
              <p className="mt-2 text-lg">
                Sign &ldquo;{currentSign.englishGloss}&rdquo; from memory.
              </p>
            </div>
          )}
        </section>

        {/* Hint row — bordered top + bottom */}
        {currentSign && currentDrill && (
          <section className="my-6 flex flex-wrap items-center justify-between gap-3 border-y border-border py-4">
            <HintButton
              signSlug={currentSign.slug}
              englishGloss={currentSign.englishGloss}
              failCount={state.context.signFailCount}
              defaultHint={signHint?.default}
              attemptHint={attemptHint}
              openSignal={hintOpenSignal}
            />
            <button
              type="button"
              data-testid="practice-restart-sign"
              onClick={restartSign}
              className="inline-flex h-8 items-center gap-1.5 rounded-md px-3 font-mono text-[0.78rem] text-fg-muted transition-[background-color,color] duration-150 ease-out hover:bg-bg-elev hover:text-fg focus-visible:outline-2 focus-visible:outline-accent-ring focus-visible:outline-offset-2"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Restart sign
            </button>
          </section>
        )}

        {/* CTA row */}
        {currentSign && currentDrill && (
          <section className="flex flex-col gap-3">
            <SelfReportRow
              signId={currentSign.id}
              drillType={currentDrill.drillType}
              onPass={() => send({ type: 'PASS' })}
              onSkip={() => send({ type: 'SKIP' })}
              continueLabel={continueLabel}
              skipLabel="Skip this sign →"
            />
            {cvAvailable && (
              <RecordAttemptRow
                phase={capture.phase}
                countdown={capture.countdown}
                disabled={capture.recording || !videoElRef.current}
                showRetry={showRetry}
                onRecord={() => void onRecordAttempt()}
              />
            )}
            <p
              data-testid="practice-advance-help"
              className="text-center font-mono text-[0.76rem] text-fg-subtle"
            >
              Tap continue when you&rsquo;re ready &mdash; or the camera will auto-advance once
              it detects a match
              <span
                aria-hidden="true"
                className="ml-1.5 inline-block h-2 w-2 rounded-full bg-success align-middle shadow-[0_0_4px_rgba(52,211,153,0.6)]"
              />
              .
            </p>
          </section>
        )}

        <DevPanel
          onSetGray={() => setBoxState('gray')}
          onSetOrange={() => setBoxState('orange')}
          onSetGreen={() => setBoxState('green')}
          onSkipDrill={() => send({ type: 'SKIP_DRILL' })}
          onAutoPassRep={() => send({ type: 'PASS' })}
          onFailRep={() => send({ type: 'FAIL' })}
          cvReadoutOn={cvReadoutOn}
          onToggleCvReadout={() =>
            setCvReadoutOn((v) => {
              const next = !v;
              writeCvReadoutPref(next);
              return next;
            })
          }
        />

        {cvReadoutOn && (
          <CvReadout
            verdict={capture.lastVerdict}
            backend={capture.backend}
            ready={capture.ready}
            notReady={capture.notReady}
            target={targetGloss}
          />
        )}

        <SignCompleteToast
          sign={congratsSign}
          onDismiss={() => setCongratsSign(null)}
        />
      </main>
    </div>
  );
}
