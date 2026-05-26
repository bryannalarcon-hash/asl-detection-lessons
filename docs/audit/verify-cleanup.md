# Cleanup verification pass (REPORT ONLY — independent re-grep)

Independent fact-check of `docs/audit/cleanup-candidates.md`. Every flag was
re-verified with fresh greps across the whole repo (imports, `.sh`, configs,
`package.json`, `playwright.config.ts`, docs, modal_apps, tests). **Nothing was
deleted, moved, or edited.** Conservative bias: a single live reference → REJECT.

Verdict key: **CONFIRMED-SAFE** (independently verified no live ref) /
**REJECTED** (found a live ref, cited) / **NEEDS-USER-DECISION** (judgement call).

The LIVE remote-training pipeline at fact-check time:
`launch_train_pod.sh` → `_remote_train.sh` (runs `train_v3_detector` for net2,
`train_v3_landmark_reg` for net3) and `launch_net2_v3_1.sh` (inline
`_remote_net2_v3_1.sh`, runs `train_v3_detector`). Both ship the
`src configs scripts modal_apps tests requirements.txt` tarball to the pod.

---

## 1. DELETE candidates

| Item | Prior flag | Verdict | Evidence | Note |
|---|---|---|---|---|
| `src/stage2/data/build_manifest.py` | delete (high) | **CONFIRMED-SAFE** | Whole-repo grep `build_manifest\b` (excl popsign): only hits are the file itself, `docs/GOAL_STATE.md:43,62` (itself a stale-doc candidate), and the summary line. The two test fns `test_build_manifest_*` in `tests/test_pipeline_integration.py:369,393` invoke `src.stage2.data.build_manifest_popsign` (lines 379, 399), **not** this file — the name match is coincidental. `git ls-files` confirms tracked. | Only ref is the stale `GOAL_STATE.md`. Net 4 round uses `build_manifest_popsign`. Safe. |
| `frontend/src/components/ui/badge.tsx` | delete (high) | **CONFIRMED-SAFE** | `grep -rn badge\|Badge frontend/src`: only self-refs in `badge.tsx` + one prose comment `MasteryBar.tsx:7` ("course-progress badge"). No `import`. Whole-repo `components/ui/badge` path grep: none outside the file. `git ls-files` tracked. | No importer anywhere. |
| `frontend/src/components/ui/tabs.tsx` | delete (high) | **CONFIRMED-SAFE** | `grep -rni ui/tabs\|Tabs frontend/src`: only self-refs in `tabs.tsx` + prose comments `Practice.tsx:353` ("pill tabs"), `DrillIndicator.tsx:18`. No `import`, no `Tabs`/`TabsList` JSX usage. `git ls-files` tracked. | No importer. |
| `src/stage1/train.py` (v1 trainer) | retire-as-one (med) | **NEEDS-USER-DECISION** | `src.stage1.train` invoked only by `scripts/nj_orchestrate.sh:16` + `scripts/launch_training.sh:43,51` — both themselves orphan launchers (no external invoker; see §3). No config/test/modal ref. | Dead only via dead launchers. Safe to retire **as a set** with both orchestrators. Not in the live pipeline. |
| `src/stage1/train_v2.py` (v2 trainer) | retire-as-one (med) | **NEEDS-USER-DECISION** | `src.stage1.train_v2\b` (not facebody) invoked only by `ca_v2_orchestrate.sh:30` + `nj_orchestrate.sh:30` — both orphan launchers. No config/test/modal ref. | Same as above; retire with the orphan orchestrators. No v2 retrain is queued (HANDOFF_MEDIAPIPE_GAP §5 Net 2 retrain uses `train_v3_detector`). |
| `src/stage1/train_v2_facebody.py` (Net 1 trainer) | retire-as-one (med) | **REJECTED** | LIVE Net 1 trainer. Invoked by `modal_apps/train_net1.py:157` **and** `modal_apps/train_net1_v3_1.py:128` (`python -m src.stage1.train_v2_facebody`). The **current** handoff `docs/handoffs/HANDOFF_MEDIAPIPE_GAP.md:87` names `modal_apps/train_net1_v3_1.py` as the live Net 1 `best.pt` source (open action item). Also `docs/DATASET_AND_TRAINING.md:154`. | Net 1 has no v3 trainer — it still trains via `train_v2_facebody`. Do NOT delete. |
| `src/stage1/augment/transforms.py` | delete-with-v1/v2 (med) | **REJECTED** | Imported by `src/stage1/data/cached.py:14` (`apply_transform`), `src/stage1/data/unified.py:18`, `eval.py:23,112`, `train.py:24`. `cached.py` is imported by the LIVE `train_v2_facebody.py:30` (`CachedKeypointDataset, gpu_render_heatmaps`). Transitively live. | Reachable from the live Net 1 trainer via `cached.py`. Do NOT delete. |
| `src/stage1/augment/transforms_v2.py` | delete-with-v1/v2 (med) | **REJECTED** | Imported directly by the LIVE `src/stage1/train_v2_facebody.py:28` (`build_train_transform_v2, build_val_transform_v2`). Also `train_v2.py:27`. | Directly imported by the live Net 1 trainer. Do NOT delete. |
| `src/stage1/losses.py` | delete-with-v1/v2 (med) | **REJECTED** | Imported by the LIVE `src/stage1/train_v2_facebody.py:31` (`HeatmapMSELoss`). Also `train.py:25`, `train_v2.py:30`, `eval.py:27`, `scripts/smoke_test.py:24`. | Directly imported by the live Net 1 trainer. Do NOT delete. |
| `src/stage1/train_v3_landmark.py` (heatmap Net 3 trainer) | keep-pending (low) | **NEEDS-USER-DECISION** | Still wired: `launch_v3.sh:72,81`, `aws_launch_net3.sh:241`, `modal_apps/train_net3.py:169,234`, `scripts/bench_model_ceiling.py:113`. Current `_remote_train.sh:63` uses `train_v3_landmark_reg` instead. `extract_keypoints.load_net3` (line 154) supports both heads but imports the **model** `HandLandmarkNet` from `landmark_net.py`, not this trainer. | Heatmap path retired from the live remote run but trainer still referenced by older launchers. Keep (report agrees). SPLIT candidate, not delete. |
| `modal_apps/train_net1.py` | keep-pending / retire Modal (low) | **NEEDS-USER-DECISION** | Referenced only by orphan `scripts/check_dual_status.sh:29` (`modal run modal_apps/train_net1.py::status`) + archived handoffs. Invokes the live `train_v2_facebody`. | Modal appears superseded by runpod/vast SSH pods, but this app is the documented Net 1 origin (v3.1 resumes from its `best.pt`, see `train_net1_v3_1.py:122`). Retire only if Modal is fully abandoned. |
| `modal_apps/train_net1_v3_1.py` | keep-pending / retire Modal (low) | **REJECTED** (as a delete) | Named by the **current** `HANDOFF_MEDIAPIPE_GAP.md:87` as the live Net 1 `best.pt` source. Shipped in the live launchers' tarballs (`launch_net2_v3_1.sh:162`, `launch_train_pod.sh:74`). | Current-round Net 1 trainer. Do NOT delete. |

