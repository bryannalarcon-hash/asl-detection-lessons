# Handoff — v3.1 Training Round (2026-05-24 00:30 UTC)

Read this entirely before doing anything. Supersedes prior handoffs
for active work; older docs in this directory are historical.

The session goal is still active: **train Net 1, Net 2, Net 3.
Report on each run finish. 20-min health check across all training.
Show each epoch update. Don't reduce quality.**

---

## 1. TL;DR — where things stand right now

| Net | Status | Best metric so far | Cost so far |
|---|---|---|---|
| **Net 1** | ✅ DONE | PCK_overall **0.7267** @ ep 18 (val on COCO val) | Modal **$3.83** of $7 |
| **Net 2** | TRAINING — Stage B ep 24/30 | train_loss 0.258 (best ep 12 was 0.271) | Vast share of $-16.70 net spend |
| **Net 3** | TRAINING — patched ep 0 in flight | (no patched-run metric yet) | Vast share of $-16.70 net spend |

Combined balances right now:
- Vast: **$22.70** (started at $6, user topped up ~$25)
- Modal: **$3.17**
- AWS: **$100.00** (untouched; quota appeal status `CASE_OPENED`)
- **TOTAL: $125.87**

Currently:
- Net 2 (Vast 5090, Maryland) will finish in ~30 min (~6 epochs left × 5.2 min)
- Net 3 (Vast 5090, Maryland) is ~7 min into a 30-min ep 0 — at this pace 200 ep = ~100 hr, **not viable**

---

## 2. Active infrastructure

### Vast instances (both training, both same hardware family)
| Instance | Net | Host | SSH | $/hr GPU | Process PID |
|---|---|---|---|---|---|
| `37489627` | Net 2 | Maryland, US, RTX 5090, reliability 0.9989 | `ssh6.vast.ai:19626` | $1.01 | 9433 (nohup) |
| `37514594` | Net 3 | Maryland, US, RTX 5090 | `ssh1.vast.ai:34594` | $1.14 | 3760 (nohup) |

SSH host/port files cached locally at:
- `/tmp/asl_logs/net2_ssh_host.txt` / `net2_ssh_port.txt`
- `/tmp/asl_logs/net3_ssh_host.txt` / `net3_ssh_port.txt`

If those files are missing (e.g. session restart wiped /tmp), refetch with:
```bash
export PATH=$HOME/.local/bin:$PATH; set -a; source .env.local; set +a
vastai show instances --raw | python3 -m json.tool   # find both instances
# Per-instance JSON has ssh_host and ssh_port fields.
```

SSH config in `~/.ssh/config` includes `Host *.vast.ai` block that picks
`~/.ssh/vast_v3` as IdentityFile — direct `ssh -p PORT root@ssh*.vast.ai`
works without -i flag.

### Modal
- Account: `bryannalarcon`, CLI at `~/.local/bin/modal`, authed via .env.local
- App `asl-net1-v3-1` is **stopped** (Net 1 finished cleanly at exit 0)
- Volume `asl-net1-vol` persists with Net 1's checkpoints

### AWS
- IAM user `asl-learning`, account `027326806636`
- S3 bucket **`asl-pilot-datasets-027326806636`**:
  - `rhd/RHD_published_v2.zip` (8.5 GB, ✓)
  - `egohands/egohands_yolo.tar.gz` (819 MB, ✓ already YOLO-converted)
- S3 bucket `asl-net3-data` exists (would be Net 3 checkpoint destination if AWS quota lands)
- Budget alarm `asl-pilot-monthly-cap` at $50/mo, emails to bryannalarcon@gmail.com
- **Spot G/VT quota: CASE_OPENED**, appeal text submitted from `docs/aws_quota_appeal.md`. Not yet approved.

### Modal Secret `asl-kaggle`
Already configured. Used by `modal_apps/train_net1_v3_1.py`.

---

## 3. Net 1 — DONE

