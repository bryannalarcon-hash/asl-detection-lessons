# GOAL_STATE — autonomous overnight run, 2026-05-24

User is asleep. This file is the resume-point if anything crashes again.
Read this first on session restore, then continue.

## The goal (user `/goal` directive, current)

1. **Finish Net 3** — run to full epoch (200) OR patience trigger. Patience
   is currently 999 (effectively never), so expect natural end at ep 200.
2. **Pull Net 3 artifacts** to `results/v3/net3_v1/` when done.
3. **Keep the Vast instance alive after Net 3 finishes** — Net 4 trains
   sequentially on the same 5090 instance (`37514594`, ssh1.vast.ai:34594).
4. **Stage 4 (Net 4) scaffolding done now** — committed (`f5a32dc`).
5. **Source Stage 4 data via swarms** — ASL Citizen primary (CC BY 4.0,
   direct download, 85 of 90 glosses, 3136 clips, on remote at
   `/workspace/asl/data/asl_citizen/ASL_Citizen/videos/`).
6. **Fill remaining 5 glosses** from WLASL via Kaggle per-file API:
   FIVE, TEN, TWENTY, NERVOUS, NICE_TO_MEET_YOU.
   Kaggle creds in `.env.local` as `KAGGLE_API`. Username
   `bryannalarcon`. Mirror: `risangbaskoro/wlasl-processed`. **Do not use
   `--unzip` locally — 5.2 GB unzip blew WSL memory once already.**
7. **Train Net 4 sequentially** on the Vast 5090 after Net 3 finishes
   (~3 hr at default HOyso config, 100 epochs).
8. **E2E smoke test** on held-out test split: `scripts/e2e_smoke_test.py`
   runs the full Net 1→2→3→4 pipeline on N test clips and prints top-1
   and top-3 accuracy.
9. **Pass criterion**: top-3 ≥ 0.5 on the smoke set (configurable).

## What's already done

| Step | State | Notes |
|---|---|---|
| 75-word catalog extracted | done | `data/signs/sign_list.json` |
| Bumped to 90-word catalog | done | +15 from directory schema (MEET, GRANDMOTHER, GRANDFATHER, LOVE, MILK, WEEK, BATHROOM, RESTAURANT, LEARN, READ, SEE, PURPLE, BROWN, RABBIT, GOOD) |
| Three research swarms run | done | ASL Citizen / license audit / mirrors all complete |
| ASL Citizen 42.8 GB zip | done | Downloaded to Vast remote |
| ASL Citizen splits CSV | done | `splits/{train,val,test}.csv` |
| Manifest built from splits | done | `/workspace/asl/data/signs/manifest.jsonl` on Vast — 3136 entries, 85/90 glosses, train 1493 / val 376 / test 1267 |
| Selective video extract | done | 2618 .mp4 files extracted, zip deleted to save disk |
| Net 4 model code | done | `src/stage2/models/sign_classifier.py` — hoyso48 1.0M params |
| Net 4 dataset code | done | `src/stage2/data/sign_dataset.py` — 343-dim per-frame features |
| Keypoint extractor | done | `src/stage2/data/extract_keypoints.py` — runs Nets 1+2+3, writes .npz |
| Manifest builder | done | `src/stage2/data/build_manifest.py` — alias map for BYE/THANKYOU/WELCOME/SHOP/AGAIN |
| Net 4 trainer | done | `src/stage2/train_v4_classifier.py` — BF16, EMA, cosine LR, top-1/3 |
| Net 4 config | done | `configs/stage2_v4_classifier.yaml` |
| Net 4 predict_clip | done | `src/stage2/predict_clip.py` — single-clip e2e |
| E2E smoke script | done | `scripts/e2e_smoke_test.py` |
| Net 1+2 ckpts on Vast | done | `/workspace/asl/results/v3/{net1_v3_1,net2_v3_1}/best.pt` |
| Net 4 code on Vast | done | All files scp'd |
| Smoke extraction on 3 clips | done | CPU, verified .npz schema + dataset loader works |

## Remaining steps in order