---

## 2. UNTRACK candidate

| Item | Prior flag | Verdict | Evidence | Note |
|---|---|---|---|---|
| `.scaffold-final-report.md` | gitignore-and-untrack (high) | **CONFIRMED-SAFE** (to untrack) | `git ls-files \| grep scaffold` → only `.scaffold-final-report.md` + `docs/prd-scaffold.md`. Siblings `.scaffold-phase1/2a/2b/3-report.md` exist on disk **untracked** (gitignored). `.gitignore:54` = `.scaffold-phase*-report.md`; **also** `.gitignore:305` `/*.md` (whitelist README/CLAUDE/GITLAB) already covers it — so it is gitignored-but-tracked (committed before the rule). | Untracking is consistent with siblings. Caveat: `HANDOFF_FRONTEND.md:61` references it by name as a baseline, so keep the file on disk; only `git rm --cached`. The report's "phase glob misses final" reasoning is slightly off (the `/*.md` rule is the real cover), but the untrack action is correct. |

---

## 3. RELOCATE candidates

| Item | Prior flag | Verdict | Evidence | Note |
|---|---|---|---|---|
| `google_iso_1st_place.md` | relocate to docs/research/ (high) | **CONFIRMED-SAFE** | `grep -rn google_iso_1st_place`: only doc-**text** refs — `GITLAB.md:316` (gitignore-rules listing), `HANDOFF_STAGE1.md:112` (archived tree diagram), `organization.md` (sibling audit), `prd-scaffold.md`. No code/script/config reads it by path. `git ls-files` tracked. | Relocate is safe. Moving will leave the `GITLAB.md:316` / archived-handoff text stale (cosmetic), and flips its ignore status (currently matched by `/*.md`). |
| `superbuilders-...computer-vision.pdf` | relocate to docs/ or untrack (high) | **CONFIRMED-SAFE** | `grep -rn superbuilders-partner-project`: doc-text only — `GITLAB.md:317`, `prd-scaffold.md:78`, `superbuilders/portfolio.md:127`, `HANDOFF_STAGE1.md:12`. No code reads it. `git ls-files` tracked. | Relocate safe; same cosmetic doc-staleness caveat. Small (210 KB), low urgency. |