| Field | Value |
|---|---|
| Architecture | KeypointDetector face+body slice K=7, 8M params, 256² input, BF16 |
| Config | `configs/stage1_v2_facebody_v3_1.yaml` |
| Trainer | `src/stage1/train_v2_facebody.py` |
| Modal app | `modal_apps/train_net1_v3_1.py` (A100-40GB) |
| Resume point | warm-started from v3's `best.pt` (PCK 0.71) |
| Mix | COCO-WholeBody 0.70 / MPII 0.30 |
| Final | epoch 38/60 (early-stopped on plateau), best at ep 18 PCK 0.7267 |
| Lift vs v3 baseline (0.709) | **+0.018** |
| Per-split val PCK | `pck_face=0.0 pck_body=0.0` — **eval bug** (compute_pck indexing on K=7 sliced model). Real face/body split needs `scripts/eval_nets.py` re-run. Tracked as task #58. |
| Artifacts | `results/v3/net1_v3_1/best.pt`, `last.pt`, `metrics.jsonl` (all 38 epochs) |

User accepted Net 1 as-is — chose not to re-train with v3.2 ideas
(50% MPII, lr/3, add CrowdPose). Defer to next round.

---

## 4. Net 2 — TRAINING (Stage B nearing completion)

| Field | Value |
|---|---|
| Architecture | PalmDetector with mini-FPN, 332K params (FPN on), 256² input, BF16 |
| Config | `configs/stage1_v3_detector_v3_1.yaml` |
| Trainer | `src/stage1/train_v3_detector.py` (run with `--stage stage_b --resume-from ...`) |
| Launcher | NOT using `scripts/launch_net2_v3_1.sh` — direct ssh + nohup (tmux was killing the process) |
| Stage A | DONE — 40 epochs HaGRID-only pretrain, best.pt at ep 38 loss 0.041 |
| Stage B | RUNNING — ep 24/30, loss 0.258, balanced mix |
| Mix (effective) | coco_wholebody 0.611 / hagrid 0.222 / freihand 0.056 / synthetic 0.111 (egohands renormalized out since download_egohands.sh failed and trainer skips empty) |
| Target metric | AP@IoU=0.5 > **0.40** on COCO val (v3 was 0.033) |
| When done | Pull checkpoint via `scp -P 19626 root@ssh6.vast.ai:/workspace/asl/checkpoints/stage1_v3_detector_v3_1/stage_b/best.pt results/v3/net2_v3_1/best.pt`. Then run `python3 -m scripts.eval_nets --net2 results/v3/net2_v3_1/best.pt --input-size 256 --use-fpn` for held-out AP. |

### Net 2 bugs hit + patches landed today

1. **Vast host reclaim** — first instance (37486581) died after 12 min. Patched launcher to filter `reliability>0.99`.
2. **Tarball too big** — original launcher packaged whole repo including `.venv-demo/` (5.6 GB). Patched to positive-include list (src+configs+scripts+modal_apps+tests+requirements.txt → 167 KB).
3. **Vast search-offers JSON parse intermittent failures** — patched retry loop.
4. **SSH key not registered on Vast** — fixed once via `vastai create ssh-key` + `~/.ssh/config` Host block.
5. **UnboundLocalError on `epoch` in post-loop save** — Stage B's warm-start from Stage A's best.pt set `start_epoch=39` but Stage B config has 30 ep total → empty range → `for` loop never executed → undefined `epoch`. Fixed by adding `args.warm_start=True` path in `train_v3_detector.py` so init_from doesn't inherit epoch counter.
6. **Dataloader deadlock around ep 5-14** — workers accumulated state in persistent_workers=True with WeightedRandomSampler + 5 mmap caches. Patched: `persistent_workers=False, timeout=60`.
7. **tmux session-killed-the-process pattern** — every restart via tmux died silently at ~ep 14 ~52%. **Switched to direct `nohup` + `disown`**; this is what's working now.

Net 2 has restarted ~6 times today. Current run from `best.pt` (ep 12) is at ep 24 — stable since tmux was eliminated.

### When Net 2 finishes
- Touch file appears at `/workspace/asl/.train_done`
- last.pt + best.pt + metrics.jsonl in `/workspace/asl/checkpoints/stage1_v3_detector_v3_1/stage_b/`
- Pull artifacts, run eval, destroy instance
- Vast 5090 freed → Net 3 keeps running on its own instance (separate billing)

---

## 5. Net 3 — TRAINING (post-prebuild, but epochs too long)

