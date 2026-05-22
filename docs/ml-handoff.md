# ML Model Handoff

For the ML team (and any future model author) integrating their trained model into the front-end. Read alongside [`principles.md`](./principles.md), [`ux-spec.md`](./ux-spec.md), and [`training-plan.md`](./training-plan.md).

The pilot's v1 frontend ships with **no real CV** — all bounding-box state transitions are user-controlled via dev panel buttons. This doc describes the contract your model must satisfy to be slotted into v2, and the exact integration points where it plugs in.

---

## TL;DR for the ML team

- The frontend will call **one async function**: `evaluate(drillType, target, frames) → DetectionResult`
- You will deliver this as a JavaScript module exporting that function. We don't care if it's WASM, WebGPU, or pure JS underneath.
- The model is expected to **constrain its evaluation to the expected target**, not return open-vocabulary argmax. This is per the PopSignAI lesson documented in `competitive/comparison.md`: the question we ask the model is "did the learner produce *this specific thing*?", not "what did the learner produce?"
- **Out-of-distribution rejection is required.** A sloppy or absent attempt must produce a low-confidence result, not an accidental pass.
- Three drill types need detection: `'handshape'`, `'movement'`, `'sign'`. They may share a backbone (Stage 1 keypoints) but their decision functions differ.

If you can satisfy that, the integration is a one-file swap.

---

## The integration contract

### Why two calls, not one

A single `evaluate(frames)` shape doesn't fit the budget. Stage 1 (keypoint detector) must run **per frame at ~30 FPS**; running it inside `evaluate()` over an array of 90 frames blows the 200ms p95 budget by an order of magnitude. The contract splits inference into a **per-frame streaming call** (Stage 1) and a **per-rep evaluation call** (Stage 2 + drill detector).

This also resolves the Stage 1 sharing question — Stage 1 runs once per frame, its keypoints are cached internally, and the per-rep call reads from that cache.

### TypeScript interface (canonical)

```typescript
// === Loading ===

// Called once at app start. Loads weights, picks the backend (WebGPU vs WASM),
// runs a warm-up inference. After this resolves, processFrame/evaluateRep are safe to call.
export async function init(config?: {
  modelBundleUrl?: string;           // defaults to /models/asl-v2.json
  preferredBackend?: 'webgpu' | 'wasm';  // default: 'webgpu' if available, else 'wasm'
}): Promise<{
  modelVersion: string;              // semver string for cache-busting and A/B
  backend: 'webgpu' | 'wasm';
  warmupLatencyMs: number;
}>;

// === Per-frame streaming (called continuously during recording) ===

export interface Frame {
  timestamp: number;                 // ms since epoch (capture time, not decode time)
  imageData: ImageBitmap;            // RGB, 8-bit per channel, sRGB color space
                                     // Resolution: 640×480 minimum (camera native)
                                     // The frontend hands you the UN-mirrored stream
                                     // (mirroring is a display-only transform on the preview)
}

// Returns the current bounding-box state for the live UI.
// Must complete in <33ms to keep the camera pipeline at 30 FPS.
// Caches keypoints internally for the next evaluateRep() call.
export function processFrame(frame: Frame): {
  state: 'no-hands' | 'hands-detected';
  framesBuffered: number;            // how many frames in the rolling buffer
};

// === Per-rep evaluation (called once at end of rep window) ===

export type DrillType = 'handshape' | 'movement' | 'sign';

export interface DetectionResult {
  state: 'target-met' | 'low-confidence' | 'no-hands';
  confidence: number;                // 0..1, calibrated probability the target was produced
  oodScore?: number;                 // 0..1, out-of-distribution score; high = unlike anything in training
  parameter?: 'handshape' | 'movement' | 'palm-orientation' | 'location' | 'timing' | 'framing';
  detail?: string;                   // optional human-readable diagnostic
  latencyMs: number;                 // your inference time for this call
  modelVersion: string;              // matches what init() returned
}

// Evaluates the most recent rep window against the expected target.
// Uses the keypoints already cached by processFrame() — does NOT re-run Stage 1.
// Must complete in <200ms p95.
export async function evaluateRep(
  drillType: DrillType,
  target: string                     // e.g. 'flat-B', 'forward-arc', 'THANK_YOU'
): Promise<DetectionResult>;

// === Lifecycle ===

// Called by the frontend between reps to clear the keypoint buffer.
export function resetRepBuffer(): void;

// Called at app shutdown / model swap.
export async function dispose(): Promise<void>;
```

### Frame format — explicit spec