---

## 4. SPLIT candidates (NOT deletions — confirm line counts + boundary symbols)

| Item | Prior flag | Verdict | Evidence | Note |
|---|---|---|---|---|
| `src/stage1/data/dali_pipelines.py` | split @ 910 (high) | **CONFIRMED** | `wc -l` = **910**. `class DALIDetectorLoader` @87, `class DALILandmarkLoader` @722, helpers `_normalize_bbox_to_input`@45, `_build_landmark_affine`@58, `_read_jpeg_with_dims`@71 all exist. | Boundaries real and clean. |
| `src/stage2/data/extract_keypoints.py` | split @ 671 (high) | **CONFIRMED** | `wc -l` = **671**. All named fns exist: `load_net1`@91/`run_net1`@225/`_decode_box_kpts`@267; `load_net2`@107/`run_net2`@301/`_expand_box`@362; `load_net3`@154/`run_net3`@398/`_net3_one_pass`@374; orchestrators `iter_video_frames`@201/`assign_hand_side`@445/`extract_one_clip`@479/`process_one`@517/`main`@564. | Per-net split boundaries real. |
| `src/stage1/models/anchors.py` | split @ 592 (high) | **CONFIRMED** | `wc -l` = **592**. `build_targets_gpu`@355, `build_targets_gpu_batched`@448 exist (the "kept off" GPU matchers); core `encode_box`@191/`decode_box`@200/`encode_kpts`@209/`decode_kpts`@231/`match_anchors_to_gt`@297/`nms`@324 stay. | Boundaries real. |
| `src/stage1/train_v3_detector.py` | split @ 584 (med) | **CONFIRMED** (line count) | `wc -l` = **584**. | LIVE trainer (`_remote_train.sh`, `launch_net2_v3_1.sh`). Split is fine; touch with care since it is in the active pipeline. |
| `src/stage1/train_v3_landmark.py` | split @ 535 (low; "moot if heatmap retired") | **CONFIRMED** (line count) | `wc -l` = **535**. Helper sibling `train_v3_landmark_helpers.py` exists (per report). | Heatmap trainer; still referenced (see §1 row). Split low-priority. |
| `frontend/src/pages/Practice.tsx` | split @ 502 (high) | **CONFIRMED** (line count) | `wc -l` = **502** (just over the 500 limit). | Helper-extraction split is reasonable; named helpers to be confirmed at edit time. |

---

## 5. Lower-confidence orphans (re-verified)