| Field | Value |
|---|---|
| Architecture | HandLandmarkNet 1.27M params, 224² input, 21 kpts × 56×56 heatmap |
| Config | `configs/stage1_v3_landmark_v1.yaml` |
| Trainer | `src/stage1/train_v3_landmark.py` |
| Mix (config) | FreiHAND 0.60 / interhand_single 0.30 / RHD 0.10 |
| Mix (actual) | freihand=130,240 / interhand=1,432,581 / **rhd=0** (RHD index built but landmark_dataset.py doesn't load it — bug, see below) |
| Target | PCK@0.05 > **0.80** on FreiHAND held-out (1628 samples) |
| Current | ep 0 in flight, GPU 96% / 9.9 GB VRAM, PID 3760 |
| Per-epoch time | **~30 min** (11,700 iter at 6.4 it/s) — **NOT viable** for 200 ep run |
| Artifacts dir | `/workspace/asl/checkpoints/stage1_v3_landmark_v1/` |

### Net 3 bugs hit + patches landed today

1. **Driver downloaded ALL datasets via `download_v3_data.sh` (no flag)** — wasted ~30 min downloading HaGRID, COCO, MPII that Net 3 doesn't need.

2. **`download_rhd.sh` silent failure** — Net 3 instance never got RHD. Fixed by pulling from our S3 mirror at LAN speed (4 min for 8.5 GB).

3. **InterHand image path mismatch** — original adapter looked at `data/interhand/images/<split>/...` but FB's 5fps tar extracts to `data/interhand/InterHand2.6M_5fps_batch1/images/<split>/...`. Result: **ALL 1.36M InterHand samples were being silently skipped** on the first run; only FreiHAND was effectively training. Patched the adapter to auto-detect images_root with the 5fps prefix.

4. **Per-batch missing-image discovery / no validated index** — every batch had cv2.imread failures flooding the log. Fixed via `scripts/prebuild_net3_indices.py` which validates image-exists per dataset and writes JSONL indices the adapter consumes (one-time pass, ~10 min).

5. **Conservative "single-hand only" filter** — original filter dropped all interacting frames. Smarter filter (in prebuild script): keep `right` and `left` always; keep `interacting` frames where right/left hand 3D centroids are >100mm apart (geometrically guaranteed non-overlapping in 2D). **Recovered nearly 3× more training data** (1.43M InterHand vs 495K).

### Outstanding Net 3 issues

1. **PENDING DECISION: cap `samples_per_epoch`** to make 200-ep training feasible.
   - Currently 1.43M × 2 (right+left expansion) + 130K = ~3M items per epoch via WeightedRandomSampler with default `num_samples=len(ds)`.
   - At 6.4 it/s, 11,700 iter/ep = ~30 min/epoch × 200 = ~100 hr. Untenable.
   - **Fix**: set `num_samples=250000` (or `train.samples_per_epoch: 250000` in config). Each epoch ~2.5 min × 200 = **~8 hr**. Stochastic sampling preserves quality — across 200 epochs sees ~50M random draws from the 3M pool, ~17× coverage.
   - Plus: wire RHD's index (it built fine at 41K but `landmark_dataset.py` doesn't reference it).
   - **User hasn't confirmed yet** — waiting for green light.

2. **2D bbox not in index** — prebuild stores 3D world_coord but bbox crops are computed at sample time via `palm_bbox(coords, visible, side)`. Slow path is fine; no fix needed.

3. **Per-split metrics bug** — same compute_pck issue as Net 1. Real PCK_face/body might not be 0 like the trainer log shows.

---

## 6. Cost ledger

`costs/ledger.csv` is the source of truth. Auto-update via:
```bash
python3 -m scripts.cost_ledger --note "your-reason"
```

Session-start balances (anchored in row 1-3 of ledger): Vast $6, Modal $7, AWS $100.

Current row format:
`ts, provider, balance_usd, spent_since_prev_usd, mtd_usd, source, note`

Spend so far this round:
- Modal: $3.83 (Net 1 only — 38 epochs A100-40 finetune)
- Vast: -$16.70 spent_net (started $6, user added ~$25 mid-session, currently $22.70)
- AWS: $0

20-min cron updates the ledger automatically with `python3 -m scripts.cost_ledger --note "20m health check"`.

S3 mirror's purpose: insurance against fragile third-party hosts.
RHD (Freiburg server down) and EgoHands (Roboflow URL broke) both pre-staged. **Do not delete** — user instructed to keep "in case we pull a checkpoint and want to migrate to AWS later."

---

## 7. Commits today (chronological)

