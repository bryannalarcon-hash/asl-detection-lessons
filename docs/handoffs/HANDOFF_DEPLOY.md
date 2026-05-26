# Handoff — Railway deploy + app integration (compaction resume point)

Read this FIRST after compaction. Self-contained. Covers the live deploy, what
works/doesn't, the local dev state, the open issues with exact next steps, and
gotchas. (Prior ML detail: `HANDOFF_WEBGPU_E2E.md`.)

---

## 1. Live deploy (Railway)

- **URL: https://asl-pilot-api-production.up.railway.app** (also in README).
- Project `asl-pilot` `10e63617-04f0-41d9-b7eb-d0600e00091c`; env `production`
  `ee4a6bde-1bd9-4167-99d8-1e9035e52a20`; app service `asl-pilot-api`
  `17bdc966-5865-4c09-a473-953d5c8b9fcd`; **Postgres** service
  `28eb7ebd-9a50-4c04-a4f7-9c20947c4653`.
- CLI is authed (Bryann). **Use the CLI, not the Railway MCP** (the MCP is
  unauthenticated; the CLI works). Deploy: `railway up --service asl-pilot-api --detach`.
- Architecture: **single service**. The Hono backend serves `/api/*` AND the
  built SPA (`frontend/dist`) on `$PORT` (Railway injects PORT=8080). Boot CMD
  (Dockerfile): `tsx migrate → SEED_IF_EMPTY=1 tsx seed → tsx serve` (all via
  tsx — `node dist` fails on ESM extensionless imports).
- Service env (set via `railway variables --service asl-pilot-api`):
  `DATABASE_URL=${{Postgres.DATABASE_URL}}`, `NODE_ENV=production`,
  `DEV_TOOLS_ENABLED=1` (DEMO posture — skip-login works), `CORS_ORIGINS=<the URL>`.

### What WORKS on prod
SPA loads; `/api/health` → `{ok:true,dbReachable:true}`; Postgres connected;
**dev-login works** (`POST /api/auth/dev-login` → Dev User, `Secure` cookie);
lessons catalog seeded (12 lessons / 96 signs, real signCounts); dashboard.
`[Dev: Skip login]` → seeded Dev User demo, like the youtube demo.

### Prod assets — RESOLVED (2026-05-26, Railway Volume)
`/models/*.onnx` and `/videos/lessons/*.mp4` now serve from a **mounted volume**
(verified: `net4.onnx` → `application/octet-stream`, `net1.onnx` full 53,515,044
bytes, `dad.mp4` → `video/mp4`). In-browser CV + real reference clips work on prod.

**The real root cause was a build bug, not the assets.** `.railwayignore` had
**unanchored** dir patterns (`src`, `tools`, `tests`, …) which in gitignore syntax
match at ANY depth — so `railway up` was stripping `frontend/src`/`backend/src`
from the upload. Every deploy after the volume was attached then failed at the
**build** step (`Rollup failed to resolve /src/main.tsx`), which is why the
failed deployments had **empty deploy logs** (they never reached the run step).
Fix: anchor every repo-root dir with a leading slash (`f2be396`). The volume was
fine all along.

---

## 2. How prod assets are served (the volume setup)

- **Volume** `asl-pilot-api-volume` (`7c141e55-…`), mounted at **`/data`** on
  `asl-pilot-api`. Env **`ASSETS_DIR=/data/assets`**.
- Backend (`backend/src/index.ts`) serves `/models/*` + `/videos/*` from
  `ASSETS_DIR` via `serveStatic` **ahead of** the SPA fallback (`c14e5a7`). The
  tiny `gloss_to_idx.json` is also in-image as a fallback.
- Heavy assets are **excluded** from both the image (`.dockerignore`) and the
  upload (`.railwayignore`): `frontend/public/models/*.onnx`, `…/models/fp16`,
  `…/videos`. Keeps the image lean + the upload well under 413.
- **Seeding the volume** (one-time): a guarded `PUT /api/_seed/asset?path=…`
  (+ `GET /api/_seed/manifest`), token-gated by env `SEED_TOKEN`, path-traversal-
  safe, **off unless both `ASSETS_DIR` and `SEED_TOKEN` are set**
  (`backend/src/routes/seed-assets.ts`). Procedure used: set a random
  `SEED_TOKEN`, deploy, run `/tmp/asl_seed_upload.sh` (curl-PUTs all 103 files
  ~639MB), verify, then **delete `SEED_TOKEN` + redeploy** to close the route
  (now returns 404). The volume data persists across redeploys.
- **Re-seed if the volume is ever wiped:** re-set a `SEED_TOKEN` var, redeploy,
  re-run the upload loop (it lives at `/tmp/asl_seed_upload.sh`; regenerate from
  the §"seed-assets" route shape if gone — it just PUTs every file under
  `frontend/public/{models,videos}`), then delete `SEED_TOKEN` + redeploy.

