# Swarm findings — fix all 4 nets

Raw outputs preserved here in case session crashes. Full transcripts at
`/tmp/claude-1000/.../tasks/*.output`. Five of seven returned; final synthesis
pending the last two agents.

## Convergent themes (across 5 returned agents)

1. **Net 4 top-3 0.85 is fantasy under Req 7.** Both net4-improver and
   architecture-reviewer independently estimate 0.45-0.60 as the honest ceiling
   even with PopSign + self-collection + ProtoNet.
2. **The 4-net cascade is the design problem.** Architecture-reviewer recommends
   collapsing Net 1 + Net 2 + Net 3 into a single multi-task "PoseNet" (49 kpts +
   visibility, one backbone, masked losses). Cascading error from Net 2 max-recall
   0.49 → Net 3 PCK 0.353 → Net 4 chance-level is fatal as currently composed.
3. **HOyso is wrong for 17 samples/class.** Net 4 should switch to **ProtoNet**
   (Snell 2017) on per-frame embeddings — built for few-shot, 600:1 overparam-
   eterization on current arch is killing val_top1.
4. **PopSign v1.0 raw video is the highest-leverage data add.** CC BY 4.0,
   covers ~45-55 of our 90 glosses at ~700 clips/class. Req 7 compliant because
   we'd run OUR Stage 1 on raw frames.
5. **Per-net targets are inconsistent in reachability:**
   - Net 1 PCK > 0.85: reachable (HRNet from scratch + Halpe + CrowdPose, ~65%)
   - Net 2 AP@0.5 > 0.40: borderline (EgoHands + Mosaic + 320², ~55-65%)
   - Net 3 PCK@0.05 > 0.80: not reachable under Req 7. Realistic ceiling 0.55-0.70
     at PCK@0.05; PCK@0.10 (>0.85) is the metric that matters for Net 4 anyway.
   - Net 4 top-3 > 0.85: not reachable under Req 7. Realistic ceiling 0.45-0.60.

## Top recommendations per agent

### net1-improver
1. Fix `compute_pck` K=7 sliced eval bug FIRST (30 LOC, $0).
2. Expand data: COCO-WholeBody full + Halpe + CrowdPose. +0.06-0.09.
3. HRNet-W18 from scratch + OHKM + DARK + aug pack. +0.06-0.09 on top.
- **Expected:** PCK 0.73 → 0.82-0.91. Cost ~$60-70.
- **Probability of >0.85:** ~65%.

### net2-improver
1. Wire EgoHands back in + self-collected webcam frames + CrowdPose + drop synthetic
   to 5%. 0.20 → ~0.30, $10.
2. Mosaic-4 + 90° rotation + perspective + lower neg_iou + GIoU box. ~0.30 → ~0.36.
3. 256² → 320² + Stage C EgoHands-heavy + hard-neg mining + multi-scale eval TTA.
   ~0.36 → 0.38-0.44. +$15.
- **Expected:** AP@0.5 0.38-0.44, max recall 0.70-0.78. Cost ~$25.
- **Probability of >0.40:** ~55-65% (drops to 40% without self-collection).

### net3-improver
1. Augmentation overhaul (rot ±180°, scale 0.30, motion blur, erase, brightness).
   +0.08-0.15.
2. Fix RHD wiring + add HO-3D + OneHand10K + CMU Panoptic. +0.06-0.10.
3. U-Net skip connections + sharpen heatmap sigma + fingertip-weighted loss.
   +0.05-0.08.
- **Expected:** PCK@0.05 0.353 → 0.55-0.70. **Recommend redefining target to
  PCK@0.05 ≥ 0.60 AND PCK@0.10 ≥ 0.85** (Net 4 cares more about topology than
  sub-pixel precision).
- **Probability of >0.80 PCK@0.05:** Not reachable. Honest ceiling 0.70 under
  Req 7 at the current model scale.

### net4-improver (the most consequential one)
Reframe as **few-shot problem**:
- Drop HOyso (too big for 17 samples/class).
- ProtoNet + episodic training + per-frame embedding encoder.
- Full augmentation stack (time-warp, mirror+side-swap, per-signer z-score,
  random kpt masking, mixup) = +0.15-0.20 standalone.
- 5-fold signer-disjoint CV; combine train+val for final.
- **PopSign v1.0 raw + 3-signer self-collection.**
- **Three honest ceilings:**
  - Req 7 strict + current data: top-3 0.20-0.35
  - Req 7 strict + PopSign + self-collect: top-3 0.50-0.65
  - Req 7 strict, signer-overlap allowed: top-3 0.75-0.88
  - Req 7 relaxed (MediaPipe Kaggle for pretrain): top-3 0.70-0.85

