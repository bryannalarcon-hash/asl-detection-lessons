# Dataset and Model Training

This document records every dataset used, how each of the four networks was
built and trained, and the concrete evidence that the whole pipeline is
**trained from scratch** with no pretrained weights, no distillation, and no
MediaPipe-derived supervision (the project calls this requirement "Req 7").
MediaPipe appears in the repo only as an optional dev-demo visual baseline; it
is never in the deployed inference path and is never a training signal.

All claims below cite repo file paths so they can be checked directly.

---

## 1. The four-net cascade

The recognizer is a per-frame computer-vision stack (Stage 1) feeding a
temporal sign classifier (Stage 2):

| Net | Role | Consumes | Produces |
|-----|------|----------|----------|
| Net 1 | Face + body keypoints | full RGB frame | 7 face/body keypoint heatmaps |
| Net 2 | Palm detector | full RGB frame | palm bounding boxes |
| Net 3 | Hand landmarks | each hand crop from Net 2 | 21 hand keypoints per crop |
| Net 4 | Sign classifier | 49-keypoint trajectory over time | sign class logits |

Net 1 and Net 2 run on the whole frame. Net 2's palm boxes are cropped and each
crop is passed to Net 3 for 21 hand landmarks. Net 1's 7 face/body points plus
Net 3's two hands (21 + 21) assemble the 49-keypoint schema
(`src/stage1/data/schema.py`, `NUM_KEYPOINTS = 49`). Net 4 consumes the
per-frame 49-keypoint trajectory, not pixels. The single bridge from Stage 1 to
Stage 2 is `src/stage2/data/extract_keypoints.py`, which runs the frozen Net 1/2/3
checkpoints over raw video and writes `(T, 49, 2)` keypoint tensors per clip.

---

## 2. Per-net architecture and training

### Net 1 — face/body keypoint detector
- **Architecture** (`src/stage1/models/detector.py`): SimpleBaseline-style
  ResNet-like encoder (stem + 4 down-stages, 32->384 ch) with three transposed-conv
  deconv stages to an output-stride-4 heatmap; final 1x1 to K channels. ~8M params,
  "trained fully from scratch — no pretrained weights at any layer" (docstring lines 18-19).
- **Training data + mix** (`configs/stage1_v2_facebody.yaml`): COCO-WholeBody 0.70,
  MPII 0.30 (`sample_ratio_coco`/`sample_ratio_freihand` + `target_mix`). Keypoint
  slice `[42, 49]` keeps the 3 face + 4 body points.
- **Hyperparameters**: base run from scratch (no `resume_from`), 210 epochs, lr 1e-3,
  weight decay 1e-4, BF16. The v3.1 config (`configs/stage1_v2_facebody_v3_1.yaml`)
  finetunes from Net 1's **own** earlier checkpoint (`resume_from: results/v3/net1/.../best.pt`),
  not an external pretrained model — a self-warm-start.

### Net 2 — palm detector
- **Architecture** (`src/stage1/models/palm_detector.py`): depthwise-separable
  backbone (stem + 4 stages, 24->128 ch) tapped at strides 8/16/32, with a mini-FPN
  top-down lateral path and a shared cls/box prediction head. ~615K params.
- **Training data + mix** (`configs/stage1_v3_detector_v3_1.yaml`, `target_mix`):
  COCO-WholeBody 0.55, HaGRID 0.20, EgoHands 0.10, FreiHAND 0.05, synthetic 0.10.
  Two-stage curriculum: stage_a HaGRID-only pretrain, stage_b balanced-mix finetune
  initialized from stage_a's own `best.pt` (`curriculum.stage_b.init_from`).
- **Hyperparameters**: focal loss (alpha 0.25, gamma 2.0), batch 256, lr 1e-3 (stage_a)
  / 1e-4 (stage_b), cosine schedule, EMA 0.9998, BF16. HaGRID is used **bbox-only**;
  its MediaPipe-pseudo landmarks are stripped at ingest (`src/stage1/data/hagrid.py`,
  `scripts/hagrid_reorganize.py`).

