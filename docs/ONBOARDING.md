# Developer Onboarding

## Before you touch anything

Read these two, in order - they'll save you from re-discovering problems
that are already documented:

1. `README.md` - "Known Limitations" and "Deployment checklist" sections
2. `docs/ARCHITECTURE.md` - the two-different-scaling-problems split is
   the single most important thing to understand before changing anything
   in `worker_pool_manager.py`, `job_queue_service.py`, or `mt5_worker.py`

## Local setup

```bash
git clone <this repo>
cd AEGIS_Platform
cp .env.example .env
# fill in AEGIS_MASTER_KEY at minimum (see .env.example for the
# generation command) - the app refuses to start without it

cd docker
docker-compose up --build
```

Backend API: `http://localhost:8000/docs` (interactive API explorer)
Admin dashboard: `http://localhost:8000/admin`
Client portal: `http://localhost:8000/portal`
Grafana: `http://localhost:3000` (admin/admin, change immediately)

## Running tests

```bash
pip install -r requirements-dev.txt
pytest -v
```

Tests cover what's genuinely testable without live infrastructure: the
rule engine's crossing/divergence primitives, payment webhook signature
verification, and credential encryption roundtrips. They do **not** cover
anything requiring a real MT5 terminal, real payment provider API calls,
or a real Android build - those need actual staging infrastructure (see
`README.md`).

## Where things live

See `docs/ARCHITECTURE.md`'s module map, and each subproject's own
README (`backend/README.md`, `mobile_app/README.md`) for more detail
than fits here.

## Conventions used throughout this codebase

- **Every non-obvious decision has a comment explaining why, not just
  what.** If you're about to add a `# TODO` or change something that
  looks wrong at first glance, check for a comment above it first - it
  might be a deliberate tradeoff with the reasoning already written down
  (e.g. why portal tokens are stored plaintext while API keys are hashed).
- **Async all the way through the backend.** If you add a new service
  method, it should be `async def` and use the existing `async_session_factory`
  pattern from `app/db/base.py` for DB access, not a new sync connection.
- **Authorization is explicit, not implicit.** Every endpoint that takes
  an `account_id` calls `require_account_match(auth, account_id)`
  directly in the function body - see `docs/SECURITY.md` for why this
  isn't a single combined FastAPI dependency instead.
- **New migrations go in `backend/alembic/versions/`**, numbered
  sequentially (`0004_...`), with both `upgrade()` and `downgrade()`
  implemented - not just the direction you need right now.

## Before you open a PR

- [ ] `pytest -v` passes locally
- [ ] `ruff check backend/app` doesn't introduce new syntax-level issues
- [ ] If you touched `db/models.py`, there's a matching Alembic migration
- [ ] If you touched an endpoint that takes `account_id`, it has
      `require_account_match` (or `require_admin` if it's genuinely
      fleet-wide) - CI doesn't currently catch a missing authorization
      check automatically, so this is on you to verify
- [ ] If you added a new required env var, it's in `.env.example` with a
      comment explaining what it's for

## Who to ask

This codebase was built through an extended iterative process with an AI
assistant (Claude) rather than a traditional team - there's no
institutional "ask Sarah, she wrote that" fallback. The comments and
`docs/` folder are the closest equivalent; if something is genuinely
undocumented and unclear, that's a gap worth filing an issue for rather
than assuming there's tribal knowledge elsewhere to find.
