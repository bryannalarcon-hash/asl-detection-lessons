# Local setup

Local-only deployment for the ASL pilot. Everything runs on your machine — no Supabase, Vercel, or cloud services in this configuration.

## What runs where

| Component | Where | Port |
|---|---|---|
| Postgres | Docker container (`asl-pilot-postgres`) | 5432 |
| Adminer (DB UI) | Docker container (`asl-pilot-adminer`) | 8088 |
| Backend (Node + Hono + Drizzle) | Host, `npm run dev:api` | 3000 |
| Frontend (Vite + React) | Host, `npm run dev` | 5173 |
| Reference videos | Frontend `/public/videos/` | Vite-served |
| ML model bundle | Frontend `/public/models/` | Vite-served (mock stub in v1) |

## Prerequisites

- **Docker** (Docker Desktop with WSL2 backend, or `docker.io` apt-installed in the WSL distro). Compose v2 required.
- **Node** matching `.nvmrc` (planned: 20.11). Install via `nvm install && nvm use` once `.nvmrc` lands.
- **Repo location**: if you're on WSL2, **keep this repo inside the WSL Linux filesystem** (e.g., `~/projects/asl-learning`), not `/mnt/c/...`. Cross-boundary filesystem mounts break Vite HMR and slow Postgres I/O by 10×.

## One-time setup

> **Note**: steps 4–7 are **planned**, not yet implemented. The frontend and backend haven't been scaffolded into this repo yet. Step 1–3 work today; steps 4–7 work after the scaffolding lands.

```bash
# 1. Copy environment file
cp .env.example .env

# 2. Start Postgres (and Adminer)
docker compose up -d

# 3. Wait for the DB to be healthy
docker compose ps  # postgres should show "(healthy)"

# 4. (Planned) Install dependencies
npm install

# 5. (Planned) Apply schema migrations
npm run db:migrate

# 6. (Planned) Seed the dev user (75 days of varied practice history)
npm run db:seed

# 7. (Planned) Start the backend and frontend in separate terminals
npm run dev:api    # backend on :3000
npm run dev        # frontend on :5173
```

The repo layout will be a monorepo with `frontend/` and `backend/` subdirs sharing one root `package.json` + workspaces. All `npm run` commands run from repo root.

## Daily use

```bash
# Start everything (use two terminals or tmux panes for the dev servers —
# the & backgrounding makes Ctrl-C messy)
docker compose up -d
# Terminal 1:
npm run dev:api    # backend
# Terminal 2:
npm run dev        # frontend

# Stop the data services (data persists)
docker compose down

# Reset the database (destroys all data, including dev account)
docker compose down -v
docker compose up -d
npm run db:migrate
npm run db:seed
```

### Backup / restore the dev DB

```bash
# Snapshot the current state to a file
docker exec -t asl-pilot-postgres pg_dump -U asl asl_pilot > backups/$(date +%F).sql

# Restore from a snapshot (drops + reloads)
docker exec -i asl-pilot-postgres psql -U asl -d asl_pilot < backups/2026-05-21.sql
```

Useful when you've hand-curated a specific mastery state and don't want `db:seed` to overwrite it.

## Dev bypasses (no auth provider in v1)

The app ships **no real auth backend in v1**. Instead, the dev panel exposes:

- **Skip-login button** on the sign-in page — signs you in as `dev@asl-pilot.local` (the seeded account with rich history)
- **Mock CV state buttons** on the Practice Screen — Set Gray / Set Orange / Set Green for the bounding box
- **Dev bypass** on every auth-blocked screen (email verification, magic link, password reset, camera permission)

All gated by `VITE_DEV_MODE=1` (default in `.env.example`). Set `VITE_DEV_MODE=0` to strip them from the build.

## Real auth (deferred)

When we add real users, the path forward is one of:
- **Better Auth** (self-hostable, modern, TypeScript-first)
- **Lucia v3** (lightweight, library-only, full control)
- **Hand-rolled cookie sessions** with a `sessions` table

This is intentionally deferred until we have a real user beyond the dev account. See `ml-handoff.md` for what the ML team needs regardless of which auth path we pick.

## DB access

- Connection string: `postgres://asl:asl_dev_only@localhost:5432/asl_pilot`
- Adminer at `http://localhost:8088` — server `postgres`, username `asl`, password `asl_dev_only`

## Reference videos

For local dev, drop Deaf-signer reference clips into `frontend/public/videos/<sign-slug>.mp4`. Naming convention: `thank-you.mp4`, `hello.mp4`, etc. Production will move these to Cloudflare Stream or Bunny.net, but local dev keeps it simple.

Captions go alongside as `<sign-slug>.vtt`. Mandatory per the WCAG floor.

## Resetting just the dev account

```bash
npm run db:seed -- --reset-dev-account
```

Wipes only the dev account's practice history + mastery rows, then re-seeds. Other accounts untouched.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `docker pull` hangs / fails | Corporate proxy? Configure `~/.docker/config.json` with proxy settings or set `HTTP_PROXY` env |
| Frontend can't reach backend | Check `BACKEND_PORT` matches `.env`; check CORS allowlist in the backend |
| `db:migrate` fails with "connection refused" | `docker compose ps` to confirm postgres is healthy; wait 10s after `up` |
| Dev bypass buttons missing | Check `VITE_DEV_MODE=1` in `.env`; restart Vite dev server |
| Adminer can't log in | Server is `postgres` (the container name), not `localhost` |
| Camera doesn't work in browser | `localhost` is a secure context for `getUserMedia` in Chrome/Firefox/Safari; if you're hitting `127.0.0.1` from Firefox specifically, try `localhost` |
| Vite HMR randomly stops working on WSL2 | Repo is on `/mnt/c/...`? Move it into the WSL Linux filesystem (`~/projects/`) |
| `localhost` doesn't resolve to WSL services | `wsl --shutdown` from a Windows PowerShell, then restart |

## What's NOT in local dev

- Email sending (verification, magic link, password reset) — use dev bypass
- OAuth providers (Google, etc.) — use dev bypass
- Real CV inference — use mock CV buttons
- Cloudflare Stream / Bunny.net — videos served from `/public/videos/`
- Sentry, PostHog, Plausible — disabled or stubbed
- CDN, edge caching, anything network-shape — single-machine only