### Net 3 — hand landmark regressor
- **Architecture** (`src/stage1/models/landmark_net.py`): MobileNetV2-lite encoder
  (stem + stage1-4, 32->256 ch at 7x7). Two heads share the same from-scratch encoder:
  `HandLandmarkNet` (heatmap, 56x56x21) and `HandLandmarkRegNet` (direct coordinate
  regression). ~1.27M params (under the 1.5M budget). Docstring lines 15-16: "All
  weights trained from scratch — no MediaPipe, no ImageNet pretrain, no distillation (Req 7)."
- **Training data + mix** (`configs/stage1_v3_landmark_reg.yaml` / `..._v2.yaml`,
  `target_mix`): FreiHAND 0.60, InterHand2.6M (single-hand) 0.30, RHD 0.10.
- **Hyperparameters** (regression config): batch 256, 150 epochs, 250k samples/epoch,
  lr 1e-3 -> 1e-5 cosine, weight decay 1e-4, EMA 0.9998, BF16, smooth-L1 loss
  (beta 0.04), fingertip-weighted keypoints, rotation canonicalization. The v2 heatmap
  config adds U-Net skips, AdaptiveWing loss, and SWA over the final 20 epochs.

### Net 4 — sign classifier
- **Architecture** (`src/stage2/models/sign_classifier.py`): PyTorch port of the
  hoyso48 ISLR stack — Dense(192) stem, two blocks of [3x Conv1DBlock(k=17) +
  TransformerBlock(4 heads)], Dense(384), masked global average pool, LateDropout,
  Dense(num_classes). Built and initialized in-module; no external weights.
- **Training data**: PopSign v1.0 raw video, keypoint trajectories extracted by **our
  own** frozen Net 1/2/3 checkpoints (`build_manifest_popsign.py` lines 35-38:
  `--net1/--net2/--net3 results/v3/...best.pt`). Per-frame feature dim derived at
  runtime (`feature_dim(...)`); num_classes derived from the catalog
  (`len(gloss_to_idx)`), not hardcoded.
- **Hyperparameters** (`configs/stage2_v4_classifier_popsign.yaml`): batch 128,
  100 epochs, lr 1e-3 -> 1e-5 cosine, weight decay 1e-4, EMA 0.9995, BF16,
  label smoothing 0.1, late-dropout 0.8 from step 4000.

---

## 3. Datasets

| Dataset | Modality | License | Used by | Acquisition |
|---------|----------|---------|---------|-------------|
| COCO-WholeBody | image | research/academic | Net 1, Net 2 | `gdown` annotation + `wget` train2017 (`scripts/download_v3_data.sh`) |
| MPII Human Pose v1.0 | image | research use (Andriluka et al. 2014) | Net 1 | `scripts/download_mpii.sh` |
| HaGRID v1 | image (bbox only) | academic | Net 2 | Kaggle `kapitanov/hagrid` ann + `innominate817/hagrid-sample-500k-384p` |
| EgoHands | image | academic | Net 2 | `scripts/download_egohands.sh` |
| FreiHAND | image | academic | Net 2, Net 3 | Kaggle `danieldelro/freihand` |
| InterHand2.6M (5fps) | image | academic | Net 3 | S3 split-tar parts + gdrive annotations |
| RHD (synthetic render) | image | research | Net 3 | `scripts/download_rhd.sh` |
| Synthetic hand-in-scene | image (composite) | derived from FreiHAND+COCO | Net 2 | `scripts/build_synthetic_composites.py` |
| PopSign v1.0 | raw video | CC BY 4.0 (attribution) | Net 4 | per-sign `.tar` over HTTPS (`signdata.cc.gatech.edu`) |

PopSign is CC BY 4.0 and requires attribution; the academic-license datasets
are for research use. Vocabulary (~96 PopSign CDI words) is in
`configs/popsign_vocab.json`; sourcing rationale in `docs/handoffs/net4_data_sourcing.md`.

