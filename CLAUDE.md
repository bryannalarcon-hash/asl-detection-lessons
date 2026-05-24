# ASL Pilot — agent instructions

This file is auto-loaded by Claude Code in every session for this project.
It overrides the global `~/CLAUDE.md` where they conflict.

For *current codebase state* (what's built, what works, gotchas), read
the latest handoff in `docs/handoffs/` (currently `HANDOFF_NET3_V2.md`
for ML training, `HANDOFF_FRONTEND.md` for the pilot app). This file is
the **invariant doctrine** — how to work, not what's been done.

---

## Commit cadence

**Commit after each change. The agent decides timing.**

- **Major changes commit immediately** — feature adds, schema migrations,
  security fixes, design overhauls, dependency bumps, anything touching
  more than 5 files, or anything that changes user-visible behavior. One
  concept = one commit.
- **Minor changes can be batched** — typos, lint nits, comment rewording,
  tiny refactors. Up to ~5 batched into one `chore: misc cleanups` commit.
- **Never batch across concerns.** Feature work and unrelated cleanup go
  in separate commits even if both are small.
- **After a build-then-review swarm:** commit only when the review swarm
  is green. Mid-swarm state is inconsistent.
- **Never `--no-verify`, never `--amend`.** Fix hook failures and create
  new commits.

Commit message format: imperative present tense, under 72-char subject,
blank line, body paragraphs describing *why*. When I authored, add trailer:
```
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Push cadence

- After a major-tier commit lands and tests are green, push.
- After a batch of minor commits, push at the end of the batch.
- Never force-push to `main`. Never push during a swarm.

---

## Swarm pattern (build → review → loop)

For any feature add larger than a 1-2 line fix:

**Phase A — Build swarm.** Spawn one named coder per concern in a single
message (`run_in_background: true`, all named). Express dependencies via
SendMessage in each prompt. Pause for status updates between phases.

**Phase B — Review swarm.** After build agents complete, spawn `reviewer`
+ `tester` (+ `security-auditor` when auth/perms/secrets touched).
Consolidate findings.

**Loop.** If review flags failures, dispatch a fix swarm targeting only
the failures, then re-run review. Repeat until the **original
user-level acceptance criteria** are met (manual UX walk + Playwright
green + curl smoke). Not just "agents say done."

Skip the swarm for: 1-2 line fixes, doc edits, config flips.

Acceptable subagent_types: `coder`, `backend-dev`, `reviewer`, `tester`,
`security-auditor`, `system-architect`, `researcher`. **Not valid:**
`frontend-dev` (use `coder`).

---

## Prod-deploy preconditions (hard requirements)

Before any non-localhost deploy of this project, set ALL of:

1. `DEV_TOOLS_ENABLED=0` (backend env) — disables `POST /api/auth/dev-login` (404s).
2. `VITE_DEV_TOOLS=0` (frontend build env) — hides `[Dev: …]` UI and (via Vite `define` + DCE) drops the dev-account credentials from the JS bundle.
3. Don't run `npm run db:seed` against the prod DB — the dev password is shared and known.
4. Update `backend/src/lib/cors.ts` allow-list from hardcoded `http://localhost:5173`.
5. Flip session-cookie `secure: false` to `true` (currently dev-only) in `backend/src/lib/session.ts`.

---

## Style invariants

- **Tests** must pass before any commit lands.
- **No emojis** in code, comments, or commit messages.
- **No comments referencing the task that produced them** ("added for X", "fixes Y", "Foundry Aurora pass").
  Comments explain *why*, not *what* or *when*.
- **Files under 500 lines** — break into sub-components when approaching.
- **Read files before editing them.**
- **Never commit secrets** — `.env.local`, dataset zips, screenshots, venvs are gitignored.
- **Validate user input at system boundaries** only. Trust internal calls.
- **Don't add abstractions for hypothetical future requirements.** Three
  similar lines is better than a premature abstraction.

---

## Pointers (for current state, not doctrine)

- `docs/handoffs/` — session handoffs (latest = `HANDOFF_NET3_V2.md`); frontend state in `HANDOFF_FRONTEND.md`
- `GITLAB.md` — repo URL, token handling, push procedure, gitignore rules
- `docs/principles.md` — pedagogy + UX principles (research synthesis)
- `docs/ux-spec.md` — 23-route UX spec + state machine + dev scaffolding
- `docs/ml-handoff.md` — CV black-box interface contract
- `docs/prd-scaffold.md` — scaffold-milestone PRD
- `design/extracted/design_handoff_asl_pilot/` — Foundry · Aurora design package (gitignored — unzip from `design/asl-pilot.zip` when needed)

---

## Auto-memory hooks

The auto-memory system at `~/.claude/projects/-home-bryann-gauntlet-asl-learning/memory/`
holds Bryann's preferences and project context.

Most important memory entries (loaded via `MEMORY.md` index):

- `feedback_terse_responses` — short answers, no ceremony
- `feedback_explicit_dev_scaffolding` — labeled `[Dev: …]` overrides over silent mocks
- `feedback_agent_swarms` — willing to spawn many parallel agents; expects status updates
- `feedback_swarm_build_then_review` — the loop pattern above
- `feedback_commit_cadence` — the cadence above
- `feedback_triangulated_research` — for non-trivial research, run primary → fact-check → tertiary

Update these when Bryann gives new direction. Don't reference them at users
unless asked.
