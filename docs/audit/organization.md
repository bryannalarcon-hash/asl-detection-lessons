# Codebase Organization Audit

REPORT ONLY. No files were moved, renamed, edited, or deleted. This proposes a
target layout and rates every move for path-reference safety. A verification
swarm must confirm import/path safety before anything is acted on.

Scope excluded from any move (gitignored, do not touch): `results/`, `data/`,
`node_modules/`, `design/`, `playground/`, `.venv-demo/`, `costs/`, `logs/`,
`screenshots/`, `test-results/`, `ruvector.db`, `ASL_Citizen.zip`, `.env*`.

---

## 1. Current-state summary

**Tracked top-level dirs:** `backend/ configs/ design/ docs/ frontend/
modal_apps/ scripts/ src/ tests/ tools/` plus root config files.

**Root clutter — most is already gitignored.** `git check-ignore` confirms
`screenshots/`, `test-results/`, `logs/`, `costs/`, `results/`, `data/`,
`playground/`, `.venv-demo/`, `ASL_Citizen.zip`, `ruvector.db`, `.env`,
`.env.local`, and `.scaffold-phase*-report.md` are all already ignored. They
sit in the working tree but are not committed, so they are cosmetic clutter,
not repo-hygiene problems.

The only **tracked** root files that arguably do not belong at root:
- `.scaffold-final-report.md` (11 KB scaffold-era artifact; note the *phase*
  reports `.scaffold-phase*-report.md` are gitignored but the *final* one is
  tracked — inconsistent)
- `google_iso_1st_place.md` (8 KB competition writeup / reference notes)
- `superbuilders-partner-project-asl-learning-with-computer-vision.pdf`
  (210 KB partner brief)

Everything else at root is legitimately root-level: `package.json`,
`package-lock.json`, `tsconfig.base.json`, `playwright.config.ts`,
`docker-compose.yml`, `requirements.txt`, `.nvmrc`, `.mcp.json`, `.env.example`,
`README.md`, `CLAUDE.md`, `GITLAB.md`.

**`scripts/` (62 entries)** is flat. It mixes seven distinct concerns:
provisioning/orchestration (runpod + aws), dataset download/extraction,
training launchers, benchmarking/profiling, eval, plotting, db/seed, and
node-side screenshot tools. **Critically, 26 of these scripts are invoked by
hardcoded `scripts/<name>` paths in 44 call sites** — mostly from remote
orchestration that does `cd /workspace/asl && bash scripts/_remote_train.sh`.
These paths must exist verbatim on a freshly-cloned pod. Moving such a script
into a subfolder silently breaks the training pipeline.

**`docs/` (55 files)** is mostly coherent: `handoffs/` (+ `handoffs/archive/`),
`research/`, `competitive/`, `optimization-attempts/`, `superbuilders/`,
`audit/` (this dir) all exist and group well. The weakness is **15 loose
top-level docs** that mix evergreen reference (principles, ux-spec, ml-handoff),
ML/training docs, and stale status reports.

**`src/`** (Python CV) has a clean `common/ stage1/ stage2/` split with
`data/ models/ augment/` subpackages. Sound. `tools/onnx_export/` and
`modal_apps/` are correctly separate from `src/`.

**`frontend/src/cv/`** mirrors the Python pipeline as a TS port with
`ort/ pipeline/` and `evaluate.{ts,mock,real}` boundary. Sound.

---

## 2. Proposed target tree

The dominant constraint is that `scripts/` and `configs/` are referenced by
flat relative paths from the remote pipeline. The proposal is therefore
**phased and conservative**: reorganize the things with few/no code references
first; leave the orchestration-coupled scripts and configs **flat** unless the
user wants to absorb a coordinated path-update pass.

