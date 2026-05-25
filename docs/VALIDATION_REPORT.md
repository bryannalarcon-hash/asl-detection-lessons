# Validation Report — From-Scratch 4-Net ASL Recognition Pipeline

Status: 2026-05-25. Deliverable #4 (accuracy targets, test conditions, known
limitations). All weights trained from scratch (Req 7 — no pretrained
backbones, no MediaPipe distillation). Numbers below are read from
`results/v3/*/metrics.jsonl`, `results/v3/*/eval_summary.json`, and the AP eval
in `scripts/eval_net2_ap.py`. Where a measured number is missing or in doubt it
is flagged.

## 1. Summary

| Net | Role | Metric | Value | Test set | Verdict |
|-----|------|--------|-------|----------|---------|
| Net 1 | Face/body keypoint regressor | PCK | ~0.72 | COCO-WholeBody val (held-out) | Acceptable; off param budget |
| Net 2 | Palm detector (deployed: `net2_v3_1`) | AP@0.5 | 0.20 | COCO-WholeBody val (held-out) | Weak; usable only with Net 3 2-pass self-orientation |
| Net 2-kpt | Palm detector w/ keypoint head (rejected variant) | AP@0.5 | 0.016–0.033 | COCO-WholeBody val (held-out) | Regressed — under-trained, not deployed |
| Net 3 | Hand landmark regressor | PCK@0.05 / @0.10 / @0.20 | 0.45 / 0.71 / 0.86 | FreiHAND val (held-out) | Best from-scratch result; trails MediaPipe (~0.8) |
| Net 4 | Sign classifier (~96-word PopSign) | top-1 / top-3 | PENDING | PopSign held-out | Training not complete |

## 2. Test conditions

**Held-out splits.**
- Net 1 / Net 2: COCO-WholeBody val, never seen in training. Net 2 GT boxes are
  derived on the fly from COCO-WholeBody hand keypoints via
  `palm_bbox_for_each_hand` — exactly the target the detector was trained to
  predict (`scripts/eval_net2_ap.py` docstring).
- Net 3: FreiHAND val — a 5% split of FreiHAND held out by fixed seed
  (`freihand_val_frac: 0.05`, `freihand_val_seed: 42` in
  `configs/stage1_v3_landmark_reg.yaml`). Training mix is FreiHAND 0.60 /
  InterHand-single 0.30 / RHD 0.10.
- Net 4: PopSign clips, held-out split (PENDING — see §3).

**Metric definitions.**
- **PCK@frac** (Percentage of Correct Keypoints): a predicted keypoint counts as
  correct if it lands within `frac × reference-size` of GT. Net 3 evaluates at
  fracs `[0.05, 0.10, 0.20]` (`eval.pck_threshold_fracs`, same config). Net 1
  reports a single `coco_val/pck_overall`.
- **AP@IoU0.5** (single-class hand): area under the precision-recall curve where
  a prediction matches GT at IoU >= 0.5. `eval_net2_ap.py` builds the PR curve
  from all predictions down to conf 0.05, and separately reports recall /
  precision / mean IoU at conf 0.5. Both 11-point and continuous AP are emitted.
- **top-k** (Net 4): the true class appears in the model's top-k predictions
  (`eval.topk: [1, 3]` in `configs/stage2_v4_classifier_popsign.yaml`).

**How eval is run.** Net 2 AP: `python3 scripts/eval_net2_ap.py --checkpoint
... --coco-ann coco_wholebody_val --coco-img train2017`. Net 1/Net 3 PCK is
logged per-epoch into `metrics.jsonl` against the val split (val_every: 1). The
combined `results/v3/eval_summary.json` is a separate post-hoc run over 2055
COCO samples.

## 3. Per-net detail

**Net 1 — face/body keypoint regressor (~0.72 PCK).** `net1_v3_1/metrics.jsonl`
holds at `coco_val/pck_overall ~0.72` (final epoch 0.718). Caveat reported
honestly: in that file `pck_hands` mirrors `pck_overall` and `pck_face` /
`pck_body` are logged as 0.0 — a sliced-eval artifact, not real zero accuracy.
The post-hoc `results/v3/eval_summary.json` (2055 samples) gives the true split:
`pck_face 0.78`, `pck_body 0.66`, `pck_overall 0.71`. Use those for face/body.

**Net 2 — palm detector (AP@0.5 = 0.20, deployed `net2_v3_1`).** Measured AP is
0.20 continuous (0.212 11-point), recall@conf0.5 ~0.09, precision ~0.65, mean
IoU ~0.65, max recall 0.49 (`results/v3/net2_v3_1/eval_summary.json`). This is
the checkpoint shipped in the pipeline. AP 0.20 is low: the detector finds hands
in some scenes but misses most at usable confidence (recall 0.09). The pipeline
compensates by feeding Net 2 + a Net 3 two-pass self-orientation step rather
than trusting Net 2 boxes alone.