| Item | Prior flag | Verdict | Evidence | Note |
|---|---|---|---|---|
| `scripts/bench_callback.py` | delete/archive (med) | **CONFIRMED-SAFE** | No external ref (only self). Tracked. | One-off bench from closed optimization round. |
| `scripts/bench_callback_breakdown.py` | delete/archive (med) | **CONFIRMED-SAFE** | No external ref. Tracked. | Same closed round. |
| `scripts/plot_dataset_mixes.py` | keep-pending (med) | **CONFIRMED-SAFE** | No ref. **Untracked** (matches `git status`). | One-off chart gen; not wired. |
| `scripts/plot_net3_aws_options.py` | keep-pending (med) | **CONFIRMED-SAFE** | No ref. Untracked. | One-off cost plot. |
| `scripts/plot_net3_gpu_options.py` | keep-pending (med) | **CONFIRMED-SAFE** | No ref. Untracked. | One-off cost plot. |
| `scripts/precompute_boxes.py` | keep-pending (low) | **NEEDS-USER-DECISION** | No external invoker of the **script**. The grep hits (`dali_pipelines.py:180,385`) are the unrelated `_precompute_boxes` **method** on `DALIDetectorLoader`. | Hand-run prep wrapping a live method. Keep until confirmed no Net 2 cache prep needs it. |
| `scripts/ca_v2_orchestrate.sh` | keep-pending (med) | **NEEDS-USER-DECISION** | No external ref; only calls `train_v2`. | Retire with the v2 trainer set. |
| `scripts/nj_orchestrate.sh` | keep-pending (med) | **NEEDS-USER-DECISION** | No external ref; calls `train` + `train_v2`. | Retire with the v1/v2 set. |
| `scripts/launch_training.sh` | keep-pending (med) | **NEEDS-USER-DECISION** | No external ref; calls `train` (v1). Superseded by `launch_v3.sh`. | Retire with v1. |
| `scripts/launch_v3_net2_only.sh` | keep-pending (low) | **NEEDS-USER-DECISION** | No external ref; calls `train_v3_detector` (current config `stage1_v3_detector.yaml`). Superseded by `launch_net2_v3_1.sh`. | Calls a LIVE trainer with a v3 config — not clearly dead. Confirm no queued Net 2 retrain uses it before removing. |
| `scripts/check_dual_status.sh` | keep-pending (low) | **NEEDS-USER-DECISION** | No external ref; runs `modal run modal_apps/train_net1.py::status`. | Retire only if Modal is abandoned. |
| `scripts/run_smoke_matrix.sh` | keep-pending (low) | **CONFIRMED-SAFE** | No external ref (self only). Tracked. | Hand-run smoke matrix; not in CI. |
| `scripts/screenshot-all-pages.ts` | keep-pending (low) | **REJECTED** (as orphan) | `GITLAB.md:189` documents it as the regen tool for `screenshots/`. | Documented dev tool, not orphan. Keep. |
| `scripts/screenshot-superbuilders.ts` | keep-pending (low) | **REJECTED** (as orphan) | `GITLAB.md:189` documents it as regen tool. | Documented dev tool. Keep. |

---

## 6. Stale docs (re-verified)

| Item | Prior flag | Verdict | Evidence | Note |
|---|---|---|---|---|
| `docs/GOAL_STATE.md` | keep-pending/archive (low) | **NEEDS-USER-DECISION** | Referenced only by `archive/HANDOFF_NET3_V2.md`. It in turn is the **only** live ref to `build_manifest.py`. | Move to archive, don't delete. |
| `docs/v3-plan.md` | keep-pending/archive (low) | **NEEDS-USER-DECISION** | Referenced only by `archive/HANDOFF_STAGE1.md` + `optimization-attempts/README.md`. | Archive, don't delete (historical record). |
| `docs/aws_quota_appeal.md` | keep-pending/archive (low) | **NEEDS-USER-DECISION** | Referenced only by `archive/HANDOFF_V3_1.md`. | Archive, don't delete. |
| `docs/VALIDATION_REPORT.md` | keep (high) | **CONFIRMED** (keep) | Referenced by current `HANDOFF_WEBGPU_E2E.md` + `HANDOFF_REGRESSION_ROUND.md`. | Current. Keep. |

---

## Where the prior report was wrong

1. **`train_v2_facebody.py` is NOT a dead v1/v2 trainer** — it is the LIVE Net 1
   trainer (`modal_apps/train_net1.py:157`, `train_net1_v3_1.py:128`; the current
   `HANDOFF_MEDIAPIPE_GAP.md:87` treats `train_net1_v3_1.py` as the Net 1
   source-of-truth). The report's "retire the v1/v2 trio as one decision" would
   delete a live trainer. **REJECTED.**
2. **`transforms_v2.py`, `transforms.py`, and `losses.py` are all transitively
   live** through `train_v2_facebody.py` (imports at lines 28, 30→cached.py:14,
   31). The report flagged them for deletion-with-the-trainers. **REJECTED.**
3. **`modal_apps/train_net1_v3_1.py` is current-round**, not a stale Modal
   duplicate — named by the active handoff and shipped by both live launchers.
   **REJECTED** as a delete.
4. **`screenshot-all-pages.ts` / `screenshot-superbuilders.ts` are documented**
   (`GITLAB.md:189`) dev tools, not pure orphans. Keep.

Everything else in the report held up. The pure-v1 (`train.py`, `train_v2.py`)
and orphan orchestrators are genuinely off the live path and safe to retire **as
a coordinated set** (user decision), but only after the live Net 1 dependency on
`train_v2_facebody` + `transforms_v2`/`transforms`/`losses` is preserved.
