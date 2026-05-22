# ASL Pilot — Training Plan (Stages 1 & 2)

End-to-end ML plan for the controlled-pilot ASL learner. Two stages, both trained from scratch in compliance with Req 7 / Req 15.

- **Stage 1**: our own MediaPipe replacement — whole-body keypoint detector.
- **Stage 2**: hoyso48's hybrid 1D CNN + Transformer classifier (see [`hoyso-architecture.md`](./hoyso-architecture.md)) running on top of Stage 1's keypoints.

See [`hoyso-architecture.md`](./hoyso-architecture.md) for the Stage 2 architecture in detail; this doc focuses on what to train, where, and how to spend money efficiently.

---

## GPU selection principle ("pennies for hours")

Use this anywhere you provision compute. It's the durable rule; specific GPU models will change.

### Observation

For a single ~1M-step training run, **the absolute cost difference between the cheapest and fastest reasonable GPU is usually well under $2, but the wall-clock difference is several hours.**

Empirical example (live vast.ai data, May 2026):

| GPU | $/hr | Training time | **Total cost** |
|---|---|---|---|
| RTX 3090 | $0.18 | ~16 hr | ~$3.10 |
| RTX 5090 | $1.34 | ~3.6 hr | ~$4.93 |
| H100 SXM | $2.65 | ~2.1 hr | ~$5.64 |
| B200 | $3.91 | ~1.4 hr | ~$5.52 |

Spread in absolute dollars: $2.54. Spread in wall-clock: **14.6 hours**.

Paying for speed costs cents per hour saved. Time is the binding constraint, not money.

### Selection rule (run this each time you provision)

1. Query vast.ai for current single-GPU offers with filters: `verified=true`, `rentable=true`, `reliability2 > 0.97`, `inet_down > 500` Mbps.
2. For each GPU type, compute estimated training time using DLperf as throughput proxy: `steps_per_sec ≈ DLperf × 0.39` (calibrated against A100 baseline).
3. Compute `total_cost = (smoke_steps + training_steps) / steps_per_sec / 3600 × $/hr`.
4. **Drop dominated options** — any GPU that is both more expensive AND slower than another option.
5. From the remaining options, pick the one that satisfies your wall-clock budget at the lowest cost. For Stage 1, target wall-clock ≤ 4 hours (fits in a single focused work session).
6. If multiple options satisfy the budget within $2 of each other, **pick the faster one**.

### Stage-specific budgets

| Stage | Wall-clock budget | Cost ceiling | Notes |
|---|---|---|---|
| **Stage 1** | ≤ 4 hr training | ~$6 | Fits in one sitting. B200/H100/5090 all qualify; pick whichever's available. |
| **Stage 2** | n/a (model is tiny) | ~$5 | Any GPU works; optimize for absolute cheapest perf/$. Often the same 4090 or 3090 still spinning. |

### What NOT to pick

- **A100 PCIE / A100 SXM4**: typically dominated. 80 GB VRAM is wasted on our small models, and perf/$ trails the 5090.
- **H100 NVL**: pricier than H100 SXM, similar speed, no advantage for our workload.
- **RTX 5080**: only 16 GB VRAM; risks OOM on 384×384 input at batch 32. Skip.
- **L4, L40**: pose estimation isn't their strength; slow per dollar.

### Live query implementation

```python
import json, urllib.parse, urllib.request, os

api = os.environ["VAST_API"]

def best_offers(min_reliability=0.97, min_inet=500):
    candidates = ["B200", "H100 SXM", "RTX 5090", "RTX 4090", "H200"]
    results = []
    for gpu in candidates:
        q = {
            "verified": {"eq": True}, "rentable": {"eq": True},
            "gpu_name": {"eq": gpu}, "num_gpus": {"eq": 1},
            "reliability2": {"gt": min_reliability},
            "inet_down": {"gt": min_inet},
            "order": [["dph_total", "asc"]], "limit": 1,
        }
        url = "https://console.vast.ai/api/v0/bundles/?q=" + urllib.parse.quote(json.dumps(q))
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api}"})
        try:
            with urllib.request.urlopen(req) as r:
                data = json.load(r)
            if data.get("offers"):
                o = data["offers"][0]
                results.append({
                    "gpu": gpu, "price": o["dph_total"],
                    "dlperf": o.get("dlperf", 0),
                    "vram_gb": o.get("gpu_ram", 0) / 1024,
                })
        except Exception:
            pass
    return results

def stage1_cost(offer, total_steps=1_030_000):
    steps_per_sec = offer["dlperf"] * 0.39
    hours = total_steps / steps_per_sec / 3600
    return {"hours": hours, "cost": hours * offer["price"]}
```

