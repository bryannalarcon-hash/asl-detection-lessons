# Codebase audit — consolidated, verified action list

Two-phase swarm: 3 analysis agents (organization / PRD gaps / cleanup) →
3 verification agents that independently re-ran every grep. This file is the
reconciled result. **Nothing has been deleted or moved.** Buckets are gated on
owner approval. Source detail: `organization.md`, `prd-gaps.md`,
`cleanup-candidates.md`, `verify-org.md`, `verify-prd.md`, `verify-cleanup.md`.

---

## Bucket A — Safe now (verification-confirmed LOW risk)

| Action | Target | Verified by |
|---|---|---|
| Delete | `src/stage2/data/build_manifest.py` (ASL-Citizen builder, superseded by `build_manifest_popsign.py`, zero live importers) | verify-cleanup |
| Delete | `frontend/src/components/ui/badge.tsx` (zero imports) | verify-cleanup |
| Delete | `frontend/src/components/ui/tabs.tsx` (zero imports) | verify-cleanup |
| Untrack | `.scaffold-final-report.md` (tracked while `.scaffold-phase*` siblings are gitignored — glob missed "final"); `git rm --cached` + add to `.gitignore` | verify-org R3 |
| Relocate | `google_iso_1st_place.md` → `docs/` (no path refs) | verify-org R1 |
| Relocate | partner-brief PDF → `docs/` (no path refs) | verify-org R2 |

Also confirmed safe-now but lower value: `scripts/plot/` grouping (no code
invokes plot scripts by path), `scripts/node/` for the screenshot TS tools,
`docs/status/` grouping for stale status docs.

## Bucket B — Coordinated / MED (atomic multi-file edits)

| Action | Must also update (or it breaks) |
|---|---|
| Regroup 15 loose `docs/` files → `docs/reference|ml|status/` | `CLAUDE.md` Pointers block + `docs/handoffs/README.md:42` (4 doc paths, atomic) |
| Move `scripts/seed-dev-user.ts` | `package.json:18` (`db:seed`) **and** `frontend/tests/unit/seed.spec.ts:14` (relative import) — verify-org caught the test ref the analysis pass missed |

## Bucket C — Deferred / HIGH (swarm-gated, NEVER mid-extraction)

- **`scripts/` subfoldering** — 46 runtime call sites across 23 scripts using
  hardcoded `scripts/<name>` paths after `cd /workspace/asl` on pods, **plus** a
  `python3 -m scripts.e2e_smoke_test` module invocation (`run_net4_after_net3.sh:127`)
  that a path-grep can't see. Only do as one swarm-gated pass that rewrites all
  sites and re-pushes to GitLab *before the next pod clone*. Pod B is extracting
  right now — do not touch.
- **`configs/` stays flat** — 53 call sites / 16 files reference `configs/<name>.yaml`.

## REJECTED by verification (do NOT delete — live references found)

- `src/stage1/train_v2_facebody.py` — **LIVE Net 1 trainer** (`modal_apps/train_net1.py:157`, `train_net1_v3_1.py:128`; named in current `HANDOFF_MEDIAPIPE_GAP.md:87`).
- `transforms_v2.py`, `transforms.py`, `losses.py` — all reachable from `train_v2_facebody.py`.
- `modal_apps/train_net1_v3_1.py` — current-round, shipped by live launchers.
- `screenshot-all-pages.ts`, `screenshot-superbuilders.ts` — documented dev tools (`GITLAB.md:189`).
- Pure-v1 `train.py` / `train_v2.py` + orphan orchestrators → retire **as a set only after** confirming the `train_v2_facebody` dep is preserved and no retrain is queued (NEEDS-DECISION).

## Oversized files — SPLIT (refactor, not delete; boundaries verified)

`dali_pipelines.py` 910 · `extract_keypoints.py` 671 · `anchors.py` 592 ·
`train_v3_detector.py` 584 · `train_v3_landmark.py` 535 · `Practice.tsx` 502.
Separate refactor effort; each split point confirmed real.

---

## PRD gaps (verified real; product backlog, ranked)

1. **Real CV is built but unwired.** `cv/evaluate.ts:3` exports the mock; zero
   callers of `processFrame`/`evaluateRep`; `CameraPanel.matchScore` never fed
   (`Practice.tsx:501`). Flip to `evaluate.real` + wire the verdict.
2. **~65MB ONNX bundle** (net1 53.5MB) vs `ml-handoff.md:200` ≤25MB target —
   hard precondition; needs quantization (deferred until the 125/word Net 4 is final).
3. **Pedagogy decomposition inert** — `toFullSignDrills` (`Practice.tsx:72-81`)
   collapses to one stage. **NOTE: this is the owner's deliberate "full-sign-only
   with reps" decision, not a regression.** Listed only so it's a conscious choice.
4. **`TOTAL_SIGNS=75`** hardcoded (backend + frontend) against a 96-sign catalog →
   mastery bar shows "/75". Small fix.
5. **Session cookie is a raw UUID**, not "signed" as `prd-scaffold.md:441` claims
   (`session.ts:20`). Already in CLAUDE.md prod preconditions; fix doc or sign.
6. **`/api/auth/me`** vs PRD's `/api/me` — doc correction.
