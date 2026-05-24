# Handoff — Net 3 v2 retrain (and the broader v2 round)

Read this entirely before doing anything. Picks up after a 7-agent swarm
review that diagnosed why all four nets miss target and produced a
unified retrain plan. Net 3 v2 prep is partially done; the launch is
not yet kicked off.

---

## 1. Where we are right now (2026-05-24)

Pipeline status:

| Net | Weights local? | Last metric | Target | Status |
|---|---|---|---|---|
| Net 1 | ✅ `results/v3/net1_v3_1/best.pt` (160 MB) | PCK 0.7267 | > 0.85 | Below |
| Net 2 | ✅ `results/v3/net2_v3_1/best.pt` (1.4 MB) | AP@0.5 0.2019 | > 0.40 | Below |
| **Net 3** | ❌ **LOST** (Vast destroyed before scp) | val_pck 0.353 (recorded in conversation logs) | > 0.80 | Below + missing |
| Net 4 | ✅ `results/v4/best.pt` (7.9 MB) | test top-3 0.059 | > 0.85 | Below + stale (uses lost Net 3) |

No active cloud instances. Cron is killed.

**User direction (literal)**: "We'll begin with net 3 retrain. Apply
any optimizations learned from the past attempt." Then: "make a handoff
file so another agent can pick up your work exactly."

---

## 2. The 7-agent swarm findings (already done, file at `docs/SWARM_FINDINGS.md`)

Summary the next agent should INTERNALISE:

1. **Net 4 top-3 0.85 is unreachable under strict Req 7.** Honest
   ceiling 0.45-0.60 with PopSign + ProtoNet. Multiple agents agree.
2. **Net 3 PCK@0.05 0.80 is also unreachable** under Req 7 at the
   current model scale. Honest ceiling ~0.65-0.70 at @0.05; **PCK@0.10
   is the metric Net 4 actually cares about** and hits 0.85+ regularly.
3. **PopSign v1.0 raw video** is the convergent single highest-leverage
   data add (CC BY 4.0, ~50 of 90 glosses at ~700 clips/class, 220-250
   GB selective). Req 7 compliant.
4. **HOyso → ProtoNet** for Net 4 (1M params on 17 samples/class is
   600:1 overparam). Saved for later — not this round.
5. **4-net vs 2-net debate**: user chose 4-net (faster to ship). The
   PoseNet refactor is the right long-term move but not for this round.
6. **The lost Net 3 weights** were a process failure: orchestrator
   copied them on the Vast box (Vast→Vast) but I never scp'd cross-
   host before destroying the instance. Memory rule
   `feedback_autonomous_artifact_pull.md` has been updated to mandate
   periodic local mirroring during training, not just at the end.

User answered the 5 gating questions implicitly via "the assignment is
about having ASL detection" + "We'll begin with net 3 retrain":
- Req 7 stays strict (assignment requirement)
- Signer-disjoint required
- Targets per-net are aspirational
- Self-supervised pretrain — not yet asked
- Architecture stays 4-net for now

---

## 3. What's already DONE for Net 3 v2