**Net 2 regression story (do not deploy the kpt variant).** A newer keypoint-head
Net 2 (`results/v3/net2/`) was meant to fold landmark output into the detector.
It REGRESSED to AP 0.016–0.033 (`results/v3/eval_summary.json`:
`net2_palm_AP_iou50_continuous 0.022`, `11point 0.033`, max recall 0.195). Root
cause was under-training from a cost-trim: ~45 epochs with a 200k-samples/epoch
cap (only ~20 epochs are logged in its `metrics.jsonl`) versus `net2_v3_1`'s
70-epoch full-dataset run. The kpt variant was rejected and `net2_v3_1` retained.

**Net 3 — hand landmark regressor (PCK@0.05 = 0.45).** `net3/metrics.jsonl`
final-epoch val: `pck_05 0.450`, `pck_10 0.712`, `pck_20 0.861`. This is the
direct-(x,y) regression rewrite. The prior heatmap + soft-argmax net
(`net3_v2/metrics.jsonl`) topped out at `pck_05 0.322`. The rewrite is a
+0.13 absolute / ~40% relative gain at the tight 0.05 threshold, per the
diagnosis in `docs/handoffs/HANDOFF_MEDIAPIPE_GAP.md` (the U-Net decoder ate the
1.3M param budget and occluded joints had no heatmap peak to supervise).

**Net 4 — sign classifier (PENDING).** ~96-word PopSign vocabulary
(`configs/popsign_vocab.json`; num_classes derived from the sign list at train
time). Training is not complete; no held-out accuracy exists yet.

| Net 4 metric | Target | Achieved |
|--------------|--------|----------|
| top-1 (constrained, attempted target X) | per `ml-handoff.md`: accept/reject gate at confidence >= 0.85 | PENDING |
| top-1 (open-vocab, all signs) | report alongside constrained (PopSignAI credibility lesson) | PENDING |
| top-3 | — | PENDING |

To be filled on training completion. `ml-handoff.md` requires publishing BOTH
the constrained-target number and the open-vocabulary number, not just the
flattering constrained one.

## 4. Known limitations (candid)

1. **Net 2 detection is weak (AP 0.20).** Recall at usable confidence is ~0.09;
   it degrades on cluttered and full-body scenes. Hands are often missed, which
   directly starves the downstream crop.
2. **The under-trained kpt-Net 2 failure (AP 0.016).** Demonstrates the pipeline
   is sensitive to training budget cuts; the cheaper recipe was a net loss.
3. **Net 3 trails MediaPipe (~0.8 PCK).** At 0.45 PCK@0.05 our landmarks are
   markedly less precise than the production reference on fine fingertip
   localization.
4. **Cascade dependency.** Net 4 consumes Net 1→2→3 output. Stage-1 quality caps
   Stage-2 accuracy: weak Net 2 recall and Net 3 precision propagate, so Net 4's
   eventual number is conditioned on upstream quality, not measured in isolation.
5. **Net 4 domain narrowness.** PopSign clips are clean, front-facing,
   single-hand, isolated. The classifier may not generalize to varied signers,
   backgrounds, lighting, or two-handed/framing variation.
6. **No neutral / "no-sign" class.** Net 4 is an isolated-clip classifier, not a
   continuous recognizer. It always outputs a sign; it cannot natively say
   "nothing was signed."
7. **OOD-rejection gate NOT implemented.** `ml-handoff.md` requires an
   out-of-distribution rejection rate >= 90% (line 224: a wrong/absent sign must
   return `low-confidence`/`no-hands`, never `target-met`). No OOD scorer exists
   or is measured yet. This is the single biggest unmet requirement.
8. **Model size over budget.** Net 1 is 13.4M params, ~7x MediaPipe's whole hand
   pipeline (`HANDOFF_MEDIAPIPE_GAP.md` item 9). The bundle budget is <= 25MB
   (`ml-handoff.md` line 200). INT8 quantization plus a backbone shrink are
   required to fit; not yet done. The 4-seed ensemble does not fit and a
   single-seed distilled student is preferred.
9. **End-to-end not validated.** The full Net 1→2→3→4 cascade has not been run
   and scored end-to-end on real input; per-net numbers do not guarantee
   composed accuracy.

## 5. Accuracy targets vs achieved

| Net / requirement | Target | Achieved | Met? |
|-------------------|--------|----------|------|
| Net 1 keypoint PCK | usable face/body localization | ~0.72 overall (face 0.78, body 0.66) | Partial — works, off param budget |
| Net 2 palm AP@0.5 | reliable hand detection | 0.20 (deployed); 0.016 (rejected kpt) | No — weak recall |
| Net 3 hand PCK@0.05 | approach MediaPipe (~0.8) | 0.45 (was 0.32) | No — improved, still trails |
| Net 4 sign accuracy | confidence-gate accept/reject (>= 0.85) | PENDING | Pending |
| OOD rejection rate | >= 90% | Not implemented / not measured | No |
| Model bundle size | <= 25MB | Net 1 alone 13.4M params (off budget) | No — needs INT8 + shrink |
| End-to-end accuracy | composed cascade validated | Not run end-to-end | No |