```
asl-learning/
├── README.md  CLAUDE.md  GITLAB.md            # keep
├── package.json  package-lock.json  tsconfig.base.json
├── playwright.config.ts  docker-compose.yml  requirements.txt
├── .nvmrc  .mcp.json  .env.example
│
├── backend/                                   # unchanged
├── frontend/                                  # unchanged (cv/ layout is good)
├── src/                                        # unchanged (stage1/stage2 good)
├── tools/onnx_export/                          # unchanged
├── modal_apps/                                 # unchanged
├── configs/                                    # LEAVE FLAT (see risk note)
│
├── scripts/
│   │   # PHASE 1 (safe): move only scripts NOT invoked by scripts/<name> paths
│   ├── plot/            # plot_*.py, profile/bench helpers consumed by humans
│   ├── node/            # seed-dev-user.ts, screenshot-*.ts  (TS, ref'd by package.json/GITLAB.md only)
│   │
│   │   # PHASE 2 (needs coordinated path update): orchestration + data + train
│   ├── runpod/          # runpod_provision.py, launch_*.sh, _remote_*.sh, round_health.sh, destroy_instance.py
│   ├── aws/             # aws_launch_net3.sh, aws_pull_net3.sh, aws_presign_datasets.sh
│   ├── data/            # download_*.sh, *_reorganize.py, convert_*, build_*_cache.py, prebuild_*, split_train_val.py
│   ├── train/           # launch_v3*.sh, run_*_on_remote.sh, ca_v2_orchestrate.sh, nj_orchestrate.sh
│   └── eval/            # eval_*.py, *_smoke*.py, verify_*, check_*, mirror_net3_local.sh
│
├── docs/
│   ├── README.md (index)                       # add a top-level index (optional)
│   ├── handoffs/        + archive/              # unchanged (good)
│   ├── research/  competitive/  superbuilders/  # unchanged (good)
│   ├── optimization-attempts/                   # unchanged (good)
│   ├── audit/                                    # this report
│   ├── reference/       # principles.md, ux-spec.md, ml-handoff.md, hoyso-architecture.md,
│   │                    #   prd-scaffold.md, local-setup.md, PRIVACY.md
│   ├── ml/              # DATASET_AND_TRAINING.md, training-plan.md, v3-plan.md,
│   │                    #   WEBGPU_PORT_PLAN.md, aws_quota_appeal.md
│   └── status/          # GOAL_STATE.md, SWARM_FINDINGS.md, VALIDATION_REPORT.md
│
└── docs/reference/google_iso_1st_place.md       # moved in from root
    docs/superbuilders/partner-brief.pdf         # moved in from root
    (drop or archive .scaffold-final-report.md — phase reports already gitignored)
```

---

## 3. Proposed moves

References were grepped across the repo excluding `node_modules .git data
results .venv-demo`. "Code refs" = `.sh/.py/.ts/.json` that invoke the path
(breaks at runtime). "Doc refs" = `.md` mentions (stale text, not runtime).