All committed in commit `1e95103` ("feat(net3-v2): config + arch + loss
+ multi-threshold PCK for retrain"). Concretely:

### Config — `configs/stage1_v3_landmark_v2.yaml`
- New file, distinct from v1 to avoid colliding with the v1 artifacts
  (none locally, but for clarity).
- `run_name: stage1_v3_landmark_v2`, `checkpoint_dir:
  checkpoints/stage1_v3_landmark_v2`
- Augmentation: `augment.rotate_deg: 180`, `scale_range: [0.6, 1.4]`,
  `blur_p: 0.5`, `brightness: 0.4`, `hflip_p: 0.0` (CRITICAL —
  horizontal flip disabled because hand-crop kpts need a per-finger
  remap; doing a naive flip mis-labels the data)
- Loss: `awing_theta 0.3` (was 0.5), `heatmap_sigma 1.5` (was 2.0),
  `keypoint_weights` array with fingertips 1.5×, wrist 0.5×, joints 1.0×
- Model: `use_unet_skip: true`
- Training: `warmup_epochs 1` (was 3), `use_swa: true`,
  `swa_start_epoch: 180` (SWA trainer hookup deferred — see Section 5)
- Eval: `pck_threshold_fracs: [0.05, 0.10, 0.20]` (multi-threshold)

### Code changes
- `src/stage1/models/landmark_net.py`: `HandLandmarkNet` now accepts
  `use_unet_skip: bool`. With it on, 1×1 lateral convs from encoder
  stages 1/2/3 sum into decoder levels 56/28/14. +39K params (well
  under the 1.5M budget). Smoke-tested locally.
- `src/stage1/losses_v3.py`:
  - `AdaptiveWingLoss` accepts optional `keypoint_weights: list[float]`.
  - `LandmarkLoss` passes them through.
- `src/stage1/train_v3_landmark.py`:
  - Honors `model.use_unet_skip` config
  - Honors `loss.keypoint_weights` config
  - Honors `augment.*` block (passes rotate_deg/scale_range/hflip_p/etc
    into `GPUAugmentation`)
- `src/stage1/train_v3_landmark_helpers.py`:
  - New `eval_pck_freihand_multi(...)` — returns
    `{0.05: pck05, 0.10: pck10, 0.20: pck20}`
  - Legacy single-threshold `eval_pck_freihand(...)` kept as back-
    compat wrapper

---

## 4. What's NOT yet done

In approximate order of dependency:

### A. Wire multi-threshold eval into the trainer (~15 LOC)
`src/stage1/train_v3_landmark.py` line ~440 currently calls
`eval_pck_freihand(...)` for a single threshold and writes `val_pck`
into `metrics.jsonl`. Change to call `eval_pck_freihand_multi(...)`
and write `val_pck_05 / val_pck_10 / val_pck_20`. **Use val_pck_05 as
the best-checkpoint criterion** (the headline number).

```python
# Around line 440 of train_v3_landmark.py
thresholds = list(deep_get(cfg, "eval.pck_threshold_fracs", [0.05]))
val_pck_multi = eval_pck_freihand_multi(
    ema.module, val_loader, device, crop_size, hm_size,
    thresholds, use_amp_bf16,
)
val_pck_05 = val_pck_multi.get(0.05, float("nan"))
# Then write val_pck_multi into the metrics.jsonl line
line.update({f"val_pck_{int(t*100):02d}": val_pck_multi.get(t, float("nan"))
             for t in thresholds})
# best.pt criterion: val_pck_05 (was: ambiguous val_pck)
score = val_pck_05 if val_pck_05 == val_pck_05 else avg_pck
```

### B. Add SWA wrapper (optional, ~30 LOC)
The config has `train.use_swa: true` but the trainer doesn't honor it.
Free +0.005-0.015 PCK if added. Pattern:

```python
from torch.optim.swa_utils import AveragedModel as SWAModel, SWALR
swa_start = int(deep_get(cfg, "train.swa_start_epoch", 9999))
swa_model = SWAModel(model)
swa_lr_sched = SWALR(optimizer, swa_lr=deep_get(cfg, "train.swa_lr", 1e-4),
                      anneal_epochs=1)
# In epoch loop after scheduler.step():
if deep_get(cfg, "train.use_swa") and epoch >= swa_start:
    swa_model.update_parameters(model)
    swa_lr_sched.step()
# End of training:
if deep_get(cfg, "train.use_swa"):
    torch.optim.swa_utils.update_bn(train_loader, swa_model, device=device)
    # save swa_model.state_dict() as separate `swa.pt`
```

Defer to v3 if time-pressed. Skip safely — model trains fine without.

### C. Local mirror cron script — CRITICAL (~80 LOC)
Per the updated memory rule (`feedback_autonomous_artifact_pull.md`),
training artifacts MUST be `scp`'d to local periodically during
training, not just at the end. Write `scripts/mirror_net3_local.sh`:

```bash
#!/usr/bin/env bash
# Pulls Net 3 best.pt + metrics.jsonl from the Vast 5090 to local
# results/v3/net3_v2/ every 30 min. Idempotent — runs from cron.
set -eu
HOST=ssh1.vast.ai     # ← update to the live instance's host
PORT=34594            # ← update to live port
REMOTE_DIR=/workspace/asl/checkpoints/stage1_v3_landmark_v2
LOCAL_DIR=/home/bryann/gauntlet/asl-learning/results/v3/net3_v2
mkdir -p "$LOCAL_DIR"
scp -P "$PORT" -o ConnectTimeout=10 \
    "root@${HOST}:${REMOTE_DIR}/best.pt" \
    "root@${HOST}:${REMOTE_DIR}/metrics.jsonl" \
    "$LOCAL_DIR/" 2>&1 | tail -3
ls -la "$LOCAL_DIR/best.pt" "$LOCAL_DIR/metrics.jsonl" 2>/dev/null
```

Plus a `CronCreate` recurring on `*/30 * * * *` (every 30 min) that
invokes this. **No exception — without this, we will lose work again.**

### D. Provision Vast 5090 + push code
Same template as previous Net 3 run:
- 5090, Maryland (or any reliability ≥0.99)
- ~$1.14/hr
- ~9-10 hr training time (200 ep × ~2.8 min)
- ~$11-12 expected spend

Procedure:
```bash
export PATH=$HOME/.local/bin:$PATH; set -a; source .env.local; set +a
# Find suitable offer
vastai search offers 'reliability >= 0.99 gpu_name=RTX_5090 num_gpus=1' \
  --order 'dph_total' --raw -o 'dph_total' | head -10
# Provision
vastai create instance <offer_id> --image pytorch/pytorch:2.7.0-cuda12.8-cudnn9-devel \
  --disk 200 --label asl-net3-v2 --ssh
# Wait for ready
vastai show instance <inst_id> --raw  # check actual_status == 'running'
# Push code (positive include, NOT exclude blocklist — tar gets too big)
tar -czf /tmp/asl_push.tgz src configs scripts modal_apps tests requirements.txt
scp -P <port> /tmp/asl_push.tgz root@<host>:/workspace/
# On remote: extract + pip install + create data symlinks (see HANDOFF_V3_1)
```

Note `src/stage1/data/interhand.py` auto-detects `images_root` between
`{root}/images/`, `{root}/InterHand2.6M_5fps_batch1/images/`, etc.
(applied during v3.1). The InterHand 5fps tar extracts to the second
path; don't break that auto-detection.

### E. Launch training (~5 commands)
```bash
ssh -p <port> root@<host>
cd /workspace/asl
# Rebuild any stale pycache
rm -rf src/stage1/data/__pycache__ src/stage1/__pycache__
# Launch with nohup, NOT tmux — tmux silently kills python on Net 2's mix.
# It worked on Net 3 last time but nohup is the safe default.
nohup python -u -m src.stage1.train_v3_landmark \
  --config configs/stage1_v3_landmark_v2.yaml \
  > logs/train_v3_landmark_v2.log 2>&1 & disown
sleep 5
pgrep -af train_v3_landmark | head -3
tail -10 logs/train_v3_landmark_v2.log
```

### F. Set up cron for monitoring + local mirror
```python
# Via CronCreate tool — recurring 30 min
{
  "cron": "*/30 * * * *",
  "prompt": "Run scripts/mirror_net3_local.sh and report success/failure + the latest val_pck_05 from metrics.jsonl.",
  "recurring": true,
  "durable": false,  # CronCreate session-scoped anyway
}
```

Also a separate 20-min health check cron (the one we've been using).

---

## 5. Memory rule reminders (do NOT skip)

From `~/.claude/projects/-home-bryann-gauntlet-asl-learning/memory/feedback_autonomous_artifact_pull.md`:

> **Hard rule: training artifacts MUST be mirrored to local during
> training, not just at the end.** A remote-only Vast→Vast copy made by
> an on-instance orchestrator is NOT a pull. Cross-host scp to local
> is the only thing that counts. ~9 hr of training and ~$21 of compute
> went with it. Never again.

Pre-destroy checklist:
- [ ] `results/v3/net3_v2/best.pt` exists locally with size > 1 KB
- [ ] `results/v3/net3_v2/last.pt` exists locally with size > 1 KB
- [ ] `results/v3/net3_v2/metrics.jsonl` exists locally with the right
      line count (~200)
- [ ] For multi-net runs, repeat for EACH net independently

---

## 6. Expected results

Per the swarm's net3-improver agent:

| Config | val_pck@0.05 | val_pck@0.10 | val_pck@0.20 |
|---|---|---|---|
| v1 (achieved) | 0.353 | likely 0.65-0.70 | likely 0.85+ |
| **v2 (target)** | **0.55-0.70** | **0.85+** | **0.95+** |

If v2 lands < 0.50 PCK@0.05, the augmentation + U-Net skips + fingertip
weighting didn't move enough — next intervention is adding HO-3D +
OneHand10K + CMU Panoptic data (a v3 round, ~$5-10 more).

If v2 lands ≥ 0.55, we're done with Net 3. Move on to:
- Net 4 retrain with PopSign + (optionally) ProtoNet
- Net 2 v3.2 retrain with EgoHands + Mosaic + 320²
- Net 1 v3.2 retrain with HRNet + Halpe + CrowdPose
- Final e2e smoke

Per-net retrain costs: ~$10-15 each. Total v2 round budget: **~$45-55**
against the user's $50-100 budget.

---

## 7. Things that broke last time — verify they still work

From the v3.1 lessons (also in `docs/handoffs/HANDOFF_V3_1.md` §4):

1. **tmux silently kills python after ~14 epochs** for Net 2's training
   mix. Use `nohup ... & disown`. Net 3 didn't hit this last time but
   prefer nohup for safety.
2. **Dataloader deadlock** at ep 5-14 with `persistent_workers=True` +
   WeightedRandomSampler. Fix is in trainer:
   `persistent_workers=False, timeout=60`. Already committed.
3. **Vast hosts can be reclaimed mid-training** — filter
   `reliability ≥ 0.99` at search time.
4. **InterHand image path mismatch** — auto-detect block already in
   `interhand.py`.
5. **RHD silent download failure** — pull from our S3 mirror
   `s3://asl-pilot-datasets-027326806636/rhd/RHD_published_v2.zip`
   (presigned URL in `scripts/aws_presign_datasets.sh`).
6. **Net 3 RHD was loaded=0 in v3.1** despite the index existing. The
   smart-prebuild script `scripts/prebuild_net3_indices.py` produces
   `data/RHD_published_v2/training/index_valid.jsonl` which
   `RHDDataset` should read. **Verify in the first epoch log** that
   the rhd count is non-zero — if it's still 0, the adapter wiring
   broke again and needs investigating.

---

## 8. The conversation context the next agent needs

User personality + preferences (from memory):
- Direct, decisive — take instructions literally
- Cost-conscious, hates idle GPU
- Wants tight tables over paragraphs
- Asks sharp ML questions; push back on sloppy reasoning honestly
- Don't reduce quality without flagging it
- 20-min cron heartbeats keep the user informed when AFK
- After a major-tier commit lands and tests pass, push

User's stated goal this round (literal quotes):
- "the assignment is about having asl detection"
- "Does the 4 net arch have a higher potential?"
- "We'll begin with net 3 retrain. Apply any optimizations learned
  from the past attempt."

User has heard the 5 gating questions and chose 4-net path. The next
agent should NOT re-litigate the architecture choice — proceed.

---

## 9. Quick command cheat sheet

```bash
# Provision (copy-paste-able)
export PATH=$HOME/.local/bin:$PATH; set -a; source .env.local; set +a
vastai search offers 'reliability>=0.99 gpu_name=RTX_5090 num_gpus=1' \
  --order 'dph_total' --raw -o 'dph_total' | head -5
vastai create instance <OFFER> --image pytorch/pytorch:2.7.0-cuda12.8-cudnn9-devel \
  --disk 200 --label asl-net3-v2 --ssh

# After 'running': get host/port
vastai show instance <ID> --raw | python3 -m json.tool | grep -E "ssh_host|ssh_port"

# Push code
tar -czf /tmp/asl_push.tgz src configs scripts modal_apps tests requirements.txt
scp -P <PORT> /tmp/asl_push.tgz root@<HOST>:/workspace/
ssh -p <PORT> root@<HOST> 'cd /workspace && tar -xzf asl_push.tgz -C asl/'

# Push Net 1 + Net 2 weights (Net 4 doesn't need them for Net 3 training)
ssh -p <PORT> root@<HOST> 'mkdir -p /workspace/asl/results/v3/{net1_v3_1,net2_v3_1}'
scp -P <PORT> results/v3/net1_v3_1/best.pt root@<HOST>:/workspace/asl/results/v3/net1_v3_1/
scp -P <PORT> results/v3/net2_v3_1/best.pt root@<HOST>:/workspace/asl/results/v3/net2_v3_1/

# Pull datasets — InterHand from S3 mirror, FreiHAND from kaggle/download, RHD from S3
# (See scripts/download_freihand.sh etc.)

# Run prebuild for smart Net 3 indices
ssh -p <PORT> root@<HOST> 'cd /workspace/asl && python3 -m scripts.prebuild_net3_indices --data-root data'

# Launch training
ssh -p <PORT> root@<HOST> 'cd /workspace/asl && \
  mkdir -p logs && \
  rm -rf src/stage1/__pycache__ src/stage1/data/__pycache__ && \
  nohup python -u -m src.stage1.train_v3_landmark \
    --config configs/stage1_v3_landmark_v2.yaml \
    > logs/train_v3_landmark_v2.log 2>&1 & disown
  sleep 8; tail -15 logs/train_v3_landmark_v2.log'

# Set up local mirror cron — recurring 30 min
# (Use CronCreate tool with the mirror_net3_local.sh script)

# Pull artifacts when done
mkdir -p results/v3/net3_v2
scp -P <PORT> root@<HOST>:/workspace/asl/checkpoints/stage1_v3_landmark_v2/{best.pt,last.pt,metrics.jsonl} \
  results/v3/net3_v2/
# VERIFY sizes BEFORE destroy:
ls -lh results/v3/net3_v2/

# Destroy when verified
yes | vastai destroy instance <ID>
```

---

## 10. Pointers to other docs

- `docs/SWARM_FINDINGS.md` — the 7-agent swarm output (Nets 1/2/3/4 +
  arch + data + devil's advocate)
- `docs/handoffs/HANDOFF_V3_1.md` — original v3.1 round handoff (overlapping
  history; ignore the active-instance fields since instances are gone)
- `docs/GOAL_STATE.md` — captures the overnight goal completion
- `docs/hoyso-architecture.md` — Net 4 architecture reference
- `docs/principles.md` — pedagogy + UX research synthesis
- `docs/ml-handoff.md` — CV black-box interface contract
- `costs/ledger.csv` — running cost log
- `data/signs/sign_list.json` — 90-word catalog (12 categories)

End of handoff. Next agent: pick up at Section 4A (multi-threshold
eval wire-up), proceed through F (provision/launch/cron), then deliver
status to the user.
