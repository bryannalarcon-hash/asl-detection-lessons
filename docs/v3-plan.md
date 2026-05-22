# Stage 1 v3 — Plan

Synthesized from a 13-agent ruflo swarm (mesh, swarm-1779405375250-xnmqfe). Goal: lift hand PCK from v2's ~0.30 to ≥0.50 within a **$30 compute budget and ≤1 day (8–12 hrs) engineering effort**, while staying compliant with Req 7 (no pretrained weights anywhere).

## Summary of swarm consensus

| Lever | Verdict | Expected PCK lift | Cost |
|---|---|---|---|
| **Two-stage palm detector → cropped landmark** | **Strongest single lever** (5/13 agents) — fixes "hand is tiny in a full frame" failure mode. Effective hand resolution jumps 4–6×. | +0.20 to +0.35 hand PCK | ~$8 + 8–12 hr eng |
| Higher-resolution heatmaps (stride 2) + DARK decoding | Cheapest meaningful arch tweak | +0.06 to +0.10 | ~$3 + 2–3 hr |
| Larger input (384×384) | Cheap, monotonic | +0.05 to +0.10 | ~$3 + 1 hr |
| Add HanCo dataset (~860K, MoCap labels, free) | Biggest data lever | +0.06 to +0.09 | ~$5 + 4 hr |
| Add InterHand2.6M (5fps, ~50 GB) | Closes two-hand+occlusion gap | +0.10 to +0.14 | ~$8 + 8 hr |
| **Adaptive Wing Loss** + soft-argmax L1 aux | Best loss swap, fingertip-friendly | +0.03 to +0.05 | $0 + 2 hr |
| EMA (0.9998) + linear warmup + grad clip | Free safety + lift | +0.02 to +0.04 | $0 + 1 hr |
| Cross-dataset compositing (FreiHAND hands on COCO backgrounds) | Single biggest aug win | +0.025 to +0.04 | $0 + 3 hr |
| Synthetic face-occlusion augmentation (ASL-specific) | ASL-critical | +0.02 to +0.035 | $0 + 2 hr |
| Self-supervised pretraining (MAE) | **Skip** — diminishing returns on 330K labeled, expensive | +0.01 to +0.03 only | $10–24 hr |

## Critical Req-7 watch

One swarm agent recommended **`timm.create_model("hrnet_w32", pretrained=True)`**. That **violates Req 7** — `pretrained=True` loads ImageNet weights. Any HRNet-derived path in v3 MUST be `pretrained=False`. Trade-off: from-scratch HRNet on 330K images is borderline data-starved and likely underperforms by ~0.05 PCK vs ImageNet-pretrained variant. So HRNet is dominated by from-scratch SimpleBaseline + better head — keep our v2 backbone family.

## Disagreements between agents

- **Loss function**: AdaptiveWing (5 agents) vs SimCC (2 agents). AdaptiveWing wins on minimal code change; SimCC would require rewriting the head — defer to v4.
- **Two-stage architecture**: most agents say it's the single biggest lever and worth the 8–12 hr engineering. One agent (the time-boxed planner) says skip for 1-day budget. **Resolution: two-stage is *the* feature; cut other novelties to fit it in.**
- **Self-collected sign-context data**: range from "highest leverage per dollar" (+8–12% on contact poses) to "skip, fits in v4." Resolution: 50–100 self-recorded frames (1 hr) under your actual webcam adds eval-set diversity for ~free; don't try to use for training.
- **Aggressive augmentation**: agents disagree on Mixup/CutMix (hurts keypoints — skip), RandAugment (marginal — skip), motion blur (re-add — yes), face-occlusion (yes), cross-dataset compositing (yes).

## Final v3 plan (the "winning portfolio")

Goal: clear PCK 0.50 on hands by end of day, with two distinct deliverables shipped.

**Architecture switch** — **two-stage from-scratch**:
- **Stage A (palm detector)**: tiny MobileNet-style backbone (~460K params, 192×192 input) → SSD-style anchors → palm bbox per hand. Trained from scratch on bboxes *derived* from existing keypoints (no new labels needed).
- **Stage B (cropped hand landmark)**: deeper MobileNet-style (~1.8M params, 224×224 hand crop, output stride 4 → 56×56 heatmap, 21 kpts). Run twice per frame (once per hand crop). Mirror left-hand crops horizontally.
- **Face/body anchors**: keep our v2 single-stage net OR add a tiny 7-kpt regression head off the detector's P3 feature.

**Data**:
- COCO-WholeBody (have) + FreiHAND (have) + **HanCo** (download, free, ~16 GB MoCap-labeled). Skip InterHand2.6M for the 1-day budget — too big to download + integrate in scope.

**Loss**:
- AdaptiveWing on heatmaps (primary) + soft-argmax L1 (auxiliary, weight 0.1, ramp on after epoch 5) + per-group weighting (hands=2.0, face=1.0, body=1.5) + sigma annealing 4.0 → 1.5.

**Augmentation** (Stage B only — Stage A uses standard SSD aug):
- ShiftScaleRotate ±30° / ±25% scale / ±8% shift
- HorizontalFlip (keypoint-index aware)
- HandOnCOCOComposite (paste FreiHAND hand on COCO background, p=0.3)
- SyntheticFaceOcclusion (ellipse patch near face region, p=0.25)
- ColorJitter + SkinToneShift in LAB space (±15)
- MotionBlur / GaussianBlur / GaussNoise OneOf (re-added vs v2)
- ImageCompression (50–95 quality, p=0.3)
- Coarse dropout (3 holes, ≤24×24, p=0.25)