| # | From | To | Reason | References to update | Risk |
|---|------|-----|--------|----------------------|------|
| R1 | `google_iso_1st_place.md` (root) | `docs/reference/google_iso_1st_place.md` | Reference notes belong in docs | doc mentions: GITLAB.md, docs/superbuilders/portfolio.md, docs/handoffs/archive/HANDOFF_STAGE1.md, docs/prd-scaffold.md, docs/handoffs/HANDOFF_FRONTEND.md (text only, no code) | **LOW** |
| R2 | `superbuilders-partner-project-...with-computer-vision.pdf` (root) | `docs/superbuilders/partner-brief.pdf` | Partner brief belongs with superbuilders docs | doc mentions only (GITLAB.md, prd-scaffold.md, HANDOFF_FRONTEND.md); no code reads it | **LOW** |
| R3 | `.scaffold-final-report.md` (root, tracked) | `docs/status/` or untrack | Scaffold artifact; sibling `.scaffold-phase*-report.md` already gitignored — inconsistent that this one is tracked | refs: .scaffold-final-report.md self, plus seed-dev-user mention; no code reads it | **LOW** |
| D1 | `docs/principles.md`, `ux-spec.md`, `ml-handoff.md`, `hoyso-architecture.md`, `prd-scaffold.md`, `local-setup.md`, `PRIVACY.md` | `docs/reference/` | Group evergreen reference docs | CLAUDE.md "Pointers" section names `docs/principles.md`, `docs/ux-spec.md`, `docs/ml-handoff.md`, `docs/prd-scaffold.md`; cross-doc links | **MED** (CLAUDE.md pointer block + internal doc links must update) |
| D2 | `docs/DATASET_AND_TRAINING.md`, `training-plan.md`, `v3-plan.md`, `WEBGPU_PORT_PLAN.md`, `aws_quota_appeal.md` | `docs/ml/` | Group ML/training planning docs | cross-doc links in handoffs; no code | **MED** (doc links only) |
| D3 | `docs/GOAL_STATE.md`, `SWARM_FINDINGS.md`, `VALIDATION_REPORT.md` | `docs/status/` | Separate point-in-time status from evergreen | cross-doc links; no code | **LOW** |
| S1 | `scripts/plot_*.py` (plot_dataset_mixes, plot_net3_aws_options, plot_net3_gpu_options, plot_training) | `scripts/plot/` | Plotting helpers, run by humans ad-hoc | none invoke via `scripts/plot_*`; only doc mentions (optimization-attempts) | **LOW** |
| S2 | `scripts/screenshot-all-pages.ts`, `screenshot-superbuilders.ts` | `scripts/node/` | Node/TS tooling, distinct from Python CV scripts | GITLAB.md mentions only; no package.json script entry | **LOW** |
| S3 | `scripts/seed-dev-user.ts` | `scripts/node/` | Group with other node tooling | **package.json** `db:seed` runs `tsx scripts/seed-dev-user.ts`; refs in ux-spec.md, HANDOFF_*; frontend tests reference dev-credentials not this path | **MED** (one package.json line + docs) |
| S4 | `scripts/aws_*.sh` (3) | `scripts/aws/` | Group AWS provisioning | `aws_presign_datasets.sh` invoked by `launch_train_pod.sh` via `scripts/aws_presign_datasets.sh`; doc mentions | **MED** (1 code caller + docs) |
| S5 | `scripts/download_*.sh`, `hagrid_reorganize.py`, `convert_egohands_to_yolo.py`, `build_*_cache.py`, `prebuild_*`, `split_train_val.py`, `preprocess_cache.py`, `add_test_splits.py`, `check_data.py` | `scripts/data/` | Group dataset prep | **HIGH coupling**: `download_v3_data.sh` is invoked by `_remote_train.sh` as `scripts/download_v3_data.sh`; it in turn calls `$SCRIPT_DIR/download_egohands.sh` etc (sibling-relative, survives if moved together) AND `scripts/split_train_val.py`, `scripts/hagrid_reorganize.py` (root-relative, breaks). modal_apps call `scripts/preprocess_cache.py`, `scripts/split_train_val.py` | **HIGH** |
| S6 | `scripts/runpod_provision.py`, `launch_train_pod.sh`, `launch_phase_c.sh`, `launch_eval_net2.sh`, `_remote_*.sh`, `round_health.sh`, `destroy_instance.py` | `scripts/runpod/` | Group the runpod orchestration chain | **HIGH coupling**: `launch_*` call `python3 scripts/runpod_provision.py` and `setsid bash scripts/_remote_*.sh` after `cd /workspace/asl`; `round_health.sh` referenced by docs+launchers; `.round_env` writer | **HIGH** |
| S7 | `scripts/launch_v3*.sh`, `run_v3_on_remote.sh`, `ca_v2_orchestrate.sh`, `nj_orchestrate.sh`, `run_net4_after_net3.sh` | `scripts/train/` | Group training launchers | `launch_v3.sh` referenced by 6 files; `ca_v2_orchestrate.sh`/`nj_orchestrate.sh` call `scripts/preprocess_cache.py`, `scripts/split_train_val.py` (root-relative) | **HIGH** |
| S8 | `scripts/eval_*.py`, `smoke_test*.py`, `e2e_smoke_test.py`, `verify_numba_anchors.py`, `bench_*.{py,sh}`, `profile_*`, `mirror_net3_local.sh`, `cost_ledger.py`, `precompute_boxes.py`, `predict_bboxes_for_phase2.py`, `strip_checkpoint.py`, `build_clip_manifest.py`, `grab_lesson_videos.py`, `eval_net4_verifier.py` | `scripts/eval/` | Group eval/bench | `eval_net2_ap.py`, `strip_checkpoint.py`, `build_clip_manifest.py`, `eval_net4_verifier.py`, `smoke_test*.py` are invoked via `scripts/<name>` from `_remote_*.sh`/`launch_v3*.sh` | **HIGH** |
| C1 | `configs/*.yaml`, `configs/*.json` | (leave flat) | Could split `configs/stage1/`, `configs/stage2/`, `configs/ablations/` | **HIGH coupling**: every config is referenced as `configs/<name>.yaml` from scripts, modal_apps, src; 16+ flat references | **HIGH — recommend NOT moving** |

---

## 4. src/ and frontend/src/cv assessment

**`src/` (Python CV) — sound, no moves proposed.**
`common/` (config, seed, v3_config) + `stage1/` (keypoints/palm/landmarks:
`data/ models/ augment/ losses* metrics eval* train*`) + `stage2/` (sign
classifier + verifier). The stage1/stage2 split matches the 4-net pipeline
(stage1 = nets 1–3 hand/keypoint, stage2 = net 4 sign classifier). The only
cosmetic note: `stage1/` carries parallel `_v2`/`_v3` versioned modules
(`train.py`, `train_v2.py`, `train_v3_detector.py`, `losses.py`, `losses_v3.py`)
— this is version sprawl, not misplacement. Do not rename; live training
configs reference these by import path.

**`frontend/src/cv/` — sound, no moves proposed.**
`evaluate.{ts,mock,real}` is the swappable boundary (matches the
`feedback_explicit_dev_scaffolding` mock-override preference), `ort/`
(session+models) is the ONNX runtime layer, `pipeline/` (anchors, features,
geom, stage1, stage2, verifier) is the TS port of `src/`. Clean mirror of the
Python side. `geom.spec.ts` colocated with `geom.ts` is fine.

**`tools/onnx_export/` and `modal_apps/`** — correctly separate from `src/`.
`modal_apps/*.py` call `scripts/<name>` and `configs/<name>` by repo-root
path, reinforcing the flat-path coupling constraint.

---

