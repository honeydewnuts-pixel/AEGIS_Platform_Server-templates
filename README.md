# AEGIS Platform

Autonomous screenshot-to-signal analysis and MT5 trade execution platform.
Company: Honeydewnuts Nigerian Limited.

## Layout

```
backend/           FastAPI API - see backend/README.md
mobile_app/        Android app - see mobile_app/README.md
admin_dashboard/   Operator-facing web dashboard (static, served by the API at /admin)
client_portal/     Subscriber-facing self-service page (static, served at /portal)
docker/            Dockerfile, docker-compose.yml, Prometheus config
tests/             pytest suite (rule engine, payment signatures, encryption)
alembic/           lives inside backend/ - DB migrations
.github/workflows/ CI: backend tests + Docker build, mobile Gradle build
```

## Quick start

```bash
cp .env.example .env
# fill in SECRET_KEY, API_KEYS, AEGIS_MASTER_KEY, payment provider keys

cd docker
docker-compose up --build
```

This brings up the API (with migrations run automatically), Postgres,
Redis, and Prometheus. Once running:

- API docs: `http://localhost:8000/docs`
- Admin dashboard: `http://localhost:8000/admin` (needs a backend URL + an
  `API_KEYS` value to log in)
- Client portal: `http://localhost:8000/portal` (needs an account ID +
  portal token - generated automatically the first time an account's
  subscription activates; show it on your checkout success page or email
  it)
- Prometheus: `http://localhost:9090`
- Metrics: `http://localhost:8000/metrics`

MT5 workers run separately, on Windows - see `backend/README.md`.

## Before this goes anywhere near real subscribers

Read `backend/README.md`'s "Known Limitations" section in full. The short
version: nothing in this repo has been executed end-to-end (no internet
access in the environment this was built in - no Android SDK, no live MT5
terminal, no real payment provider keys, no way to `pip install` and run
`pytest`). Every piece has been statically verified as thoroughly as
that allows - syntax, cross-file field matching, import resolution,
async/await correctness - but a real staging pass with an actual test
device, a demo MT5 account, and provider sandbox keys is the honest
remaining step before launch, not optional.

## What's genuinely new in this checkpoint vs. the previous delivery

- Monorepo structure (was two separate zips)
- Postgres + SQLAlchemy + Alembic migrations, replacing the earlier
  SQLite-file-per-service approach (fixes a real multi-instance bug)
- pytest suite for the parts that are testable without live infra
- GitHub Actions CI for both backend and mobile
- `/metrics` (Prometheus) with custom fleet-health gauges
- Admin dashboard and client portal, both functional static web apps
  served directly by the FastAPI app (no separate frontend deploy needed)
- Client-portal authentication (account ID + portal token) - new, since
  none existed before; documented as a foundation, not full subscriber
  account management (no password reset flows, no email delivery wired up)

## Known gaps still open (not silently dropped, just not done yet)

- No email delivery anywhere (portal tokens, receipts, alerts) - you'll
  want to wire in a transactional email provider
- Admin dashboard has no auth beyond the shared API key - fine for you
  personally, not fine for a multi-admin team without upgrading it
- `CandlestickDetectionService` / `VisionPipelineService` dead code from
  the original repo - still there, still unwired, still awaiting your
  call on keep-vs-remove

## Deployment checklist

**Fixed in this pass (real gaps, not cosmetic):**
- `docker-compose.yml` had a startup race condition - the API container
  would try to run migrations against Postgres before Postgres was
  actually ready to accept connections, not just started. Now uses
  healthchecks + `condition: service_healthy`.
- Postgres/Redis ports were published to `0.0.0.0` (reachable from
  outside the host). Now bound to `127.0.0.1` only - still reachable
  from your own machine's DB tools, not from the public internet.
- `DEBUG` defaulted to `True` and, separately, was never actually wired
  into the FastAPI app at all - dead config giving false confidence
  either way. Now defaults to `False` and is properly passed through
  (`debug=settings.DEBUG` in `main.py`), since `debug=True` leaks full
  tracebacks in HTTP error responses if left on anywhere reachable by
  someone other than you.
- Docker image ran as root - no `USER` instruction existed. Now runs as
  a dedicated non-root user.
- No `.gitignore` existed at all - meaning a real `.env` with real
  secrets had no guard against being committed. Added, along with
  `.dockerignore` to keep the build context clean.

**Still genuinely open - these need a human with real access, not more code:**
- Nothing here has been executed even once (see "Before this goes
  anywhere near real subscribers" above) - a real staging pass with
  actual `docker-compose up`, a demo MT5 account, and provider sandbox
  keys is the honest remaining step.
- No TLS/reverse proxy config - this Dockerfile serves plain HTTP on
  8000. Put nginx/Caddy/a load balancer in front of it with a real
  certificate before any of this touches the public internet - broker
  credentials should never travel over plain HTTP.
- No backup strategy configured for the Postgres volume - `postgres-data`
  is a Docker named volume, which survives container restarts but not
  host loss. Set up `pg_dump` on a schedule (or your cloud provider's
  managed Postgres backups) before this holds real subscriber data.
- No log aggregation - container logs go to stdout/Docker's default
  driver only. Fine for `docker logs`, not fine for debugging a fleet
  of workers across machines - point them at something centralized
  (CloudWatch, Loki, etc.) once you have more than one worker machine.
- Regulatory/compliance review, as flagged before, is unchanged and
  still outstanding.