---

## 4. No-pretrained-models evidence (Req 7)

**Statement.** No network in this pipeline uses pretrained weights, pretrained
backbones, knowledge distillation, or pseudo-labels. A repo-wide search for
`pretrained`, `torchvision.models`, `timm`, `model_zoo`, `hub.load`, and
`IMAGENET` weights in `src/` returns **zero** functional uses — every hit is a
comment/docstring affirming the from-scratch policy.

Per-net proof:
- **Net 1** (`detector.py`): `_init_weights` uses `kaiming_normal_` for conv/deconv,
  constant BN init, small-std final layer. No state-dict load of external weights.
- **Net 2** (`palm_detector.py`): `_init_weights` kaiming + focal-prior bias init.
  HaGRID's MediaPipe-pseudo landmarks are explicitly dropped (Req 7) and only
  human-annotated bboxes are consumed.
- **Net 3** (`landmark_net.py`): `_init_weights` kaiming for convs, normal(std=0.01)
  for the FC head; both heads share one from-scratch encoder. No pretrained load.
- **Net 4** (`sign_classifier.py`): all layers constructed and default-initialized
  in-module; training input is keypoints produced by our own Net 1/2/3, not the
  banned Kaggle MediaPipe-landmark parquet (see `net4_data_sourcing.md`: "Kaggle
  `asl-signs` landmark parquet is BANNED (MediaPipe-derived)... all sources ship RAW VIDEO").

**MediaPipe scope.** MediaPipe is referenced only as (a) a keypoint-ordering
convention ("MediaPipe-style" index layout) and (b) an optional dev-demo overlay.
It is not loaded in the deployed inference path and provides no training labels.

**Self-warm-starting caveat.** Net 1 v3.1 and the Net 2/Net 3 curricula resume
from their **own** prior checkpoints (`resume_from` / `init_from`). These are
checkpoints this project trained from scratch, not external pretrained models.

---

## 5. Reproducibility

Run on a GPU box with ~200 GB disk (Stage 1 datasets are large; PopSign is
streamed per-sign). Sequence:

```bash
# 1. Datasets (all four nets)
bash scripts/download_v3_data.sh                 # COCO, FreiHAND, HaGRID, InterHand, EgoHands, MPII, RHD, synthetic

# 2. Net 1 (face/body), from scratch
python -m src.stage1.train_v2_facebody --config configs/stage1_v2_facebody.yaml

# 3. Net 2 (palm), two-stage curriculum
python -m src.stage1.train_v3_detector --config configs/stage1_v3_detector_v3_1.yaml --stage stage_a
python -m src.stage1.train_v3_detector --config configs/stage1_v3_detector_v3_1.yaml --stage stage_b

# 4. Net 3 (hand landmarks), regression head
python -m src.stage1.train_v3_landmark_reg --config configs/stage1_v3_landmark_reg.yaml

# 5. Net 4 data: extract keypoints from raw PopSign video using OUR Net 1/2/3
#    (per-sign download -> extract -> keypoint -> rm; see build_manifest_popsign.py header)
python -m src.stage2.data.extract_keypoints \
    --manifest <clip list> \
    --net1 results/v3/net1_v3_1/best.pt \
    --net2 results/v3/net2_v3_1/best.pt \
    --net3 results/v3/net3_v2/best.pt \
    --out data/signs/popsign_kpt_cache/ --max-frames 64 --delete-after
python -m src.stage2.data.build_manifest_popsign \
    --vocab configs/popsign_vocab.json --kpt-dir data/signs/popsign_kpt_cache \
    --sign-list-out data/signs/popsign_sign_list.json

# 6. Net 4 (sign classifier), from scratch
python -m src.stage2.train_v4_classifier --config configs/stage2_v4_classifier_popsign.yaml
```

Exact CLI flags for each trainer are in the file headers
(`src/stage1/train_v3_detector.py`, `src/stage1/train_v3_landmark_reg.py`,
`src/stage2/train_v4_classifier.py`).
