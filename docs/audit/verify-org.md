# Organization Audit — Verification Pass

REPORT ONLY. No files moved, renamed, edited, or deleted. This independently
re-greps the reference graph behind `docs/audit/organization.md` and confirms,
corrects, or flags each risk rating. The remote training pipeline is LIVE
(a pod is mid-extraction; `scripts/` scp/source each other after
`cd /workspace/asl`), so move-safety on the orchestration scripts is load-bearing.

Method: ran `grep` for `scripts/<name>.{sh,py,ts}` and `-m scripts.<name>`
across `scripts/ modal_apps/ src/ tools/ backend/ frontend/ package.json`,
then classified each hit as **runtime invocation** (breaks on move),
**compile-time import** (breaks on move), **self-reference usage string**
(harmless), or **comment/docstring/`.md` mention** (stale text, no runtime break).

---

## Headline corrections vs the prior report

1. **The prior report's path-grep missed an entire coupling class:
   `python3 -m scripts.<name>` module invocations.** `scripts/` has no
   `__init__.py` but `-m scripts.X` resolves via implicit-namespace package
   from repo root. Moving such a script into `scripts/<sub>/` rewrites its
   module path to `scripts.<sub>.X` and breaks `-m` callers — a *silent*
   break the `scripts/<name>` grep cannot see. One is a **live runtime
   cross-call**: `run_net4_after_net3.sh:127` runs
   `python3 -u -m scripts.e2e_smoke_test`. Self-doc'd module scripts also
   exist: `cost_ledger.py`, `prebuild_net3_indices.py`,
   `build_synthetic_composites.py`, `convert_egohands_to_yolo.py`,
   `profile_v3_detector.py`, plus archived-handoff calls to
   `-m scripts.eval_nets` / `-m scripts.cost_ledger`.

2. **S3 (`seed-dev-user.ts`) is under-coupled in the report.** It is rated
   MED "one package.json line + docs," but there is **also a compile-time
   TypeScript import**: `frontend/tests/unit/seed.spec.ts:14`
   `import {...} from '../../../scripts/seed-dev-user'`. Moving the file
   breaks that relative import (becomes `../../../scripts/node/...`). So S3
   couples **two** code files, not one. The report's note "frontend tests
   reference dev-credentials not this path" is incorrect.

3. **Dead reference found (not a move risk, but worth noting):**
   `launch_net2_v3_1.sh:169` points at `scripts/_remote_net2_v3_1.sh`, which
   **does not exist** in the tree. Whatever S6/S7 pass touches launchers
   should not treat this as a live edge.

4. **Distinct-invoked-script count: report says 26, I count 23** by hardcoded
   runtime path. The gap is the `$SCRIPT_DIR`-relative siblings
   (`download_egohands.sh`, `download_rhd.sh`, `download_mpii.sh` when called
   from `download_v3_data.sh`, `build_synthetic_composites.py`) which are
   *not* `scripts/<name>` hardcoded paths. **Call-site count: report says 44,
   I count 46** runtime invocations (47 incl. the dead ref). Net: the HIGH
   rating is firmly confirmed; the headline numbers are close and if anything
   the call-site total is understated.

---

## Per-move verification table