### Step A — Fill 5 missing glosses (now)
1. Local: parse `data/wlasl/WLASL_v0.3.json` (660 KB, safe).
2. Identify video IDs for FIVE, TEN, TWENTY, NERVOUS.
   (NICE_TO_MEET_YOU likely absent — accept the 1 gap.)
3. Per-file download via Kaggle API:
   `kaggle datasets download -d risangbaskoro/wlasl-processed -f videos/00XXX.mp4`
   for each ID. ~10-20 videos per gloss × 4 = 50-80 files, ~50 MB total.
4. scp to `/workspace/asl/data/wlasl/videos/` on Vast.
5. Rebuild manifest: extend `build_manifest.py` to also scan WLASL.

### Step B — Wait for Net 3 (long, passive)
- Cron `95e82264` fires every 20 min on `:7, :27, :47`.
- Check val_pck monotonic, train_loss decreasing.
- Net 3 finishes (ep 200) → trainer drops `best.pt`/`last.pt` and exits.

### Step C — When Net 3 finishes
1. SCP `best.pt`, `last.pt`, `metrics.jsonl` to local `results/v3/net3_v1/`.
2. Do NOT destroy the instance — keep alive for Net 4 (per user direction).
3. Pull-eval-destroy memory rule: skip the destroy because Net 4 follows.

### Step D — Extract keypoints for all clips
Run on Vast 5090 with all three frozen nets:
```
python -u -m src.stage2.data.extract_keypoints \
  --manifest /workspace/asl/data/signs/manifest.jsonl \
  --net1 /workspace/asl/results/v3/net1_v3_1/best.pt \
  --net2 /workspace/asl/results/v3/net2_v3_1/best.pt \
  --net3 /workspace/asl/checkpoints/stage1_v3_landmark_v1/best.pt \
  --out /workspace/asl/data/signs/kpt_cache \
  --device cuda
```
~3136 clips × ~1 sec/clip on GPU = ~1 hr. .npz per clip ~50-200 KB each.

### Step E — Train Net 4
```
python -u -m src.stage2.train_v4_classifier \
  --config /workspace/asl/configs/stage2_v4_classifier.yaml
```
100 epochs, batch 128, cosine LR. ~3 hr on 5090. Saves
`/workspace/asl/checkpoints/stage2_v4_classifier_v1/best.pt`.

### Step F — E2E smoke
1. Pull Net 4 best.pt to local.
2. Pick 30 random test-split clips.
3. Run `scripts/e2e_smoke_test.py` with all 4 net checkpoints.
4. Report top-1 / top-3 accuracy.

### Step G — Wrap up
1. Pull final results.
2. Destroy Vast instance `37514594`.
3. Update docs/handoffs/HANDOFF_V3_1.md with all results.
4. Final commit + push.

## Memory safety rules

- WSL has 7.6 GB RAM + 2 GB swap. Local `--unzip` of a 5.2 GB zip crashes it.
- Always check `free -h` before heavy local ops.
- Use per-file Kaggle API, not bulk `--unzip`.
- Stream extraction (zipfile + write each file then close).
- Net 3 / Net 4 training runs on the remote — no local memory pressure.

## Cron job (must remain alive)

`95e82264 — 7,27,47 * * * *` — session-only. If session restarts, recreate
via `CronCreate` with the same 20-min health check prompt from
docs/handoffs/HANDOFF_V3_1.md section 9.

## Files of interest

- `data/signs/sign_list.json` — 90-word catalog
- `data/signs/manifest.jsonl` — on local (stale, 75 only). The
  authoritative manifest is on Vast at
  `/workspace/asl/data/signs/manifest.jsonl` (90 glosses, 3136 entries).
- `data/wlasl/WLASL_v0.3.json` — local, 660 KB
- `data/asl_citizen/` — local empty (everything is on Vast)
- `results/v3/{net1_v3_1,net2_v3_1}/best.pt` — local + Vast
- `results/v3/net3_v1/` — local empty, will populate when Net 3 finishes
- `results/v4/` — local empty, will populate when Net 4 finishes