| Property | Value | Notes |
|---|---|---|
| Color space | sRGB | Browser default from `getUserMedia()` |
| Bit depth | 8 bits per channel | RGB, no alpha |
| Resolution | 640×480 minimum (camera native, typically 1280×720) | Don't assume any specific resolution; resize/letterbox internally to whatever your model needs |
| Mirroring | **Un-mirrored** (raw camera stream) | The mirrored display is a CSS transform on the preview only. You receive the canonical orientation. |
| Frame rate | ~30 FPS target, may drop on low-end devices | Don't trust `requestAnimationFrame` timing; use the `timestamp` field |
| Pixel format | `ImageBitmap` (transferable) | Mutate freely; the frontend doesn't keep the reference after handing it to you |
| Rep window | 3 seconds typical, configurable in frontend | `framesBuffered` ≈ 90 at 30 FPS |

If your model trained on 384×384 RGB (per `training-plan.md` Stage 1), do the resize+center-crop inside your module. The frontend is not responsible for matching training resolution.

### Temporal window — 90 frames vs T=64

The frontend captures ~90 frames per rep (~3s @ 30fps). The hoyso architecture uses T=64. **You handle the temporal alignment inside your module** — typically by resampling to T=64 in the Stage 2 input pipeline. Don't expect the frontend to pre-sample.

### Per-drill semantics

| `drillType` | `target` example | What you're checking | Suggested signal source |
|---|---|---|---|
| `'handshape'` | `'flat-B'`, `'5'`, `'X'`, `'flat-O'` | Is the user's hand currently in the expected handshape? Mostly static. | Stage 1 keypoints → handshape classifier OR rule-based feature checks on finger joints |
| `'movement'` | `'forward-arc'`, `'downward'`, `'circular-cw'` | Did the user's hand trace the expected trajectory? Temporal. | Stage 1 keypoint sequence → trajectory match (DTW, learned classifier, or heuristic) |
| `'sign'` | `'THANK_YOU'`, `'NICE'`, `'HELLO'` | Did the user produce the expected sign overall? Composite. | Stage 2 hoyso48-style classifier → return p(target) |

Per-drill detectors are **independent deliverables**. You can ship handshape detection while movement and sign are still in training; the frontend will use what you give it.

### State machine the frontend expects

Two state fields, returned by two different calls:

| Call | Returned state | Bounding box | Rep counts? |
|---|---|---|---|
| `processFrame()` | `'no-hands'` | **Gray** | n/a (in-progress) |
| `processFrame()` | `'hands-detected'` | **Orange** | n/a (in-progress) |
| `evaluateRep()` | `'target-met'` | **Green** | Yes — pass |
| `evaluateRep()` | `'low-confidence'` | Stays orange / fades; UI shows retry CTA | No |
| `evaluateRep()` | `'no-hands'` | Gray; UI shows "we didn't see your hands" CTA | No |

Recommended thresholds (deployment-tunable):

- `'target-met'`: `confidence ≥ 0.85` AND `oodScore ≤ 0.30`
- `'low-confidence'`: `0.20 < confidence < 0.85` OR `oodScore > 0.30`
- `'no-hands'` from `evaluateRep`: returned if Stage 1 found no hands in the rep window (independent of confidence)

You may recommend different thresholds per drill type via documentation; the frontend exposes them as config.

### What NOT to do

- **Don't return `'target-met'` when the user signed nothing.** This is the PopSignAI failure mode — argmax over a constrained set will always pick *something*. Your `state` machine must distinguish "I'm confident they did the right thing" from "I'm not sure but among the options this is closest."
- **Don't depend on a server.** All inference runs in-browser. Network calls during a rep are forbidden by Req 5 (browser-first inference) and Req 13 (privacy / no upload).
- **Don't trust frame timing.** Browsers throttle `requestAnimationFrame` on hidden tabs and low-power devices. The frame array may have variable spacing; design accordingly.

---

## Where in the codebase your module plugs in

We don't have the codebase scaffolded yet, but the planned shape:

```
frontend/
├── public/
│   └── models/             # your model bundle lives here
│       └── asl-stub.json   # v1 stub manifest pointing at nothing
├── src/
│   ├── cv/
│   │   ├── evaluate.ts     # the public function the frontend imports
│   │   ├── evaluate.mock.ts  # v1 implementation — returns DetectionResult from the dev panel state
│   │   └── evaluate.real.ts  # v2 — your code, or imports your module
│   └── ...
```

In v1, `evaluate.ts` re-exports `evaluate.mock.ts`. To slot in your model:

1. Build your inference module as a single JS/TS file exporting `evaluate` matching the interface above.
2. Drop it at `frontend/src/cv/evaluate.real.ts`.
3. Drop the model weights / ONNX file at `frontend/public/models/`.
4. Change `evaluate.ts` to re-export from `evaluate.real.ts`.
5. Set `VITE_DEV_MODE=0` for production builds — the mock dev panel disappears automatically.

