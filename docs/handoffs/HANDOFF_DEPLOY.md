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

### What does NOT work on prod (the open issue)
**`/models/*.onnx` and `/videos/lessons/*.mp4` return `index.html`** (the SPA
fallback) — they're never in `dist`. Root cause: those assets are **gitignored**
and `railway up` excludes gitignored paths. `--no-gitignore` + a `.railwayignore`
did NOT include them (the prod vite build runs in ~5s = no large public assets
copied), and the full ~700MB upload hits **413 Payload Too Large**. Consequences:
- In-browser CV is disabled on prod (worker fetches net1.onnx → gets HTML → ORT
  parse error → `notReady` → no Record button).
- Reference videos show the **nyan-cat mock** (real clip 404 → onError fallback).

---

## 2. NEXT STEPS — get the prod assets served (priority)

The gitignored large assets (`frontend/public/models/*.onnx` ~93MB,
`frontend/public/videos/lessons/*.mp4` ~578MB) must reach the deployed image.
`railway up` can't carry them (gitignore-excluded + 413 over ~hundreds of MB).
Options, recommended order:

1. **External object storage (best for the videos).** Put videos+models in a
   public bucket (Cloudflare R2 / S3 / Backblaze). Make the app's asset base
   configurable: `videoSrcForSign` (`frontend/src/lib/lesson-config.ts`,
   `LESSON_VIDEO_BASE`) and the model URLs (`frontend/src/cv/ort/models.ts`,
   `/models/...`) → prefix with `VITE_ASSET_BASE` (build-time env). Build with
   `VITE_ASSET_BASE=https://<bucket>`. No backend change; no upload-size issue.
2. **Docker image via a registry (handles any size).** Build locally (`docker
   build .` — `.dockerignore` keeps videos/models since they're on the local
   FS), push to GHCR/Docker Hub, point the service at the image. Bypasses the
   `railway up` upload limit. Needs registry creds.
3. **Railway Volume** mounted at the assets path, populated once (e.g., boot
   downloads from a temp URL). More moving parts.

Quick test to confirm a fix served the models (not the SPA fallback):
`curl -sI <URL>/models/net4.onnx` → expect `content-type: application/octet-stream`,
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

- `railway up` honors `.gitignore`; `--no-gitignore` + `.railwayignore` still
  did not include the gitignored models/videos this session — that's the live
  asset-serving blocker (see §2).
- 413 at ~700MB upload; ~70MB uploads fine.
- Backend MUST run via `tsx` in prod (tsc-ESM emits extensionless imports
  `node` can't resolve). Build only the frontend in Docker.
- vite-plugin-pwa errors on any precache file >2MB → `.wasm` is in `globIgnores`.
- Secure cookie is gated on `NODE_ENV==='production'`; CORS on `CORS_ORIGINS`.
- Models/videos are gitignored + regenerable; never commit them (578MB/93MB).
- Verify a model serves (not the SPA fallback): content-type must be
  `application/octet-stream`, not `text/html`.
