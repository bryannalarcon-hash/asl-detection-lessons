# WebGPU in-browser inference port — plan

Goal: run the full Net 1→2→3→4 ASL pipeline **in the browser on the user's GPU**
via ONNX Runtime Web (WebGPU EP, WASM fallback), replacing the mock CV in the
React app. This is the `evaluate.real` deliverable from `docs/ml-handoff.md`
(Req 5 browser-first inference, Req 13 privacy/no-upload).

Today the only real inference is the **Python/PyTorch Streamlit demo** (CPU,
slow). The React app ships `evaluate.mock`. The port makes the *real* app run
the pipeline client-side at real-time.

INT8 quantization is **deferred** (redo once the 125/word Net 4 is final). The
port uses FP32 (or FP16) ONNX first; quantization is a later swap of the .onnx
assets, not a code change.

---

## Target architecture

```
frontend/src/cv/
  evaluate.real.ts     # public contract: init / processFrame / evaluateRep / reset / dispose
  ort/
    session.ts         # ORT Web session mgmt, backend pick (webgpu->wasm), warm-up
    models.ts          # model URLs + IO tensor specs (the EXPORT CONTRACT)
  pipeline/
    geom.ts            # letterbox, crop+rotate, soft-argmax, NMS, unproject (ports of the Python glue)
    stage1.ts          # Net1 (face/body) + Net2 (palm) + Net3 (2-pass hand) -> 49-kpt frame vector
    features.ts        # per-frame 343-dim feature (coords+visibility+lag deltas) + window_to_model_input
    stage2.ts          # Net4 forward -> softmax -> top-k
    verifier.ts        # TS port of SignVerifier (30-frame window, 0.8 vote, motion gate, hysteresis)
frontend/public/models/
  net1.onnx net2.onnx net3.onnx net4.onnx  manifest.json    # exported assets (gitignored if large)
tools/onnx_export/
  export_all.py        # PyTorch -> ONNX for all 4 nets + IO spec + parity dump (tracked)
  dump_reference.py    # fixed-input reference IO + full-pipeline output -> JSON fixtures (tracked)
frontend/tests/cv/
  *.parity.spec.ts     # ORT-Web output == Python reference fixtures, per net + e2e
```

Contract (from ml-handoff.md, canonical): `init(config) -> {modelVersion,
backend, warmupLatencyMs}`; `processFrame(frame) -> {state, framesBuffered}`
(<33ms); `evaluateRep(drillType, target) -> DetectionResult` (<200ms). The
verifier's continuous green/orange maps onto processFrame state + evaluateRep.

---

## The hard part

Not the model forwards (ORT runs those) — it's porting the **Python glue to TS
with numerical parity**: letterbox math, Net1 soft-argmax + index remap, Net2
anchor decode + NMS, Net3 expand-box + crop + rotate + **2-pass self-orient** +
unproject, the 343-dim feature vector (coords + visibility + lag deltas), the
window pad/subsample, and the SignVerifier vote/hysteresis. Every one of these
must match `src/stage1/*`, `src/stage2/extract_keypoints.py`,
`src/stage2/predict_clip.py`, `src/stage2/data/sign_dataset.py`,
`src/stage2/sign_verifier.py`. Parity tests against Python reference dumps are
non-negotiable.

---

## Workstreams (parallelizable; interfaces decouple them)

**A — ONNX export + IO contract** (`tools/onnx_export/`, unblocks everyone).
Export net1/2/3/4 to ONNX (opset 17), dynamic batch, validate each ONNX (ORT
CPU) matches PyTorch within 1e-3. Publish `models.ts` IO spec (names, shapes,
dtypes, pre/post expectations) — the seam all TS work codes against. Also dump
**reference fixtures** (`tools/onnx_export/dump_reference.py`): for fixed RNG
inputs, the IO of each net AND the full predict_clip pipeline output on 1-2
lesson clips, as JSON, for the parity tests. **Deliver the IO spec + fixtures
first; B/C can stub against the spec meanwhile.**

**B — Stage-1 keypoint pipeline TS** (`pipeline/geom.ts`, `pipeline/stage1.ts`).
Port letterbox, Net1 forward+soft-argmax+remap, Net2 decode+NMS, Net3
crop+rotate+2-pass+unproject. Output: a 49-keypoint frame vector identical to
`extract_keypoints.extract_one_clip`'s per-frame output. Depends on A's IO spec.

**C — Stage-2 classify + verifier TS** (`pipeline/features.ts`, `stage2.ts`,
`verifier.ts`). Port the 343-dim feature builder + window_to_model_input + Net4
forward + softmax/top-k + SignVerifier. Input: the keypoint buffer from B.
Depends on A (Net4 IO) — can build against the spec before B is done.

**D — ORT runtime + integration** (`ort/session.ts`, `evaluate.real.ts`, the
`evaluate.ts` swap). onnxruntime-web setup, WebGPU->WASM backend pick, model
load + warm-up, and wire B+C into init/processFrame/evaluateRep. Owns the
public contract + the React swap (behind a flag so mock stays default until
parity passes).

---

## Verification (dedicated agents, gate the merge)

**V1 — per-net parity:** for each net, feed the A-fixtures through ORT Web (node
harness) and assert output == PyTorch reference within tol (1e-3 fp32). Catches
export + pre/post-processing drift.

**V2 — e2e parity:** run a known lesson clip through the full TS pipeline
(node/ORT) and assert the top-3 glosses + the keypoint sequence match
`predict_clip` on the same clip (the exact thing the Python side produces).
Green only when e2e matches.

**V3 — contract + perf review:** evaluate.real conforms to the ml-handoff
interface; processFrame <33ms / evaluateRep <200ms measured in a real browser
(WebGPU) on the PoC numbers; the mock->real swap is flag-gated and reversible.

---

## Dependencies / sequencing

```
A (export + IO spec + fixtures)  ──►  B (stage1 TS) ──►┐
                                 ──►  C (stage2/verifier TS) ──►┤──► D (integrate) ──► V2/V3
A fixtures ─────────────────────────────────────────► V1 (per-net parity, as each net lands)
```
A is the critical path. B and C parallelize after A's spec. D integrates. V1
runs per-net as they land; V2/V3 gate the final merge.

## Risks
- ONNX export of soft-argmax / NMS / the 2-pass control flow may need op
  workarounds or doing that step in TS instead of in-graph. Prefer: export the
  pure conv forwards; do soft-argmax/NMS/crop/feature math in TS (easier parity).
- Numerical parity across fp32 reductions (browser vs torch) — tol 1e-3, not bit.
- 25MB bundle + latency are gated later by INT8 + Net1 shrink (separate items).

## Milestones
1. A: 4 ONNX + IO spec + fixtures, each net parity-validated (Python side).
2. B+C: stage1 + stage2/verifier TS pass V1 per-net parity.
3. D: evaluate.real wired; V2 e2e parity green on a lesson clip.
4. Browser: WebGPU perf meets budget (from the PoC); flag-flip mock->real.
5. (later) INT8 quant of the final 125/word models; re-run V1/V2.