That's the entire integration. No re-routing of state, no API changes, no test rewrites beyond updating the dev panel tests.

---

## Test fixtures we'll need from you

To run our Playwright e2e tests against the real model (rather than just the mock), we'll need:

- **A deterministic frame sequence** (~90 frames at 30fps) labeled with the expected `DetectionResult` for each drill type. We feed this through `evaluate()` in CI to detect regressions.
- **At least one "definitely target-met" sequence per drill type.** Used to test the green-state UI path.
- **At least one "definitely low-confidence" sequence per drill type.** Used to test OOD rejection.
- **At least one "no hands in frame" sequence.** Used to test the gray-state UI path.

Frame format: PNG sequence or single MP4 we can decode with `MediaSource`. Put them in `frontend/test-fixtures/cv/` with a manifest JSON describing expected outputs.

---

## Performance budget

| Metric | Target | Hard ceiling | Notes |
|---|---|---|---|
| `processFrame()` latency | ≤ 25ms p95 | 33ms p95 | Must not stall the 30 FPS camera pipeline |
| `evaluateRep()` latency | ≤ 150ms p50, ≤ 200ms p95 | 500ms p99 | Stage 2 + drill detector only — Stage 1 already done |
| `init()` latency | ≤ 5s (cold) | 15s (cold) | Includes weight download; subsequent loads from browser cache should be ≤ 500ms |
| Frame buffer size | 90 frames (3s @ 30fps) | 180 frames (6s @ 30fps) | |
| **Model bundle size** | **≤ 25MB total** | 40MB | Stage 1 (~10M params) + Stage 2 won't fit in 10MB. Use INT8 quantization. **Single-seed distilled student strongly preferred over 4-seed ensemble.** |
| Memory footprint at inference | ≤ 500MB | 1GB | |
| Browser requirements | Chrome/Edge 113+ (WebGPU), Firefox 121+ (WebGPU experimental), Safari 17+ | WASM fallback for older browsers | You handle backend selection in `init()` |
| Warm-up overhead | First `evaluateRep()` may be 2–5× slower than steady-state | Up to 1s for first call | Run warm-up inference inside `init()` to absorb this |

### Bundle size — ensemble vs distillation decision

`training-plan.md` Stage 2 calls for a 4-seed ensemble (probability average), citing hoyso48's setup. At 1.85M params × FP32 × 4 seeds = ~28MB just for Stage 2, before Stage 1. **The 4-seed ensemble does not fit the budget.** Two paths forward:

