# GitLab Integration

How to interact with the `asl-detection-lessons` project through Gauntlet's GitLab instance. (The local working directory is named `asl-learning`; the remote project is `asl-detection-lessons`.)

---

## Project coordinates

| Field | Value |
|---|---|
| **Instance** | `https://labs.gauntletai.com` (GitLab CE 18.11.3) |
| **Web URL** | `https://labs.gauntletai.com/bryannalarcon/asl-detection-lessons` *(expected — confirm on creation)* |
| **HTTPS clone** | `https://labs.gauntletai.com/bryannalarcon/asl-detection-lessons.git` |
| **SSH clone** | `ssh://git@labs.gauntletai.com:22022/bryannalarcon/asl-detection-lessons.git` *(custom SSH port 22022)* |
| **Project ID** | `949` |
| **Default branch** | `main` |
| **Visibility** | Private |

If you haven't created the project yet:
1. Visit <https://labs.gauntletai.com/projects/new>
2. Project already exists at `bryannalarcon/asl-detection-lessons` (confirmed via URL).
3. Generate a **Project Access Token** with scopes: `api`, `read_repository`, `write_repository`, `create_runner`, `manage_runner`, `k8s_proxy`, `self_rotate`, `ai_features`. Set the same expiry as your other project tokens.
4. Copy the token into `.env.local` as `GITLAB_TOKEN=glpat-…`.
5. Note the numeric Project ID from the project settings page and replace `<TBD>` above + in the API URLs below.

---

## Authentication

A **Project Access Token** should live only in your local `.env.local` (which is gitignored) — **never commit it**, never paste into other files.

```bash
# Add to .env.local:
GITLAB_TOKEN="glpat-<your-token>"
```

The token is a "bot user" tied to this project (Maintainer-equivalent permissions, scoped to this project only — it cannot access your personal account or other projects).

> The synthesis-clone-SB project token is scoped to that project (ID 915) and **will not work** here. Provision a new token for `asl-detection-lessons`.

---

## First-time setup (in this working directory)

**The local repo is not yet initialized as a git repo.** Run this once after creating the GitLab project + provisioning the token.

```bash
cd /home/bryann/gauntlet/asl-learning

# Sanity-check .gitignore covers secrets + large artifacts first (see "What this repo does not publish" below).
cat .gitignore | head -40

# Initialize
git init -b main
git config user.email "your-email@example.com"
git config user.name "Bryann Alarcon"

# Source the token
source .env.local      # exports GITLAB_TOKEN

# Connect to GitLab via HTTPS + token
git remote add origin "https://oauth2:${GITLAB_TOKEN}@labs.gauntletai.com/bryannalarcon/asl-detection-lessons.git"

# Verify connection
git ls-remote origin                # should list refs

# NOTE: the remote already has one auto-generated commit ("Initial commit" with
# a boilerplate README.md created by GitLab on project creation). The push
# below uses --allow-unrelated-histories + -X ours to keep our README.md and
# preserve the GitLab initial commit as the root.

git add -A
git status                          # review what's staged BEFORE committing
git commit -m "Initial commit: ASL pilot scaffold + auth + camera + Aurora theme"

git fetch origin main
git merge -X ours --allow-unrelated-histories --no-edit origin/main
git push -u origin main
```