```
f877ac5  v3.1: balanced sampling + mini-FPN + new datasets + AWS hardening
583636f  fix: track src/stage1/data/ modules previously hidden by over-broad gitignore
f0e1dad  fix(net2-launcher): cache all 5 v3.1 sources, not just hagrid+coco
c27678e  feat(net1-v3.1): Modal app for face+body finetune with MPII mix
1721ab2  fix(net2-launcher): tolerate vast JSON parse hiccups + auto-confirm destroy
e0a3102  fix(net2-launcher): positive-include tar instead of exclude blocklist
8bc5336  fix(net2-launcher): pipe offers JSON via stdin (ARG_MAX limit)
15bb8cf  fix(net2-launcher): retry vast offer search on transient empty responses
280d1f3  docs(net2-launcher): document one-time vast SSH key registration
08c4c83  fix(net2-launcher): correct vast offer filter field name
fadc4f3  docs: AWS quota appeal text + safety measures actually in place
33c2e56  fix(net2-trainer): warm-start path resets epoch counter for stage transitions
22dc638  fix(downloads): timeout EgoHands too (matches RHD pattern)
6a306d7  fix(net2-cache): skip missing source dirs instead of crashing
5efc37b  feat(s3-mirror): presigned URLs for fragile datasets + EgoHands converter
05b2944  fix(net2-trainer): disable persistent_workers + add fetch timeout
e8b0fd1  feat(net3): prebuild indices + smart interacting-hand filter
```

