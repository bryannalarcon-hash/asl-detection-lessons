# ASL Pilot

Browser-based ASL vocabulary practice for college ASL 1 learners. SuperBuilders partner project.

**Live app:** <https://asl-pilot-api-production.up.railway.app> — hosted on Railway (deploying shortly).

## Status

Scaffold milestone — feature work begins after the 16 acceptance criteria in [`docs/prd-scaffold.md`](./docs/prd-scaffold.md) all pass.

## Docs

- [`docs/prd-scaffold.md`](./docs/prd-scaffold.md) — scaffold milestone PRD (source of truth for the build)
- [`docs/principles.md`](./docs/principles.md) — pedagogy + design synthesis
- [`docs/ux-spec.md`](./docs/ux-spec.md) — pages, features, state machines
- [`docs/local-setup.md`](./docs/local-setup.md) — how to run locally
- [`docs/ml-handoff.md`](./docs/ml-handoff.md) — how the ML model integrates
- [`docs/training-plan.md`](./docs/training-plan.md) — ML training plan
- [`docs/hoyso-architecture.md`](./docs/hoyso-architecture.md) — Stage 2 architecture reference

### Submission deliverables

- [`docs/DATASET_AND_TRAINING.md`](./docs/DATASET_AND_TRAINING.md) — dataset + model-training process, evidence no pretrained models were used (deliverable 3)
- [`docs/VALIDATION_REPORT.md`](./docs/VALIDATION_REPORT.md) — accuracy targets, test conditions, known limitations (deliverable 4)
- [`docs/PRIVACY.md`](./docs/PRIVACY.md) — how camera/video data is handled (deliverable 7)
- [`docs/superbuilders/`](./docs/superbuilders/) — brand alignment
- [`docs/competitive/`](./docs/competitive/) — competitive teardowns

## Quick start

See [`docs/local-setup.md`](./docs/local-setup.md) for the full setup, including WSL2 prerequisites.

```bash
cp .env.example .env
docker compose up -d
npm install
npm run db:migrate
npm run db:seed
# Two terminals:
npm run dev:api    # backend on :3000
npm run dev        # frontend on :5173
```

Open <http://localhost:5173>, click **`[Dev: Skip login]`** on the sign-in page, land on the dashboard with the seeded dev account's 75 days of practice history.

## Repo layout

```
asl-learning/
├── docker-compose.yml      Local Postgres + Adminer
├── frontend/               React + Vite + Tailwind + shadcn/ui
├── backend/                Hono + Drizzle + Postgres
├── scripts/                Seed scripts + DB init
├── src/                    Python ML side (Stage 1 keypoint detector + Stage 2 classifier — separate from the web app)
└── docs/                   All planning + spec docs
```

## Notes

- The Python ML side (`src/`, `requirements.txt`) is separate from the web app — managed by the ML team per [`docs/training-plan.md`](./docs/training-plan.md).
- v1 has no real CV — the practice screen uses mock CV state buttons. See [`docs/ml-handoff.md`](./docs/ml-handoff.md) for the v2 integration path.