### architecture-reviewer (cross-cutting)
- Collapse Net 1+2+3 → "PoseNet" (MobileNetV3-small, 3M params, multi-task heads).
- Switch Net 4 from HOyso → ProtoNet.
- Self-supervised contrastive pretrain on unlabeled clips (SimCLR over (T,49,3)
  keypoint sequences). Flag to instructor first — likely Req 7 compliant since
  we pretrain on our own data.
- Deploy: ONNX + int8 quantization + WebGPU, T=16 frame subsample. 13s → <500ms.
- **2-week bet:** PoseNet + contrastive pretrain + ProtoNet → top-3 **0.45-0.60.**
  Cost ~$60.
- Recommends setting **public target to top-3 0.50** instead of 0.85; honest
  framing wins assignments, fake numbers get caught.

## data-strategy-reviewer (returned)

Same convergent answer: **PopSign v1.0 selective pull is the single highest-
leverage move**. CC BY 4.0, commercial-safe, 47 deaf signers.

Sharpest additions:
- Storage estimate corrected: **220-250 GB** for 50-gloss selective pull
  (not 50-100 GB). 4.4 GB per gloss avg.
- **Test split is upside-down**: current 1504/379/1270 (48/12/40) wastes data.
  Resize to **200 val / 200 test / 2753 train** keeping signer-disjoint —
  recovers ~1250 train clips for free before PopSign arrives.
- **Self-collection at 5 signers is a trap.** 20-signer round is the right
  number, but recruiting blocks it.
- **Net 3 0.80 target is unreachable under Req 7** — realistic ceiling 0.65-
  0.72. Net 3 target should be relaxed OR Req 7 partially relaxed for hand
  kpts only.
- **Net 2 0.40 target is reachable** with balanced HaGRID-down sampling alone
  (70% probability).
- Honest commercial-safe universe: **ASL Citizen + PopSign**. That's it. Everything
  else has a license problem.

Per-net target probabilities post-refresh:
- Net 1 > 0.85: **55%**
- Net 2 > 0.40: **70%**
- Net 3 > 0.80: **<10%** under Req 7 strict
- Net 4 top-3 > 0.85: **15%** PopSign-only, **45%** PopSign + 20-signer self-collect

## retrain-plan-reviewer (devil's advocate, returned)

Sharpest finding: **the standard "fix everything for $50" playbook fails this
project** because Net 4 is data-bound, not training-bound. 17 signer-disjoint
clips/class is below any published threshold for 90-class sign recognition.
No training-side intervention closes a 14× gap.

**Single strongest intervention:** metric audit first ($0, 3 hrs). Then PopSign
v1.0 raw video selective download for Net 4 (~$15 retrain).

Probability metric audit "saves" each net:
- Net 3: ~60% (PCK@0.10 likely much better than @0.05)
- Net 4: ~5% (0.06 top-3 is genuinely chance-level, audit confirms)
- Net 1: ~30% (target recalibration for K=7 sliced model)
- Net 2: ~10%

Gating tree the user must answer before any more spend:
1. **Run metric audit ($0).**
2. **Branch on Req 7:**
   - hard constraint → PopSign + Net 4 retrain (~$15), expect 0.25-0.35 top-3
   - negotiable → Kaggle ISLR integration (~$20), expect 0.55-0.70 top-3
   - demo-first → $0 retrain, invest in hint system + UX

Five questions to ask user before spending another dollar:
1. **Is Req 7 hard or strong preference?** Single highest-leverage question.
2. **What's the actual deliverable?** Pilot UX, research artifact, or assignment?
3. **OK with "45 of 90 signs at 0.35 top-3, hint system covers the rest"?**
4. **Timeline?** $50 over 2 weeks vs 2 months changes self-collection calculus.
5. **Will evaluators see metrics or just the demo?**

"Self-collection is a trap" — 5 signers × 20 × 90 = 9000 clips × ~2 min each
= 300 hours of human labor. Not feasible on a college deadline.

## Unresolved questions (for user)
1. Is **self-supervised contrastive pretrain on our own unlabeled video** within
   Req 7? (Likely yes, but needs explicit ruling.)
2. Is **signer-disjoint** required by the assignment, or is **signer-overlap**
   ("the app learns you") acceptable? (Massive impact: 0.50 vs 0.85.)
3. Is the **0.85 top-3 target negotiable** based on the honest ceiling, or
   non-negotiable per assignment rubric?
4. Are we willing to **collapse the 4-net design into 2 nets (PoseNet + Net 4)**?
   This is the biggest architectural recommendation.