**Training recipe**:
- AdamW, peak LR 5e-4, 3-epoch linear warmup → cosine to 1e-5
- Batch 128 (Stage B), batch 256 (Stage A)
- Grad clip 1.0, fp16 mixed precision (or bf16 on Blackwell)
- EMA decay 0.9998
- 60 epochs (Stage A), 80 epochs (Stage B) — early-stop patience 20
- Per-source loss weighting (sqrt(1/size))

**Evaluation suite**:
- PCK@0.05 / @0.1 / @0.2 + AUC on COCO val + FreiHAND val (scene split) + HanCo val
- Per-finger breakdown (thumb / index / middle / ring / pinky / wrist / fingertips)
- Latency benchmark (separate from accuracy)
- **NEW**: 50-frame self-recorded calibration set under your actual webcam — never train on, eval at every milestone

## Compute & GPU choice

Use the same approach as v2:
- Filter for **RTX 5090, US-located, ≥12 effective CPU cores, ≥1.5 Gbps net, ≥98% reliability**
- At ~$1.00–1.30/hr interruptible
- Expect ~9 GPU-hours total (Stage A ~3h, Stage B ~5h, eval+iteration ~1h)
- **Projected compute spend: $9–12**

GPU choice principle (from the swarm): once we're compute-bound (40M+ params), 5090 is dominant. We're not at 40M params, so 4090 is also fine. **Pick whichever has 12+ effective CPU cores at the cheapest rate when launching.**

## Hour-by-hour timeline

| Hour | Work | Cost so far |
|---|---|---|
| 0–1 | Write `palm_detector.py`, `landmark_net.py`, `anchors.py`, `palm_boxes.py` from skeletons | $0 |
| 1–2 | Write `hanco.py` loader; write loss `losses_v3.py` with AdaptiveWing + soft-argmax + per-group weights | $0 |
| 2–3 | Augmentation file `transforms_v3.py` with face-occlusion + skin-tone + compositing | $0 |
| 3 | **Spin up 5090** on vast (US); push code; download HanCo (~5 min on 7 Gbps); preprocess cache | $0.05 |
| 3–4 | Train Stage A (palm detector, 60 epochs, batch 256) | $1.50 |
| 4 | Eval Stage A bbox AP; gate: must be ≥0.85 AP@IoU=0.5 to proceed | $1.60 |
| 4–8 | Train Stage B (landmark, 80 epochs, batch 128, fp16+EMA) | $5.50 |
| 8 | Eval both stages end-to-end on COCO val + FreiHAND val + HanCo val + calibration set | $5.80 |
| 8–9 | Pull artifacts, destroy instance, write delta summary | $6.00 |

**Buffer**: $24 of $30 reserved for: one full retry with adjusted hyperparams, or extending Stage B to 120 epochs.

## Stop-and-pivot gates

| Gate | At hour | Trigger | Action |
|---|---|---|---|
| **G1** | 3 | smoke run loss matches v2's step-0 within 10% | proceed; otherwise debug + fix BEFORE renting GPU |
| **G2** | 4 | Stage A palm AP@IoU=0.5 ≥ 0.80 | proceed; if <0.70, the detector is broken — abort and ship v2 |
| **G3** | 6 (mid Stage B) | val PCK ≥ 0.35 by epoch 30 | proceed; if still 0.30–0.32, the new pipeline is no better — kill at G3 |
| **G4** | 8 | final hand PCK ≥ 0.40 | ship v3; if 0.35–0.40, ship v3 as variant; if <0.35, ship v2 + postmortem |

## Hard kill switch

$25 spent OR 14 wall-clock hours, whichever first. Reserve $5 for re-eval + packaging.

## What NOT to do in v3 (explicit)

Documenting these so we don't relitigate:

- ❌ MAE/SimCLR/DINO self-supervised pretraining — diminishing returns on 330K labeled, expensive
- ❌ HRNet with ImageNet pretrained weights — violates Req 7
- ❌ ResNet-50 from scratch — consistently underperforms smaller nets without ImageNet pretrain
- ❌ Mixup/CutMix on keypoint targets — label interpolation breaks coordinates
- ❌ SGD+momentum — needs full retune, AdamW wins on heatmap regression
- ❌ Wider channels (64,128,256,512,768) alone — capacity isn't the bottleneck, resolution is
- ❌ InterHand2.6M for this round — 50 GB download + integration too big for 1-day budget; consider for v4
- ❌ Synthetic-generation-via-Stable-Diffusion sign-context data — anatomy quality too low

## Expected outcomes

- **Conservative**: PCK 0.42–0.48 hands. Two-stage gives the biggest single jump; HanCo + augmentation polish pushes a bit further.
- **Realistic**: PCK 0.50–0.58 hands. The full stack stacks well; per-finger breakdown will show wrist > MCPs > tips by ~0.10.
- **Optimistic**: PCK 0.55–0.65 hands. Requires everything to compound positively and no debug detours.

In all cases, we'll know within 6 hours whether v3 is meaningfully better than v2.

## Next iteration (v4) — out of scope for this round

For after v3 ships, in rough order of impact:
1. SimCC head architecture (replaces heatmap head with 1D coord classification)
2. InterHand2.6M integration (+0.10–0.14 PCK)
3. ImageNet self-supervised MAE pretraining on our 330K (only if we have a week)
4. Multi-scale test-time augmentation
5. Real-time temporal smoothing (One-Euro filter at inference)

## Open questions for the user

Before launching v3:

1. **Is the 2-stage architectural complexity acceptable?** It doubles model count and complicates browser deployment but is the biggest accuracy lever.
2. **Self-collected calibration frames**: do you want to record ~50 frames now (1 hour) as a held-out test, or use COCO/FreiHAND val alone?
3. **Budget**: $30 spending cap holds, or push to $50 if v3 looks promising at gate G3?
