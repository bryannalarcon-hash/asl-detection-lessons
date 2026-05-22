import { describe, it, expect } from 'vitest';
import { createActor } from 'xstate';
import { practiceMachine, type PracticeSign } from '@/lib/machines/practice';

const SAMPLE_SIGNS: PracticeSign[] = [
  {
    id: 'sign-1',
    slug: 'hello',
    englishGloss: 'HELLO',
    drills: [
      { drillType: 'handshape', target: 'flat-B' },
      { drillType: 'movement', target: 'forward-arc' },
      { drillType: 'sign', target: 'HELLO' },
    ],
  },
  {
    id: 'sign-2',
    slug: 'thank-you',
    englishGloss: 'THANK_YOU',
    drills: [
      { drillType: 'handshape', target: 'flat-B' },
      { drillType: 'movement', target: 'forward-arc' },
      { drillType: 'sign', target: 'THANK_YOU' },
    ],
  },
];

function spawn() {
  const actor = createActor(practiceMachine, {
    input: { signs: SAMPLE_SIGNS, repsPerDrill: 3 },
  });
  actor.start();
  return actor;
}

function passOneRep(actor: ReturnType<typeof spawn>) {
  // Walk: PROMPT_SHOWN → COUNTDOWN → RECORDING → SELF_REPORT → PASS → (back to PROMPT_SHOWN or onward)
  actor.send({ type: 'COUNTDOWN_DONE' }); // PROMPT_SHOWN → COUNTDOWN
  actor.send({ type: 'REC_DONE' }); // COUNTDOWN → RECORDING
  actor.send({ type: 'REC_DONE' }); // RECORDING → SELF_REPORT
  actor.send({ type: 'PASS' }); // SELF_REPORT → REP_PASS → (always)
}

describe('practiceMachine', () => {
  it('initializes in IDLE with all indices at 0', () => {
    const actor = spawn();
    expect(actor.getSnapshot().value).toBe('IDLE');
    expect(actor.getSnapshot().context.signIndex).toBe(0);
    expect(actor.getSnapshot().context.drillIndex).toBe(0);
    expect(actor.getSnapshot().context.repIndex).toBe(0);
  });

  it('transitions IDLE → READY on START', () => {
    const actor = spawn();
    actor.send({ type: 'START' });
    expect(actor.getSnapshot().value).toBe('READY');
  });

  it('transitions READY → PROMPT_SHOWN on PROMPT_READY', () => {
    const actor = spawn();
    actor.send({ type: 'START' });
    actor.send({ type: 'PROMPT_READY' });
    expect(actor.getSnapshot().value).toBe('PROMPT_SHOWN');
  });

  it('transitions PROMPT_SHOWN → COUNTDOWN → RECORDING → SELF_REPORT', () => {
    const actor = spawn();
    actor.send({ type: 'START' });
    actor.send({ type: 'PROMPT_READY' });
    actor.send({ type: 'COUNTDOWN_DONE' });
    expect(actor.getSnapshot().value).toBe('COUNTDOWN');
    actor.send({ type: 'REC_DONE' });
    expect(actor.getSnapshot().value).toBe('RECORDING');
    actor.send({ type: 'REC_DONE' });
    expect(actor.getSnapshot().value).toBe('SELF_REPORT');
  });

  it('advances repIndex on PASS within a drill', () => {
    const actor = spawn();
    actor.send({ type: 'START' });
    actor.send({ type: 'PROMPT_READY' });
    expect(actor.getSnapshot().context.repIndex).toBe(0);
    passOneRep(actor);
    // After first pass: repIndex bumped to 1, machine is back at PROMPT_SHOWN.
    expect(actor.getSnapshot().context.repIndex).toBe(1);
    expect(actor.getSnapshot().value).toBe('PROMPT_SHOWN');
  });

  it('advances drillIndex after 3 passes on handshape', () => {
    const actor = spawn();
    actor.send({ type: 'START' });
    actor.send({ type: 'PROMPT_READY' });
    // 3 passes complete the handshape drill (drillIndex 0 → 1, movement).
    passOneRep(actor);
    passOneRep(actor);
    passOneRep(actor);
    const ctx = actor.getSnapshot().context;
    expect(ctx.drillIndex).toBe(1);
    expect(ctx.repIndex).toBe(0);
  });

  it('advances to next sign after 3 passes on the final sign drill', () => {
    const actor = spawn();
    actor.send({ type: 'START' });
    actor.send({ type: 'PROMPT_READY' });
    // Complete all 3 drills × 3 reps for sign 0.
    for (let drill = 0; drill < 3; drill++) {
      for (let rep = 0; rep < 3; rep++) {
        passOneRep(actor);
      }
    }
    const ctx = actor.getSnapshot().context;
    expect(ctx.signIndex).toBe(1);
    expect(ctx.drillIndex).toBe(0);
    expect(ctx.repIndex).toBe(0);
  });

  it('reaches LESSON_COMPLETE after the last sign finishes', () => {
    const actor = spawn();
    actor.send({ type: 'START' });
    actor.send({ type: 'PROMPT_READY' });
    // Two signs × 3 drills × 3 reps = 18 passes
    for (let sign = 0; sign < SAMPLE_SIGNS.length; sign++) {
      for (let drill = 0; drill < 3; drill++) {
        for (let rep = 0; rep < 3; rep++) {
          passOneRep(actor);
        }
      }
    }
    expect(actor.getSnapshot().value).toBe('LESSON_COMPLETE');
    expect(actor.getSnapshot().status).toBe('done');
  });

  it('SKIP_DRILL from SELF_REPORT advances drill without completing reps', () => {
    const actor = spawn();
    actor.send({ type: 'START' });
    actor.send({ type: 'PROMPT_READY' });
    actor.send({ type: 'COUNTDOWN_DONE' });
    actor.send({ type: 'REC_DONE' });
    actor.send({ type: 'REC_DONE' });
    // We're now in SELF_REPORT.
    expect(actor.getSnapshot().value).toBe('SELF_REPORT');
    actor.send({ type: 'SKIP_DRILL' });
    // Should land back in PROMPT_SHOWN for the next drill.
    expect(actor.getSnapshot().context.drillIndex).toBe(1);
    expect(actor.getSnapshot().context.repIndex).toBe(0);
  });

  it('sets lastOutcome to "pass" after a PASS event', () => {
    const actor = spawn();
    actor.send({ type: 'START' });
    actor.send({ type: 'PROMPT_READY' });
    actor.send({ type: 'COUNTDOWN_DONE' });
    actor.send({ type: 'REC_DONE' });
    actor.send({ type: 'REC_DONE' });
    actor.send({ type: 'PASS' });
    expect(actor.getSnapshot().context.lastOutcome).toBe('pass');
  });
});