(Plus all the earlier session's commits prior to today.)

---

## 8. Active task list

```
#53  [in_progress] Net 2 v3.1 — training Stage B, ep 24/30, finishing in ~30 min
#55  [in_progress] Net 3 v1   — patched & training but epochs too long; pending samples_per_epoch cap
#57  [in_progress] Review-phase fix list — most items closed, see git history
#58  [pending]     Held-out eval on Net 1 v3.1 best.pt + per-split PCK bug
#59  [completed]   Net 3 prebuild indices + smart interacting-hand filter
```

Net 1's task #54 marked completed earlier today.

---

## 9. 20-min cron health check

A recurring cron job fires the health-check prompt every 20 min on
`7,27,47` minute marks. The cron is **session-scoped** — if the
Claude session restarts, recreate via `CronCreate`:

The prompt text the cron sends is preserved in `scripts/aws_presign_datasets.sh`-adjacent
(approximately — actual content is in the running cron). Format: SIX-column table with
`Net | Platform | Instance/App ID | Last epoch line | Epoch time | Cumulative spend this session`.

Key probes the cron runs:
```bash
# Vast
vastai show instances --raw | python3 -c "..."
# Modal
modal app list | grep -E "(running|deploying|ephemeral)"
# AWS instances
aws ec2 describe-instances --filters "Name=instance-state-name,Values=running,pending"
# Net 2 latest metric
ssh -p $PORT root@$HOST "tail -3 /workspace/asl/checkpoints/stage1_v3_detector_v3_1/stage_b/metrics.jsonl"
# Net 3 latest metric
ssh -p $PORT root@$HOST "tail -3 /workspace/asl/checkpoints/stage1_v3_landmark_v1/metrics.jsonl"
# Ledger
python3 -m scripts.cost_ledger --note "20m health check"
```

Rules in the cron:
- Rule 7: if a net's provider shows zero active and its task is in_progress → investigate + update TaskUpdate
- Rule 8: if any net hits its target (Net 1 PCK > 0.85, Net 2 AP > 0.40, Net 3 PCK > 0.80) → pull artifacts + report final
- Do NOT start new training in cron — just observe + report

---

## 10. Quick commands cheat sheet

```bash
# Check Net 2 metric
ssh -p 19626 root@ssh6.vast.ai 'tail -3 /workspace/asl/checkpoints/stage1_v3_detector_v3_1/stage_b/metrics.jsonl'

# Check Net 3 metric
ssh -p 34594 root@ssh1.vast.ai 'tail -3 /workspace/asl/checkpoints/stage1_v3_landmark_v1/metrics.jsonl'

# Pull Net 2 best.pt when done
mkdir -p results/v3/net2_v3_1
scp -P 19626 root@ssh6.vast.ai:/workspace/asl/checkpoints/stage1_v3_detector_v3_1/stage_b/best.pt results/v3/net2_v3_1/best.pt
scp -P 19626 root@ssh6.vast.ai:/workspace/asl/checkpoints/stage1_v3_detector_v3_1/stage_b/metrics.jsonl results/v3/net2_v3_1/

# Run held-out AP eval for Net 2
python3 -m scripts.eval_nets --net2 results/v3/net2_v3_1/best.pt --input-size 256 --use-fpn

# Update ledger
python3 -m scripts.cost_ledger --note "post Net 2 done"

# Destroy Net 2's Vast instance after artifact pull
export PATH=$HOME/.local/bin:$PATH; set -a; source .env.local; set +a
yes | vastai destroy instance 37489627

# Restart Net 3 with samples_per_epoch cap (PENDING — needs config patch)
# 1. Edit configs/stage1_v3_landmark_v1.yaml: add `train.samples_per_epoch: 250000`
# 2. Patch helpers.py to honor the cap in WeightedRandomSampler
# 3. scp + restart
```

---

## 11. User communication style — important

User preferences observed this session (preserve in any continuation):

- **Direct and decisive** — "go", "stop", "ride it" → take literally
- **Cost-conscious** — always tally spend, no surprises
- **Wants tight tables** over paragraphs for status reports
- **Asks sharp ML questions** — push back when reasoning is sloppy ("can't we clean that up ahead of time?"). They're not a deep ML practitioner but have strong engineering intuition that's often right; honor it.
- **Expects equivalent quality after dataset filtering** — "if you made decisions based on the size of the dataset, try to maintain those standards." Don't silently downgrade.
- **20-min cron updates are the heartbeat** — they re-engage every ~20 min via the cron firing; in between they're often AFK
- **"Don't reduce quality" is non-negotiable** — accept longer training rather than fewer epochs
- **Wants both context and decision** — present options with concrete cost/time and explicit recommendation
- **Likes when sub-issues are recovered cleanly** — recovering from a stall by restarting from `best.pt` rather than going back to scratch
- **Auto Mode active** — should make reasonable calls and keep going on continuation rather than asking permission for every step

---

## 12. Pending decisions awaiting user input

1. **Net 3 samples_per_epoch cap** — Option A from last turn (cap 250K + wire RHD). User hasn't confirmed yet. Without it, Net 3 = 100 hr.
2. **Net 2 v3.2 retry?** — user said no for now ("go with 3.1 as is")
3. **Wipe `asl-net3-vol` (Modal volume from prior round)?** — user hasn't said. Default: leave 1 week then delete.
4. **AWS quota appeal email reply** — user submitted appeal. Status `CASE_OPENED`. Watch for response in Inbox.

---

## 13. If you find yourself debugging after compaction

Common gotchas this session:
- **Net 3's `[data] interhand=1,361,062`** in the log is from the PRE-patch run. The patched run produces 1,432,581. If a log shows the smaller number, the patched adapter isn't being used (check `images_root` is being detected via the `InterHand2.6M_5fps_batch1` candidate).
- **tmux on Vast 5090 silently kills python processes** at ~ep 14 ~52% for Net 2's mix. **ALWAYS use nohup + disown for Net 2**. tmux is fine for Net 3.
- **Vast hosts can have stale Python cache** — `__pycache__/*.pyc` files can shadow source changes. After scp'ing patches, also `rm -rf __pycache__/` on remote.
- **Vast SSH host/port** can rotate between instance restarts (rare). Re-fetch from `vastai show instance <id> --raw`.
- **InterHand image_path access** — `e["image_path"]` in the smart index is a STRING starting with `InterHand2.6M_5fps_batch1/...`. The adapter joins to `self.root = data/interhand` → final path is `data/interhand/InterHand2.6M_5fps_batch1/images/...`.

---

## 14. Files added/modified today (in addition to commits)

New files:
- `docs/HANDOFF_V3_1.md` (this file)
- `docs/aws_quota_appeal.md`
- `scripts/prebuild_net3_indices.py`
- `scripts/convert_egohands_to_yolo.py`
- `scripts/aws_presign_datasets.sh`
- `scripts/cost_ledger.py`
- `modal_apps/train_net1_v3_1.py`
- `costs/ledger.csv` (auto-grown)

S3 buckets created:
- `asl-net3-data` (for Net 3 AWS launch if quota lands)
- `asl-pilot-datasets-027326806636` (dataset mirror)

---

End of handoff. Next step (per user direction): wait for their nod on the
Net 3 `samples_per_epoch` cap, then patch + restart Net 3. Meanwhile Net 2
finishes naturally in ~30 min.