## 5. Naming inconsistencies (noted, no risky renames proposed)

- **`results/v1`, `v1_resumed`, `v2`, `v3`, `v4`** vs configs named
  `stage1_v2`, `stage1_v3_detector`, `stage1_v3_landmark_v1`, `_v3_1`,
  `_facebody_v3_1`. The "v3" axis in `results/` (training round) is a different
  axis from "v1/v2/v3" in config names (model architecture revision). They
  collide semantically. `results/` is gitignored — leave it.
- **`net2_v3_1` / `net1_v3_1` / `net3_v2`** under `results/v3/` — the per-net
  revision suffix is inconsistent (`_v3_1` vs `_v2`). Cosmetic; gitignored.
- **`.scaffold-final-report.md` tracked while `.scaffold-phase*-report.md`
  gitignored** — inconsistent gitignore treatment of the same artifact family
  (see R3).
- **Script prefix conventions are actually decent**: `_remote_*` = runs on the
  pod (private), `launch_*` = local entrypoint, `download_*`/`build_*`/`eval_*`/
  `plot_*`/`bench_*` = verb-grouped. These prefixes already encode the grouping
  the subfolders would make explicit — which is the argument for *either*
  subfoldering *or* leaving flat, but not renaming.
- **`scripts/db/`** subfolder already exists (the only one) — a precedent that
  subfoldering scripts is acceptable here.

---

## 6. Safe-to-do-now vs needs-care split

### Safe to do now (LOW risk — doc-only or single-known-caller references)

- **R1** move `google_iso_1st_place.md` -> `docs/reference/`
- **R2** move the partner-brief PDF -> `docs/superbuilders/partner-brief.pdf`
- **R3** untrack or move `.scaffold-final-report.md` (align with its gitignored siblings)
- **D3** group `GOAL_STATE.md`, `SWARM_FINDINGS.md`, `VALIDATION_REPORT.md` -> `docs/status/`
- **S1** move `plot_*.py` -> `scripts/plot/` (no code invokes them by path)
- **S2** move `screenshot-*.ts` -> `scripts/node/` (no package.json entry; GITLAB.md text only)

All LOW-risk moves touch only `.md` text references and one `.png`-producing TS
pair. After each, grep the named doc/GITLAB.md mentions and update text. No
runtime path breaks.

### Needs care (MED — coordinated single-file update)

- **D1 / D2** docs regrouping into `docs/reference/` and `docs/ml/` — must
  update the **CLAUDE.md "Pointers" block** (names `docs/principles.md`,
  `docs/ux-spec.md`, `docs/ml-handoff.md`, `docs/prd-scaffold.md`) plus
  inter-doc links. Mechanical but must be done atomically.
- **S3** `seed-dev-user.ts` -> `scripts/node/` — update **package.json**
  `db:seed` script in the same commit, plus doc mentions.
- **S4** `aws_*.sh` -> `scripts/aws/` — update the one caller
  (`launch_train_pod.sh` invokes `scripts/aws_presign_datasets.sh`).

### Needs care (HIGH — breaks the remote training pipeline without a coordinated path-update pass)

- **S5 / S6 / S7 / S8** the data/runpod/train/eval script subfoldering. **26
  scripts are invoked by hardcoded `scripts/<name>` paths in 44 call sites**,
  mostly after `cd /workspace/asl` on a rented pod. Moving any of them requires
  updating every `python3 scripts/<name>` / `bash scripts/<name>` /
  `setsid bash scripts/<name>` call site in `_remote_*.sh`, `launch_*.sh`,
  `*_orchestrate.sh`, and `modal_apps/*.py`, **and** the scripts must be
  re-pushed to GitLab before the next pod clone or training silently fails.
  Recommend doing these only as one deliberate, swarm-verified pass, not
  piecemeal. `download_v3_data.sh`'s `$SCRIPT_DIR`-relative sibling calls
  survive a move-together, but its root-relative `scripts/split_train_val.py` /
  `scripts/hagrid_reorganize.py` calls do not.
- **C1** `configs/` subfoldering — **recommend NOT doing.** Every config is a
  flat `configs/<name>.yaml` reference from scripts, modal_apps, and src; the
  ratio of churn to benefit is poor and the break is silent (training starts,
  then can't find its config).

### Recommended sequencing

1. Land R1, R2, R3, D3, S1, S2 (LOW) in one cleanup commit — purely
   cosmetic, no runtime risk.
2. Land D1, D2, S3, S4 (MED) in a second commit, each with its single
   coupled file (CLAUDE.md / package.json / launch_train_pod.sh) updated in
   the same diff.
3. Defer S5–S8 (HIGH) to a dedicated, verification-swarm-gated change that
   updates all 44 call sites + re-pushes to GitLab before the next training
   round. Leave `configs/` (C1) flat indefinitely.