| Proposed move | Prior risk | Verified risk | Reference count + key call sites | Verdict |
|---|---|---|---|---|
| **R1** `google_iso_1st_place.md` → `docs/reference/` | LOW | LOW | 0 code refs. Doc-only: `GITLAB.md`, `docs/handoffs/archive/HANDOFF_STAGE1.md`, `docs/audit/cleanup-candidates.md`, `docs/audit/organization.md`. (Report's ref list omitted cleanup-candidates.md.) | **CONFIRMED** |
| **R2** partner-brief PDF → `docs/superbuilders/` | LOW | LOW | 0 code refs. Doc-only: `GITLAB.md`, `docs/prd-scaffold.md`, `docs/superbuilders/portfolio.md`, `docs/handoffs/archive/HANDOFF_STAGE1.md`, `docs/audit/*`. | **CONFIRMED** |
| **R3** `.scaffold-final-report.md` → `docs/status/` or untrack | LOW | LOW | 0 code refs. `git check-ignore` confirms it is **tracked** (siblings `.scaffold-phase*` are ignored). Doc-only mentions: `HANDOFF_FRONTEND.md`, `docs/audit/*`. | **CONFIRMED** |
| **D1** 7 evergreen docs → `docs/reference/` | MED | MED | 0 *runtime* refs. CLAUDE.md (repo root) hardcodes exactly **4**: `docs/principles.md`, `docs/ux-spec.md`, `docs/ml-handoff.md`, `docs/prd-scaffold.md` — confirmed. `docs/handoffs/README.md:42` also names `docs/ml-handoff.md`. Heavy cross-doc links (principles 17, ml-handoff 17, ux-spec 14 .md mentions). 5 "code refs" found (ux-spec, ml-handoff ×3, hoyso ×1) are all **comments/docstrings** (e.g. `practice.ts:1`, `evaluate.mock.ts:1`, `sign_classifier.py:4`) — no runtime break. | **CONFIRMED** (must atomically update CLAUDE.md pointer block + handoffs/README.md) |
| **D2** 5 ML docs → `docs/ml/` | MED | LOW–MED | 0 code refs, 0 CLAUDE.md path. Doc-link only (training-plan 8, others ~3 each). Slightly over-rated vs D3 (no CLAUDE.md coupling), but the link count justifies MED. | **CONFIRMED** (lean LOW) |
| **D3** 3 status docs → `docs/status/` | LOW | LOW | 0 code refs. Few doc links (3–4 each). | **CONFIRMED** |
| **S1** `plot_*.py` (4) → `scripts/plot/` | LOW | LOW | 0 runtime invocations, **0 `-m scripts.plot_*`** module calls. Human-run ad-hoc. (3 of the 4 are uncommitted new files.) | **CONFIRMED** |
| **S2** `screenshot-*.ts` (2) → `scripts/node/` | LOW | LOW | No `package.json` entry; only `GITLAB.md` + self-refs. | **CONFIRMED** |
| **S3** `seed-dev-user.ts` → `scripts/node/` | MED | MED (couples 2 code files) | `package.json:18` `db:seed` (runtime) **AND** `frontend/tests/unit/seed.spec.ts:14` relative TS **import** (compile-time). Plus doc mentions. Report claimed 1 coupled file + wrongly said tests don't reference the path. | **RISK-UNDERSTATED** (still MED, but +1 code file to update atomically) |
| **S4** `aws_*.sh` (3) → `scripts/aws/` | MED | MED | Exactly **1** runtime caller: `launch_train_pod.sh:84` → `scripts/aws_presign_datasets.sh`. `aws_launch_net3.sh` / `aws_pull_net3.sh` have **no** code callers (doc-only). | **CONFIRMED** |
| **S5** data-prep scripts → `scripts/data/` | HIGH | HIGH | `_remote_train.sh:42/61`, `launch_v3*.sh`, `launch_net2_v3_1.sh`, `aws_launch_net3.sh:237` call `scripts/download_v3_data.sh`; that script's `split_train_val.py`/`hagrid_reorganize.py` calls are root-relative (`scripts/<name>`, break) while `download_egohands/rhd/mpii.sh` + `build_synthetic_composites.py` are `$SCRIPT_DIR`-relative (survive move-together — confirmed at lines 202–234). `modal_apps/train_net1{,_v3_1}.py` call `scripts/preprocess_cache.py`, `scripts/split_train_val.py`. **Also: `modal_apps/train_net1_v3_1.py:92` calls `scripts/download_mpii.sh` directly** (root-relative) — so `download_mpii.sh` IS path-coupled despite being a `$SCRIPT_DIR` sibling elsewhere. | **CONFIRMED** |
| **S6** runpod orchestration → `scripts/runpod/` | HIGH | HIGH | `launch_{train_pod,phase_c,eval_net2}.sh` call `python3 scripts/runpod_provision.py` + `setsid bash scripts/_remote_*.sh` after `cd /workspace/asl`. `round_health.sh` invoked by launcher (line 116). All run on a freshly-cloned pod with verbatim paths. | **CONFIRMED** |
| **S7** training launchers → `scripts/train/` | HIGH | HIGH | `run_v3_on_remote.sh:27` → `scripts/launch_v3.sh`; `ca_v2_orchestrate.sh` + `nj_orchestrate.sh` → `scripts/{preprocess_cache,split_train_val}.py` (root-relative); **`run_net4_after_net3.sh:127` → `python3 -m scripts.e2e_smoke_test`** (module-path coupling, NOT visible to the `scripts/<name>` grep). `_remote_net2_v3_1.sh` ref is dead. | **CONFIRMED** (plus undisclosed `-m` coupling) |
| **S8** eval/bench scripts → `scripts/eval/` | HIGH | HIGH | `_remote_eval_net2.sh:57` → `scripts/eval_net2_ap.py`; `_remote_phase_c.sh:93` → `scripts/build_clip_manifest.py`. **`e2e_smoke_test.py` is bound by the module form `-m scripts.e2e_smoke_test`, not the path form** — moving it to `scripts/eval/` breaks `run_net4_after_net3.sh:127` silently. `run_smoke_matrix.sh:18` → `scripts/bench_smoke.sh`. | **CONFIRMED** (the report rated this via path-form; the real binding for the e2e runner is module-form) |
| **C1** `configs/` subfoldering | HIGH (don't move) | HIGH (don't move) | **53 call sites** referencing **16 distinct config files** across `scripts/`, `modal_apps/`, `src/`, all as flat `configs/<name>.yaml`/`.json` — runtime `--config` args (e.g. `_remote_train.sh:49/53/64`, `modal_apps/train_net3.py:163/227`, `src/stage1/train_v3_detector.py:3`). Report said "16+"; the true call-site total is far higher. | **RISK-UNDERSTATED** (rating correct; the count is much larger than "16+" — 53 sites) |

---

## Cross-cutting facts (independently verified)

- **`cd /workspace/asl` (pod root) assumed by** `_remote_train.sh:11`,
  `_remote_eval_net2.sh:8`, `_remote_phase_c.sh:13`, and the three launchers'
  SSH heredocs (`launch_train_pod.sh:92`, `launch_phase_c.sh:77`,
  `launch_eval_net2.sh:57`). A few human-doc/older scripts use
  `cd /workspace/asl-learning` (`nj_orchestrate.sh:7`, `bench_smoke.sh:12`,
  `ca_v2_orchestrate.sh:4`, `run_v3_on_remote.sh:6`, `run_smoke_matrix.sh:6`)
  — i.e. there are **two** assumed pod clone-dir names in the tree. Not a
  move-safety issue, but relevant to "freshly-cloned pod" assumptions.
- **`$SCRIPT_DIR`-relative sibling calls survive a move-together** (confirmed
  in `download_v3_data.sh:202–234`): `download_egohands.sh`,
  `download_mpii.sh`, `download_rhd.sh`, `build_synthetic_composites.py`. But
  these *same* files are *also* hit by root-relative callers elsewhere
  (`modal_apps/train_net1_v3_1.py:92` → `scripts/download_mpii.sh`), so they
  cannot be treated as "safe because sibling-relative."
- **`scripts/db/`** is the only existing subfolder; it holds `init.sql` only
  (no `__init__.py`), so it sets a benign precedent that does not interact
  with the `-m scripts.X` module resolution.

---

## Recommended order of operations (unchanged shape, two corrections)

1. **Cleanup commit (LOW, zero runtime risk):** R1, R2, R3, D3, S1, S2.
   Update the named `.md`/`GITLAB.md` text mentions in the same commit.
2. **Coordinated single-file commits (MED):** D1 (+ atomically update the
   CLAUDE.md "Pointers" block **and** `docs/handoffs/README.md:42`), D2,
   S4 (+ `launch_train_pod.sh:84`), and **S3 — update BOTH `package.json:18`
   AND `frontend/tests/unit/seed.spec.ts:14` in the same diff**, then run the
   frontend unit suite.
3. **Defer S5–S8 (HIGH)** to one verification-swarm-gated pass that updates
   **all 46 runtime call sites** — including the `-m scripts.e2e_smoke_test`
   module call in `run_net4_after_net3.sh:127` (and any other `-m scripts.X`
   if those scripts move) — and re-pushes to GitLab before the next pod clone.
   Do NOT do these while a pod is mid-extraction.
4. **Leave `configs/` (C1) flat indefinitely** — 53 flat call sites, silent
   break.