Run this immediately before launching. Pick the row that gives the best wall-clock under your budget.

---

## Stage 1 — Whole-body keypoint detector

### Scope

A from-scratch CNN that ingests a 384×384 RGB frame and predicts ~35 keypoints: 21 per hand (42), face anchors (nose, eyes, lips, chin), shoulders/torso. Per-frame, stateless, deployed in-browser.

### Architecture

```
RGB frame 384×384×3
  → 5-stage CNN (HRNet-style or simpler ResNet from scratch, ~10M params)
  → heatmap head at 96×96 × 35 keypoints
  → soft-argmax → (x, y) per keypoint
  → rescale to original frame coordinates
  → (inference only) One-Euro filter to suppress jitter
```

No pretrained weights anywhere. AdamW initialization (random); every parameter learned on labeled images during training.

### Datasets

| Dataset | Size | Images | Labels | License | Role |
|---|---|---|---|---|---|
| **COCO-WholeBody** | ~20 GB | ~200K | 133 kpts (body+face+hands+feet), human-annotated | CC BY 4.0 | Foundation; scene/lighting variety |
| **FreiHAND** | ~6–7 GB | ~130K | 21 hand kpts, multi-view + MoCap | Research/educational | Hand precision boost |

**Total ~26 GB, ~330K labeled images.** Both publicly hosted with direct download links (cocodataset.org, lmb.informatik.uni-freiburg.de). Both Req-7 clean — labels are human/MoCap, not model-generated.

Add a third dataset only if the Stage 1 gate fails (next candidate: HanCo).

### Training recipe (canonical, no sweep)

| Component | Setting |
|---|---|
| Optimizer | AdamW |
| Learning rate | 1e-3 → 5e-4 cosine decay, no warmup |
| Batch size | 32 |
| Epochs | 210 nominal; early-stop on val PCK plateau (patience ~30 epochs) |
| Precision | fp16 mixed |
| Augmentation | random crop, scale, rotate, color jitter, horizontal flip; **also sample frames from our own Stage 2 video clips** to close the deployment domain gap |
| Loss | MSE on heatmaps (per-keypoint), optionally + coordinate-regression auxiliary loss |
| Validation | 80/10/10 split; val PCK@0.05 every epoch |

This recipe is well-established across HRNet, MMPose, ViTPose, and MediaPipe variants. We copy it; we do not sweep.

### Run plan

| Step | Purpose | Time on a top-tier GPU (5090 / H100 / B200) |
|---|---|---|
| **Smoke** | 1–2 epochs; verify loss decreases, no NaN, no crashes | 5–15 min |
| **Training** | Full 210-epoch schedule with cosine decay; typically plateaus at epoch 150–180 | 1.4–4 hr |

If the training run misses the Stage 1 gate, add one **adjustment run** (typically just LR or augmentation strength). One adjustment is the budget cap — if a second is needed, something deeper is wrong.

### Stage 1 gate

All four must pass:

1. **PCK@0.05 ≥ 0.85** on hands, **≥ 0.90** on face/body (held-out COCO-WholeBody test split).
2. **Visually stable** on Stage 0 calibration clips — no landmark swaps between left/right hand, no high-frequency jitter after One-Euro smoothing.
3. **≥ 30 FPS in-browser** via ONNX Runtime Web (WebGPU backend) on a typical college laptop. Acceptable hardware ladder:
   - M-series Mac: 30–60 FPS expected
   - Recent Windows laptop with dGPU: 60+ FPS expected
   - Integrated graphics: 15–30 FPS; may require dropping to 256×256 input
4. **Side-panel landmark visualization** working end-to-end (debug tool that doubles as the camera setup-check UI).

If any fails: iterate Stage 1. Hard cap: 3 weeks and $50 total before falling back to Tier 1 (RGB-only classifier, weaker hints).

### Stage 1 cost

Computed with the live selection rule above. Representative numbers:

```
On B200 (if available):    ~$5.50 total (1.4 hr training)
On H100 SXM:               ~$5.60 total (2.1 hr training)
On RTX 5090:               ~$5.00 total (3.6 hr training)
On RTX 4090 (fallback):    ~$3.00 total (~9 hr training, overnight)
```

