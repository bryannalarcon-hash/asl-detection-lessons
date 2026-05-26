# PRD Gap Audit — Independent Verification Pass

Empirical re-check of the load-bearing claims in `docs/audit/prd-gaps.md`.
Every verdict below was derived from a fresh grep/read/byte-count, not from the
prior report. Date: 2026-05-25.

Verdict legend: CONFIRMED = report was correct; REFUTED = report was wrong;
PARTIALLY-CORRECT = directionally right with a material nuance.

## Verification matrix

| Claim | Prior status | Verdict | Evidence (file:line / command) |
|---|---|---|---|
| **1. Real CV is dead code; `evaluate.ts` exports mock; no live component imports the real pipeline** | MISSING / NOT WIRED | **CONFIRMED** | `frontend/src/cv/evaluate.ts:3` = `export * from './evaluate.mock';`. Only importer of `@/cv/evaluate` in the whole app is `components/practice/DevPanel.tsx:2` (`__devSetBoxState`, a mock-only export). `grep processFrame\|evaluateRep\|evaluate.real` across `frontend/src` → zero callers (only the self-reference comment in `evaluate.ts:2` and a comment in `cv/ort/session.ts:320`). `CameraPanel` accepts a `matchScore?` prop (`CameraPanel.tsx:14`) but `Practice.tsx:501` renders `<CameraPanel boxState mirror paused />` — `matchScore` is never passed, so it is always `undefined`. The real cascade is built but unreachable from the app. |
| **2. Bundle ~65MB; net1.onnx 53.5MB vs ≤25MB target / 40MB ceiling** | AT RISK | **CONFIRMED** (numbers exact) | `stat` bytes: net1=53,515,044 (51.0 MiB / 53.5 MB decimal), net2=1,361,316, net3=5,855,558, net4=4,151,648. **Total = 64,883,566 bytes = 61.9 MiB (~64.9 MB decimal).** Budget figures live in `docs/ml-handoff.md:200`: "Model bundle size **≤ 25MB total**", current "40MB", "Use INT8 quantization." latency budget at `ml-handoff.md:196` (≤25ms p95, current 33ms). The "~65MB" and "53.5MB" are accurate; total is ~62 MiB / ~65 MB depending on MB convention. |
| **3. Pedagogy inert — `toFullSignDrills` collapses every sign to one full-sign stage; handshape/movement never run live** | NOT IMPLEMENTED / PARTIAL | **CONFIRMED** | `Practice.tsx:72-81` `toFullSignDrills()` always returns a **single-element array** with `drillType: 'sign'` (prefers existing `sign` drill → else first drill retargeted as `sign` → else synthesized `sign`). `buildSignsFromBackend` (`:61`) routes every sign through it. `drillTypes` (`:235-236`) therefore length 1, so the `DrillIndicator` stage tabs are hidden (`:354` `drillTypes.length > 1`). Nuance: the DB **does** store all 3 stages — `scripts/seed-dev-user.ts:326-345` emits `handshape`/`movement`/`sign` rows per sign and `schema.ts:64` `drill_definition` holds them — so the data and the XState machine support decomposition; only the frontend lesson-build path discards it. |
| **4. TOTAL_SIGNS=75 hardcoded vs 96-sign catalog** | DRIFTED | **CONFIRMED** | `scripts/seed-dev-user.ts:46` `TOTAL_SIGNS = 96`; lesson `signCount` fields sum to **96** (`grep signCount \| awk` → 96). Backend `routes/progress.ts:21` `const TOTAL_SIGNS = 75` and uses it as the dashboard denominator (`:241 total: TOTAL_SIGNS`). Frontend `lib/constants.ts:3` `TOTAL_SIGNS = 75`. Nuance: `Dashboard.tsx:41` prefers the live API value (`data?.masterySummary.total`) and only falls back to the constant — but the API value is itself the backend's hardcoded 75, so the headline still reads "X / 75" against a 96-sign catalog. |
| **5. Session cookie documented "signed" but is a plain UUID** | PARTIAL | **CONFIRMED** | `backend/src/lib/session.ts:20` `setCookie(c, SESSION_COOKIE_NAME, userId, {...})` — the cookie value IS the raw user UUID; flags are `httpOnly`, `sameSite:'Lax'`, `secure:false`. No HMAC/signing anywhere; the file header comment (`:4-12`) explicitly states "no signing, no encryption." Validation is just a UUID-shape regex (`:38`). The "signed" claim is in `docs/prd-scaffold.md:441`: "Cookie: `asl_session`, signed, httpOnly...". So the contract over-claims; code is honest plain-UUID. |
| **6. `/api/me` is actually `/api/auth/me`** | DONE (path differs) | **CONFIRMED** | `backend/src/routes/auth.ts:234` `app.get('/me', ...)`; mounted at `backend/src/index.ts:16` `app.route('/api/auth', authRoutes)` → effective path `/api/auth/me`. PRD documents `/api/me` (`docs/prd-scaffold.md:417` table row and `:144` directory comment). Frontend calls `/api/auth/me` (`frontend/src/lib/api.ts` auth helpers), so app is internally consistent; only the written PRD contract differs. |