Confirm models serve (not the SPA fallback):
`curl -sI <URL>/models/net4.onnx` → `content-type: application/octet-stream`,
NOT `text/html` (737b = index.html).

## 3. Other open issues

- **Camera self-view not appearing on prod even when allowed.** Independent of
  the assets (`getUserMedia`, not a file). HTTPS is a secure context and there's
  no restrictive Permissions-Policy header. NEEDS the user's browser console
  error + desktop/mobile+browser to diagnose. Suspect: PWA service worker or a
  prod-only JS issue. The Permissions-API auto-recover fix (`fc9632e`,
  `useCameraPermission.ts`) is deployed.
- **Prod hardening (CLAUDE.md preconditions) — currently DEMO posture.**
  `DEV_TOOLS_ENABLED=1`, shared dev account seeded, dev-login open. Before any
  real-learner use: `DEV_TOOLS_ENABLED=0`, rebuild with `VITE_DEV_TOOLS=0`, drop/
  secure the shared dev account. (Secure cookie + CORS already env-correct.)
- **net1Stride=32** in the app (`captureRep.ts`) is the −4.3pp accuracy cliff;
  16 is the −0.7pp safe limit. Capture window is **3s**, **top-5 acceptance**.

## 4. Local dev (all working — assets present locally)

- Backend `:4000` (`BACKEND_PORT=4000 npm run -w backend dev`, nohup);
  frontend `:5173` (`VITE_API_URL=http://localhost:4000 npm run -w frontend dev`,
  nohup). Postgres docker `asl-pilot-postgres` on **:5433** (NOT 5432 — another
  project holds 5432). If it's stopped: `POSTGRES_PORT=5433 docker compose up -d
  postgres` (named volume persists the seed). Restart servers with `nohup` (the
  sandbox SIGTERMs `run_in_background` sockets).

## 5. What shipped this session (committed to main, NOT pushed to remote)

Capture-rep CV wired into the React app (`frontend/src/cv/{captureRep,
captureWorker,batchedRuntime,batchedDecode}.ts` + `hooks/useCaptureRep.ts` +
`components/practice/RecordAttemptRow.tsx`; backend serves the SPA). Hint system
(`data/sign-hints.ts` 96 entries + `lib/hint-diagnosis.ts` + HintButton: word-tied
default, rule-based targeted hint after a fail). Dev CV readout (`CvReadout.tsx`,
toggle in DevPanel) + **dev "Replay my capture"** (`DevClipReplay.tsx`, in-memory
last clip). **top-5 acceptance** + 5-in-readout. **3s** capture window. Catalog
`signCount` LEFT-JOIN fix. Reset-progress per lesson (`POST
/api/progress/lesson/:slug/reset` + LessonIntro button). Camera auto-recover.
ORT pinned **1.26.0** (wasm CDN). PWA precache excludes `.wasm`. Practice UX:
red-on-fail box, 3s green hold, hide segment bars in whole-sign. Audit reports in
`docs/audit/`. The Railway deploy: `Dockerfile`, `.dockerignore`, `.railwayignore`
+ backend SPA-serving/PORT/secure-cookie/CORS-env. `onnxruntime-node` devDep.

Recent commits (all local): `1153ccc 413-exclude videos`, `eba9ece no-gitignore`,
`a98f305 tsx server`, `a1a5cc9 .wasm precache`, `ba23c66 single-service deploy`.

## 6. Gotchas

- **`.railwayignore`/`.dockerignore` patterns are gitignore-style**: an
  UNANCHORED name (`src`, `tools`, `tests`) matches that dir at ANY depth — it
  WILL strip `frontend/src`/`backend/src` and break the build with empty deploy
  logs. Anchor every repo-root dir with a leading slash (`/src`). This was the
  asset-serving red herring that cost most of the 2026-05-26 session.
- A FAILED deploy that never ran its CMD shows **empty deploy logs** — look at
  the **build** logs (`railway logs <id> -b`), the failure is usually there.
- `railway logs` with no id shows the most recent **successful** deploy; pass the
  failed deployment id (from `railway deployment list --json`) to see its logs.
- Deleting/changing a var does **not** reliably auto-redeploy; run
  `railway redeploy --service asl-pilot-api -y` to apply env changes.
- `railway volume files upload` needs an SSH key registered (`railway ssh keys
  add`); we seed via the HTTP `/api/_seed` route instead (no SSH).
- 413 at ~700MB upload; lean uploads (code only, assets on the volume) are fine.
- Backend MUST run via `tsx` in prod (tsc-ESM emits extensionless imports
  `node` can't resolve). Build only the frontend in Docker.
- vite-plugin-pwa errors on any precache file >2MB → `.wasm` is in `globIgnores`.
- Secure cookie is gated on `NODE_ENV==='production'`; CORS on `CORS_ORIGINS`.
- Models/videos are gitignored + regenerable; never commit them (578MB/93MB).
- Verify a model serves (not the SPA fallback): content-type must be
  `application/octet-stream`, not `text/html`.