Add ~$3 if one adjustment run is needed. **Realistic ceiling: $10.**

### Storage during Stage 1

While the instance is running, disk is bundled into the hourly rate. Per-hour storage cost for our 30 GB allocation:

```
30 GB × $0.20/GB/month ÷ (30 × 24 hr) ≈ $0.0083/hr
```

For a 5-hour session: **~$0.04**. Effectively free.

Do **not** keep the instance stopped (with disk allocated) between sessions unless necessary. Plan Stage 1 as one continuous session: spin up → download datasets (3–5 min) → smoke → train → save model locally → destroy instance.

If the work spans multiple days, host disk costs are ~$0.20/day for our allocation. Still trivial unless extended for weeks.

---

## Stage 2 — Sign classifier (hoyso architecture)

### Scope

Take Stage 1's per-frame keypoints as input, predict one of 75–100 ASL vocabulary labels with confidence. See [`hoyso-architecture.md`](./hoyso-architecture.md) for the full architecture detail.

### Architecture (unchanged from hoyso)

```
T=64 frames × ~80 features (per-frame keypoints + lag-1 + lag-2 motion deltas)
  → Masking + stem (Dense 192 + BatchNorm)
  → [Conv1DBlock ×3 → TransformerBlock] ×2
  → top conv → GAP → LateDropout(0.8) → Dense(NUM_CLASSES)
```