- **Distill** the 4-seed ensemble into a single-seed student (hoyso flagged this as an open question; it's now load-bearing for deployment)
- **Quantize aggressively** — INT8 brings each seed to ~2MB, and 4 × 2MB + Stage 1 INT8 (~10MB) = ~18MB. Tight but feasible.

Distillation is the cleaner answer. Coordinate with the product team before training the final v2 weights.

Latency over 200ms p95 doesn't kill the feature but kills the "snappy" feel. If you can't meet it, surface early so UI adjusts (longer "Evaluating..." spinner is fine up to ~2s per NN/g).

---

## v2 deployment gates

From [`principles.md`](./principles.md). The OOD gate (#3 below) is being added to principles.md in the same edit pass as this doc — they should match.

1. **Top-1 ≥ 92%** on the expected target across a held-out test set of **≥ 5 actual ASL-1 learners** (not the Kaggle/PopSign Deaf-signer pool).
2. **Top-3 ≥ 98%** on same.
3. **OOD rejection rate ≥ 90%** — when the learner signs something else (or nothing), `evaluateRep()` must return `'low-confidence'` or `'no-hands'`, not `'target-met'`.
4. **`evaluateRep()` p95 latency ≤ 200ms** AND **`processFrame()` p95 ≤ 33ms** on the lowest-spec target laptop (integrated GPU, WebGPU enabled).
5. **2-week A/B pilot**: CV arm shows no worse confidence/usage retention than mirror arm AND equal-or-better vocab quiz performance at week 2.

Gates 1–3 are measured **per drill type**. Handshape and movement are generally easier than full sign; quote per-drill numbers in your eval. The product team will accept per-drill threshold relaxations with justification.

**The PopSignAI lesson**: publish both your **constrained-target accuracy** (your gates above — "given the learner attempted target X, was X correctly accepted/rejected?") and your **open-vocabulary accuracy** ("which of all 75 signs does the model think they did?") when you ship. Don't headline the constrained number without footnoting the open-vocab number — that's the credibility trap PopSignAI fell into.

### Open-vocabulary measurement set

For the open-vocab number, use the **deployed pilot vocabulary of 75–100 signs**, not the Kaggle 250 or ASL Citizen 2731. The deployment context is what matters for credibility, not the training-set size.

---

## What the frontend does between v1 and v2

| Phase | Frontend behavior | Your responsibility |
|---|---|---|
| v1 (now) | Mock `evaluate()` returns whatever the dev panel buttons set. Bounding box driven by user clicks. | None — keep training. |
| Pre-v2 (your model partially ready) | Frontend keeps mock, your detectors run in shadow mode if you want to measure latency in real users' browsers | Optionally ship a stub module that logs but doesn't display. |
| v2 cutover | Frontend swaps `evaluate.mock` for `evaluate.real`. Dev panel hidden in production. | Ship the module, weights, and test fixtures. Sign off on the latency/accuracy gates. |
| Post-v2 | A/B between mock-self-report arm and your CV arm | Help interpret retention metrics. |

---

## How auth, sessions, and progress relate to your work

**They don't.** Your module is stateless — it receives a frame sequence, returns a `DetectionResult`. It doesn't know who the user is, what lesson they're on, or what their progress state is. All of that is the frontend + backend's problem.

The only handoff between session state and CV is the `target` argument: "for *this* rep, look for *this* handshape / movement / sign." The frontend constructs that from the current Lesson + Sign + Drill state.

This means **you can develop and test your model entirely in isolation** — no backend, no auth, no Postgres. Just a frame sequence in, a `DetectionResult` out.

---

## Data flow diagram

```
[Camera @ 30 FPS] ──────────────────────┐
                                        │
                                        ▼  (every frame)
                          ┌──────────────────────────────┐
                          │  processFrame(frame)         │
                          │    - Stage 1 keypoints       │
                          │    - Update internal buffer  │
                          │    - Return live box state   │
                          └───────────┬──────────────────┘
                                      │
                          { state: 'no-hands' | 'hands-detected',
                            framesBuffered }
                                      │
                          ┌───────────▼──────────────────┐
                          │  Live bounding box (gray/orange)│
                          │  No rep decisions yet           │
                          └─────────────────────────────────┘

(at end of rep window, ~3s in)

[Frontend triggers] ────────────────────┐
                                        ▼
                          ┌──────────────────────────────┐
                          │  evaluateRep(                 │
                          │    drillType,                 │  ← current drill state
                          │    target                     │  ← current sign data
                          │  )                            │
                          │                               │
                          │    Uses CACHED keypoints from │
                          │    processFrame() loop.       │
                          │    Stage 2 / drill detector / │
                          │    OOD rejection /            │
                          │    confidence calibration.    │
                          └───────────┬──────────────────┘
                                      │
                          DetectionResult { state, confidence,
                                            oodScore?, parameter?,
                                            detail?, latencyMs,
                                            modelVersion }
                                      │
                          ┌───────────▼──────────────────┐
                          │  Frontend state machine       │
                          │  - Sets box color (green/orange/gray)│
                          │  - Advances rep or not         │
                          │  - Surfaces hint copy          │
                          └───────────┬──────────────────┘
                                      │
                                      ▼
                          [Mastery DB write]  ← via backend API
                                              (rep outcome only —
                                               no frames, no keypoints)
```

The hot path stays in-browser. No frames or keypoints cross the network. Only the **outcome** of a rep (pass/fail/skip + sign identifier) gets sent to the backend, and only for mastery-state updates.

---

## Open questions for the ML team

1. **Path A vs Path B for handshape/movement detectors** (per `competitive/comparison.md`):
   - **Path A**: deterministic feature rules over Stage 1 keypoints (faster to ship, less accurate)
   - **Path B**: separate small classifiers per parameter (slower to ship, more accurate)
   
   Which path are you taking? This decision blocks UI work on the hint specificity layer.

2. **Calibration**: are your confidence scores calibrated probabilities, or just softmax outputs? The frontend's threshold logic assumes the former. If they're not calibrated, we need either a calibration layer (temperature scaling) or different thresholds per drill type.

3. **Test learners**: who's giving us the held-out test set of ASL-1 learners for gate verification? This needs to be settled before v2 cutover, ideally before v2 training even finishes.

4. **Model bundle format**: ONNX + ONNX Runtime Web is the assumption per `training-plan.md`. If your final architecture deviates (e.g., TFLite, custom WASM), flag early so we adjust the integration shim.

5. **Stage 1 sharing**: if all three drill detectors share Stage 1 keypoint output, where does that computation live? Per-call inside each detector (wasteful) or once per frame and cached (faster, but requires module-level state)?

---

## Contact and review

When you're ready to integrate, open a PR against this repo with your module at `frontend/src/cv/evaluate.real.ts` plus test fixtures. Tag the frontend lead for review. Expected review focus: interface conformance, latency, fixture coverage.

Until then, keep training. The frontend will be ready when you are.
