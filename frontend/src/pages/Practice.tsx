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
import {
  readLessonConfig,
  isAutoSegment,
  type LessonConfig,
} from '@/lib/lesson-config';
import { FALLBACK_SIGNS } from '@/lib/fallback-lesson';
import { CameraPanel } from '@/components/practice/CameraPanel';
import { ReferenceVideo } from '@/components/practice/ReferenceVideo';
import { DrillIndicator } from '@/components/practice/DrillIndicator';
import { RepCounter } from '@/components/practice/RepCounter';
import { SelfReportRow } from '@/components/practice/SelfReportRow';
import { DevPanel } from '@/components/practice/DevPanel';
import { HintButton } from '@/components/practice/HintButton';
import { BoundingBox, type BoxState } from '@/components/practice/BoundingBox';
import { PracticeHeader } from '@/components/practice/PracticeHeader';
import { PauseOverlay } from '@/components/practice/PauseOverlay';
import { SignCompleteToast } from '@/components/practice/SignCompleteToast';
import {
  readResume,
  writeResume,
  clearResume,
} from '@/lib/practice-resume';
import type { DrillType } from '@/cv/types';

/**
 * Build practice signs from backend data. The lesson plan presents only the
 * full-sign stage, so the handshape/movement drills are dropped here and each
 * sign keeps exactly one drill (`drillType === 'sign'`). When the backend
 * omits a sign drill, the first available drill is retargeted as the sign so
 * the sign still has a stage to run.
 */
function buildSignsFromBackend(
  signs: { id: string; slug: string; englishGloss: string }[],
  drills: { signId: string; drillType: DrillType; targetString: string; orderIndex: number }[]
): PracticeSign[] {
  return signs.map((sign) => {
    const signDrills = drills
      .filter((d) => d.signId === sign.id)
      .sort((a, b) => a.orderIndex - b.orderIndex)
      .map((d) => ({ drillType: d.drillType, target: d.targetString }));
    return {
      id: sign.id,
      slug: sign.slug,
      englishGloss: sign.englishGloss,
      drills: toFullSignDrills(signDrills, sign.englishGloss),
    };
  });
}

/**
 * Collapse a sign's drill list to a single full-sign drill. Prefers the
 * existing `sign` stage (carrying any reps/segment overlay); falls back to the
 * first drill retargeted as the sign, or a synthesized drill when the list is
 * empty, so every sign always has exactly one stage to practice.
 */
function toFullSignDrills(
  drills: PracticeSign['drills'],
  englishGloss: string
): PracticeSign['drills'] {
  const signDrill = drills.find((d) => d.drillType === 'sign');
  if (signDrill) return [signDrill];
  const first = drills[0];
  if (first) return [{ ...first, drillType: 'sign' }];
  return [{ drillType: 'sign', target: englishGloss }];
}

/**
 * Apply a dev Lesson Config overlay onto the default signs. The overlay's sign
 * list defines the lesson's sign count and order; each entry carries per-stage
 * reps + clip trim. We overlay onto each sign's existing drills by matching
 * stage (drillType). Unknown slugs are dropped. An unset trim ({0,0}) is left
 * off so the reference video falls back to its natural segment.
 */
function applyLessonConfig(
  defaults: PracticeSign[],
  config: LessonConfig
): PracticeSign[] {
  const bySlug = new Map(defaults.map((s) => [s.slug, s]));
  const out: PracticeSign[] = [];
  for (const sc of config.signs) {
    const base = bySlug.get(sc.sign);
    if (!base) continue;
    out.push({
      ...base,
      videoSrc: sc.videoSrc,
      drills: base.drills.map((d) => {
        const stage = sc.stages[d.drillType];
        if (!stage) return d;
        return {
          ...d,
          reps: stage.reps,
          segment: isAutoSegment(stage.segment) ? undefined : stage.segment,
        };
      }),
    });
  }
  return out.length > 0 ? out : defaults;
}

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
      const t = window.setTimeout(() => {
        // Flip the box BEFORE sending PASS so the post-advance SELF_REPORT
        // re-render doesn't see a still-green box and chain-fire.
        setBoxState('orange');
        send({ type: 'PASS' });
      }, 350);
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
    }
    prevSignIndexRef.current = next;
    prevSignGlossRef.current = currentSign?.englishGloss ?? null;
  }, [state.context.signIndex, currentSign]);

  // CTA label: within-sign rep advances read "Next rep (X of N) →"; the last
  // rep of a sign (next press starts a new word) reads "Continue →".
  const continueLabel = computeContinueLabel({
    repIndex: state.context.repIndex,
    repTotal: repsForCurrentSign,
  });

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
        />

        <SignCompleteToast
          sign={congratsSign}
          onDismiss={() => setCongratsSign(null)}
        />
      </main>
    </div>
  );
}

/**
 * Advance-button label. With the full-sign-only plan a sign has one drill, so
 * a drill transition is a word transition. If reps remain in the current sign
 * the next press advances a rep -> "Next rep (X of N) →". On the last rep the
 * next press moves to a different word -> "Continue →".
 */
function computeContinueLabel({
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

function CameraPanelWrapper({
  boxState,
  mirror,
  paused,
}: {
  boxState: BoxState;
  mirror: boolean;
  paused: boolean;
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
  return <CameraPanel boxState={boxState} mirror={mirror} paused={paused} />;
}