~1.85M parameters. We adopt the entire architecture and training recipe; only the input source changes (our Stage 1 keypoints instead of MediaPipe's).

### Datasets

| Dataset | Size | Pull? | Notes |
|---|---|---|---|
| **ASL Citizen** | ~84K clips, 2731 signs, 52 signers | **YES** | Newest, largest, most signer diversity. Filter to our 75–100 vocab → ~8–15K clips. Microsoft Research, requires access request. |
| **Our own collected** | Target 3–5K clips | **YES, required** | Closes the gap to controlled-framing distribution. Necessary for fairness across skin tones, lighting, signer body types. |
| WLASL | ~21K clips | Fallback if ASL Citizen access denied | Video URLs (many dead) |
| MS-ASL | ~25K clips | Skip; superseded by ASL Citizen | |

**Realistic combined corpus: ~12–18K clips after filtering, ~120–250 per class.** Hoyso trained on ~375 clips per class for ~250 classes and got 0.80 CV. Our task is easier (fewer classes, controlled framing), so this range should reach ≥ 0.80.

### Important: we don't use any landmark labels these datasets may ship with

We use only the **video frames** and **sign labels**. We re-extract keypoints with our Stage 1 detector. This keeps the entire pipeline trained by us, with no external landmark dependency.

### Training recipe (canonical hoyso, no sweep)

| Component | Setting |
|---|---|
| Optimizer | RAdam + Lookahead |
| Learning rate | 4e-3 cosine decay, no warmup |
| Batch size | 64 effective |
| Epochs | 400 |
| Loss | CCE with label smoothing 0.1 |
| Regularization | DropPath (p=0.2), LateDropout (p=0.8, starts at epoch 15), AWP (λ=0.2, starts at epoch 15) |
| Sequence length | max_len=64, variable, masked |
| Augmentation | Random resample 0.5×–1.5×, random temporal masking, horizontal flip, random affine, random cutout |
| Validation | Signer-stratified k-fold (no signer leakage) |
| Ensemble | 4 seeds, probability average |

The only thing we might tune: `LateDropout`'s `start_step` because our dataset is smaller than hoyso's. One-shot adjustment, not a sweep.

### Stage 2 cost

The classifier itself trains in minutes. The expensive part is **extracting keypoints from the ~15K video clips** with our Stage 1 detector.

| Step | Approximate time on 5090 | Cost |
|---|---|---|
| Stage 1 detector on ~900K frames sampled from clips | ~2–4 hr | ~$3–5 |
| Stage 2 training, 1 seed with AWP | ~45 min | ~$1 |
| Stage 2 training, 4-seed ensemble with AWP | ~3 hr | ~$4 |
| Storage during the session (~30 GB × 5 hr) | included | ~$0.05 |

**Total Stage 2 cost: ~$5–8.**

This is small because the model is tiny and trains fast.

### Stage 2 gate

All three must pass:

1. **≥ 0.80 top-1** on held-out signer split (no signer overlap with training).
2. **≥ 0.90 top-3** on same split.
3. **Confidence threshold calibrated** so that ≥ 0.95 precision at the chosen pass threshold (per Req 9 — "must avoid marking uncertain predictions as correct"). Tune by examining ROC curve on validation set.
4. **Runs in browser at < 50 ms inference latency** on a rolling 64-frame window.

---

## End-to-end totals

| Item | Stage 1 | Stage 2 | Total |
|---|---|---|---|
| GPU compute (single try) | ~$3–6 | ~$5–8 | **~$8–14** |
| Adjustment runs / retries | ~$3 | ~$3 | **~$6** |
| Storage during sessions | ~$0.05 | ~$0.05 | **~$0.10** |
| **Realistic ceiling** | | | **~$20–30** |

Wall-clock from "dataset downloaded" to "both gates passed":
- Optimistic: 1–2 weeks if both first runs succeed
- Realistic: 3–4 weeks with normal iteration
- Pessimistic: 6–8 weeks if Stage 1 needs significant rework

---

## Storage strategy (summary)

| Phase | Storage location | Cost |
|---|---|---|
| During an active session | Vast host disk, bundled in hourly rate | Negligible (~$0.01/hr) |
| Between sessions (if needed for ≤ 1 week) | Vast host disk while instance is stopped | ~$0.20/day for 30 GB |
| Between sessions (if needed for > 1 month) | Cloudflare R2 ($0.015/GB/mo, free egress) | ~$0.45/month, re-download (3–5 min) on each instance launch |

For our timeline: **vast host disk during sessions; destroy instance and re-pull data between sessions** unless gap is < 24 hours.

The 26 GB datasets are publicly hosted; re-downloading from source is 3–5 minutes at gigabit. No need to babysit storage between sessions.

---

## Data transfer strategy

**Do not scp datasets from your local machine** to vast. Your home upload speed will bottleneck for 60+ minutes.

Instead, on every fresh vast instance:
```bash
# COCO-WholeBody
wget http://images.cocodataset.org/zips/train2017.zip
wget http://images.cocodataset.org/zips/val2017.zip
# (plus the WholeBody annotation JSON from its GitHub release)

# FreiHAND
wget https://lmb.informatik.uni-freiburg.de/data/freihand/FreiHAND_pub_v2.zip
```

Datacenter-to-datacenter speeds are 1–10 Gbps. 26 GB completes in 3–5 minutes. The instance is paying ~$0.05–0.10 in idle GPU time during the pull — trivial.

The **only** thing you ever scp from your machine is **our own collected video clips** for Stage 0 calibration and Stage 2 training. That's a few GB at most early on. Push it once to either:
- A persistent vast host disk
- Cloudflare R2 (~$0.50/month for ~30 GB; free egress so pulls are free)

---

## Operational checklist

When ready to launch Stage 1:

1. Run the live offer query (script above). Pick GPU per the selection rule.
2. Launch instance with ≥ 30 GB disk allocation.
3. `wget` both datasets directly to the instance.
4. Verify training data loads correctly with a 10-step dry run.
5. Kick off smoke run (1–2 epochs).
6. If smoke healthy → kick off full training, hop off the instance, return when notification fires.
7. On completion: evaluate against gate criteria. If pass → download model file (~40 MB) locally.
8. Destroy instance. Storage clock stops.

When ready to launch Stage 2:

1. Apply for ASL Citizen dataset access (1–2 day turnaround).
2. Spin up cheaper GPU (4090 or 3090 is fine).
3. Pull ASL Citizen + our own clips.
4. Run Stage 1 detector over all clips to produce keypoint sequences (~2–4 hr).
5. Train hoyso 4-seed ensemble (~3 hr).
6. Evaluate against gate criteria. Download ensemble weights.
7. Destroy instance.

---

---

## Lessons from run #1 + v2 plan

Run #1 (H200, May 2026) revealed that the DLperf-based GPU selection rule is **only valid for compute-bound workloads**. Our pose-estimation pipeline is **CPU/data bound**: each training step does ~60 ms of CPU work (JPEG decode, augmentation, heatmap rasterization) but only ~5 ms of GPU work. The H200 sits at 50–80% utilization with all 24 data-loader workers maxed.

Net effect: ~14 steps/sec actual vs ~190 steps/sec predicted by DLperf scaling. Wall-clock blew up from estimated 1.5 h to ~1.5 h (saved by dropping image size to 256 and epochs to 50) — but on hardware we couldn't fully use. **Roughly $5 of the H200's hourly rate was wasted compute capacity.**

### Corrected GPU selection rule

For pose estimation (and any vision pipeline doing JPEG decode + heatmap gen on CPU):
- **Pick by CPU core count and disk speed, not GPU compute.**
- Once the GPU isn't the bottleneck, anything from RTX 3090 upward is sufficient.
- For our scope: rent the cheapest reliable card with ≥24 CPU cores and ≥1 Gbps internet. Usually a 4090 or 5090 at $0.40–$0.70/hr.
- Only step up to A100/H100/H200 if you've **measured** the workload as compute-bound.

### v2 data pipeline (the cleaner version)

Five changes:

| # | Change | Why | Per-step CPU saved |
|---|---|---|---|
| 1 | **Cache decoded + base-resized images as .npy** (one-time, ~10 min) | JPEG decode + initial resize are deterministic — no reason to redo every epoch | ~10–15 ms/sample |
| 2 | **GPU heatmap generation** — render Gaussians from `(B, K, 2)` keypoint tensors on the GPU via broadcasted torch ops | Heatmap rasterization in numpy loops is the single biggest CPU cost; trivial on GPU | ~15 ms/sample |
| 3 | **Drop the OneOf{MotionBlur, GaussianBlur, GaussNoise}** augmentation | ~10 ms/sample with marginal regularization value at our scale | ~10 ms/sample |
| 4 | **Scene-level FreiHAND split** (hold out by scene_idx, not image_idx) | The 4 background variants per scene cause leakage if split by image | (no perf change; correctness fix) |
| 5 | **Switch to 4090** (~$0.40/hr) once the pipeline is data-bound but cheap CPUs and disks suffice | H200 compute is wasted | ~10× cheaper hourly |

### Random vs deterministic in augmentation

The deterministic half of preprocessing (decode + base resize) can and should be cached. **Random augmentation must stay per-step** — that's the whole point of augmentation. The model needs to see different rotations/crops/colors of the same image across epochs; precomputing N versions and cycling bounds the regularization to a discrete distribution and costs ~N× disk.

The middle ground (cache decoded baseline, randomize on the cached tensor at training time) is the standard compromise.

### Predicted impact

| Metric | Run #1 (H200, naïve pipeline) | Run #2 (4090, v2 pipeline) |
|---|---|---|
| Per-sample CPU | ~60 ms | ~25 ms |
| GPU utilization | 50–80% | ~95% |
| Throughput | ~14 it/s @ batch 128 | ~50–80 it/s |
| 50-epoch wall-clock | ~80 min | ~15–25 min |
| Hourly rate | $4.27 | $0.40 |
| **Total compute cost** | **~$10** | **~$0.30** |

Run #2 is launched in parallel with run #1 ending — they share a code base, only the dataset loader path differs. Compare PCK at the gate; pick the better model.

### Storage strategy update

Run #1 incurred ~$0 in storage (one continuous session, no persistent volume). Run #2 ditto — its preprocessing cache (~32 GB) lives inside the rented instance's allocated disk, not as a separate persistent volume. If we ever do a third iteration, we should push the cache + the trained model to Cloudflare R2 (~$0.50/month for both) so future instances can pull pre-processed data in ~30 seconds instead of re-doing the prep.

### Operational lesson

The plan said "run a 1-epoch benchmark before committing to a GPU choice." We skipped that step. If we hadn't, we'd have caught the data bottleneck before paying H200 rates. **For run #3 and beyond: always run the benchmark first, then size the GPU.**

---

## What we are NOT doing

For clarity, an explicit non-list:

- **Not** using any pretrained model weights at any layer.
- **Not** using MediaPipe-generated pseudo-labels for training (banned by Req 7 / Req 15).
- **Not** doing a hyperparameter sweep — canonical recipes are well-established for both stages.
- **Not** running a reproduction-seed sanity check on Stage 1 (single trained model is sufficient for the pilot; reproduction is research-paper standard).
- **Not** training on still images then expecting magic on video — we sample frames from our own video clips into Stage 1's training mix to close the domain gap.
- **Not** scp'ing datasets from local — direct download to instance is 20× faster.
- **Not** picking the cheapest GPU per hour — picking the GPU with the best wall-clock under budget, paying $1–2 more for hours saved.