## Spot-checks (additional, my choosing)

| Claim | Prior status | Verdict | Evidence |
|---|---|---|---|
| 8 DB tables present | DONE | **CONFIRMED** | `schema.ts` `pgTable` defs: `user:30`, `lesson:45`, `sign:54`, `drill_definition:64`, `rep_log:74`, `mastery_state:95`, `streak_state:114`, `notification_pref:124` — all 8. |
| 3 drill_definition rows per sign | DONE | **CONFIRMED** | `seed-dev-user.ts:326-345` returns `handshape`/`movement`/`sign` per sign; `:503` `drillTypes = ['handshape','movement','sign']`. |
| No video/frame upload; only rep outcomes leave device | DONE | **CONFIRMED** | `frontend/src/lib/api.ts` rep payload (`:139-143`) = `signId/drillType/outcome/source/hintRequested` only; no `FormData`, frame, or keypoint field anywhere. `CameraPanel.tsx` binds `getUserMedia` to a local `<video>` (`useCameraPermission`), no fetch of stream. Note: `source` enum includes `'cv'` but with CV unwired only `self-report`/`dev` are produced live. |
| Auto-advance on green box (green→PASS after 350ms, re-fire latch) | DONE | **CONFIRMED** | `Practice.tsx:208-229` `greenFiredRef` latch; on `SELF_REPORT` + green, 350ms timeout flips box to orange then `send({type:'PASS'})`; latch resets only when box leaves green. |
| ≤25MB/40MB budget figure location | (cited) | **CONFIRMED** | `docs/ml-handoff.md:200` exact text; latency budget `ml-handoff.md:196`. |

## Net assessment

- **CONFIRMED, real, and high-impact:** Claims 1 (CV dead code), 2 (~65MB bundle, net1=53.5MB), 3 (drill decomposition inert), 4 (75 vs 96), 5 (plain-UUID cookie), 6 (`/api/auth/me` path). None were overstated; the numbers in the report (53.5MB, 96, 75, total ~65MB) check out to the byte.
- **Slightly understated nuance on Claim 3:** the report frames the pedagogy as "machinery exists, pedagogy doesn't run." That's correct, but it is worth emphasizing the gap is **purely one frontend function** (`toFullSignDrills`) — the DB rows, the API types, and the XState machine all already carry the 3-stage decomposition. The fix surface is small; the behavioral gap is large.
- **Slightly overstated nuance on Claim 4:** Dashboard reads the live API total first, not the frontend constant, so the frontend `75` is a fallback — but since the backend also hardcodes `75`, the user-visible "/75" is still wrong vs the 96-sign catalog.
- **No claim was REFUTED.** The prior report is empirically accurate on all six load-bearing claims and the spot-checked secondary claims.

## Single most important real gap

**Real CV is fully built but completely unwired (Claim 1).** `evaluate.ts`
re-exports the mock, no component imports `processFrame`/`evaluateRep`,
`CameraPanel.matchScore` is never fed. The flagship "camera-aware" capability —
the entire ORT/WebGPU cascade and all four ONNX models — does not execute in the
live app at all. Claim 2 (the ~65MB unquantized bundle) is the prerequisite
blocker: even a one-line `evaluate.ts` swap would ship a 53.5MB unquantized
net1.onnx that blows the ≤25MB budget and would be impractical to load on the
target laptop.