After the first push, normal `git push` / `git pull` works without re-specifying the token (it's baked into the remote URL).

> **Note on the embedded token:** putting `${GITLAB_TOKEN}` in the remote URL writes the token into `.git/config` on disk. `.git/` is local-only (never pushed), but anyone with read access to your machine can read it. If that matters, use SSH instead (see below).

---

## SSH-based alternative (recommended for long-term work)

If you'd rather not embed the token in `.git/config`:

```bash
# 1. Add your SSH public key to GitLab:
#    https://labs.gauntletai.com/-/user_settings/ssh_keys

# 2. Set the SSH remote (note non-standard port 22022)
git remote set-url origin "ssh://git@labs.gauntletai.com:22022/bryannalarcon/asl-detection-lessons.git"

# 3. Test
ssh -T -p 22022 git@labs.gauntletai.com
```

SSH avoids token-in-config and survives token rotation.

---

## Common operations

### Push your work

```bash
git add -A
git commit -m "describe what you changed"
git push
```

### Pull the latest from GitLab

```bash
git pull --rebase
```

### Open a Merge Request from the CLI

```bash
# Push a feature branch
git checkout -b feature/some-thing
git push -u origin feature/some-thing

# Then either:
#   - Use the GitLab web UI to open the MR, OR
#   - Use the API:
curl -X POST \
  -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  -F "source_branch=feature/some-thing" \
  -F "target_branch=main" \
  -F "title=Feature: some thing" \
  "https://labs.gauntletai.com/api/v4/projects/949/merge_requests"
```

### View pipelines

```bash
curl -s -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://labs.gauntletai.com/api/v4/projects/949/pipelines?per_page=10" | jq
```

### View issues

```bash
curl -s -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://labs.gauntletai.com/api/v4/projects/949/issues?state=opened" | jq '.[] | {id, title, web_url}'
```

### Create an issue

```bash
curl -X POST -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  --data-urlencode "title=Bug: something broken" \
  --data-urlencode "description=Steps to reproduce..." \
  "https://labs.gauntletai.com/api/v4/projects/949/issues"
```

### Trigger a pipeline manually

```bash
curl -X POST -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://labs.gauntletai.com/api/v4/projects/949/pipeline?ref=main"
```

### Read a single file via API (no clone needed)

```bash
# Example: read README.md from main
curl -s -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://labs.gauntletai.com/api/v4/projects/949/repository/files/README.md/raw?ref=main"
```

---

## What this repo *does not* publish to GitLab

The `.gitignore` should keep the GitLab repo lean. The following must stay local-only:

- `node_modules/`, build caches
- **`.env.local`** and any other env files — they hold the GitLab token + `VAST_API` + `KAGGLE_API` + the dev database password. Never commit.
- `playwright-report/`, `test-results/`, coverage artifacts
- **`design/extracted/`** — unzipped design package (`design/asl-pilot.zip` is the source-of-truth artifact; the unzipped directory is regenerable)
- **`ASL_Citizen.zip`** — the raw ASL Citizen dataset (~hundreds of MB; track via Git LFS or DVC, not main repo)
- **`screenshots/`** — auto-generated route captures + SuperBuilders crawls (regenerable via `scripts/screenshot-all-pages.ts` + `scripts/screenshot-superbuilders.ts`)
- `results/`, `playground/`, `ruvector.db`, `test-results/` — local experimentation / DB artifacts
- `.claude/`, `.swarm/`, `.codex/` — local orchestrator state (memory + reasoning artifacts)

What **should** be tracked:
- All `frontend/` and `backend/` source code
- `docs/` (PRD, ux-spec, principles, training-plan, ml-handoff, competitive teardowns, research notes)
- `scripts/` (seed, screenshots, etc.)
- `configs/`, `tsconfig.base.json`, `playwright.config.ts`, `docker-compose.yml`, `.env.example`
- `docs/handoffs/`, `README.md`, this `GITLAB.md`
- `design/asl-pilot.zip` — the source design artifact (it's small, ~100 KB)

Before the **first commit**, verify `.gitignore` covers everything in the must-stay-local list:

```bash
cd /home/bryann/gauntlet/asl-learning
cat .gitignore                       # review
git check-ignore -v .env.local       # should print the matching gitignore rule
git check-ignore -v ASL_Citizen.zip  # should match
git check-ignore -v screenshots/     # should match
```

If anything in the must-stay-local list shows as not-ignored, add it to `.gitignore` before `git add -A`.

---

## Token rotation

Token expires when you set it. To rotate before then (or after a leak):

```bash
# Using the self-rotate scope on the current token
curl -X POST -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://labs.gauntletai.com/api/v4/personal_access_tokens/self/rotate"
```

The response includes the new token. Update `.env.local` immediately. The old token is revoked at the same moment.

Or rotate via the web UI: <https://labs.gauntletai.com/bryannalarcon/asl-detection-lessons/-/settings/access_tokens>

---

## CI runner (only if you set up CI)

This project's token should have `create_runner` and `manage_runner` scope. To register a runner:

```bash
# 1. Create a runner config via API (returns a registration token)
curl -X POST -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://labs.gauntletai.com/api/v4/user/runners" \
  -F "runner_type=project_type" \
  -F "project_id=949" \
  -F "description=local-dev-runner" \
  -F "tag_list=local"

# 2. Install gitlab-runner locally, then register with the token from step 1
sudo gitlab-runner register --url https://labs.gauntletai.com --token <token-from-step-1>
```

A `.gitlab-ci.yml` is not currently in this repo. A reasonable first pipeline:

```yaml
# .gitlab-ci.yml (example — not yet committed)
stages: [lint, test]
typecheck:
  stage: lint
  image: node:20-alpine
  script:
    - npm ci
    - npx tsc --noEmit -p frontend/tsconfig.json
    - npx tsc --noEmit -p backend/tsconfig.json
playwright:
  stage: test
  image: mcr.microsoft.com/playwright:v1.49.0-jammy
  services:
    - name: postgres:16-alpine
      alias: postgres
      variables: { POSTGRES_DB: asl_pilot, POSTGRES_USER: asl, POSTGRES_PASSWORD: asl_dev_only }
  variables:
    DATABASE_URL: "postgres://asl:asl_dev_only@postgres:5432/asl_pilot"
  script:
    - npm ci
    - npx playwright install --with-deps chromium
    - npm run -w @asl-pilot/backend db:migrate
    - npm run db:seed
    - npx playwright test
```

---

## Quick reference — most-used URLs

- Project home: <https://labs.gauntletai.com/bryannalarcon/asl-detection-lessons>
- Access token settings: <https://labs.gauntletai.com/bryannalarcon/asl-detection-lessons/-/settings/access_tokens>
- Pipelines: <https://labs.gauntletai.com/bryannalarcon/asl-detection-lessons/-/pipelines>
- Issues: <https://labs.gauntletai.com/bryannalarcon/asl-detection-lessons/-/issues>
- Merge requests: <https://labs.gauntletai.com/bryannalarcon/asl-detection-lessons/-/merge_requests>
- Repository: <https://labs.gauntletai.com/bryannalarcon/asl-detection-lessons/-/tree/main>
- API root: <https://labs.gauntletai.com/api/v4/projects/949>

---

## Important: do NOT push while build agents are running

This repo uses the build-then-review swarm pattern (see `CLAUDE.md` §"Swarm pattern" and `docs/handoffs/HANDOFF_FRONTEND.md` §"Development workflow"). When swarm agents are mid-refactor, files are in inconsistent states. **Wait for the swarm to complete + the review swarm to greenlight before pushing.**

If `TaskList` shows any pending or in-progress build tasks, finish them first.

---

## Gitignore additions specific to this project

The synthesis-clone-SB `.gitignore` blanket-ignores root-level markdown (`/*.md`) and allowlists `README.md`. For `asl-learning` we want to track more docs (CLAUDE, GITLAB), so the rule should look like:

```
# Track these root markdown files explicitly
/*.md
!/README.md
!/CLAUDE.md
!/GITLAB.md

# Large artifacts
ASL_Citizen.zip
screenshots/
results/
playground/
ruvector.db
google_iso_1st_place.md
superbuilders-partner-project-asl-learning-with-computer-vision.pdf

# Generated
design/extracted/

# Local orchestrator state
.claude/
.swarm/
.codex/

# Standard
node_modules/
.env*
!.env.example
dist/
build/
.next/
playwright-report/
test-results/
*.log
```

Verify with `git check-ignore -v <path>` before the first `git add -A`.
