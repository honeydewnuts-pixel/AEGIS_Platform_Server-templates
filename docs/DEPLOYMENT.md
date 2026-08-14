# Deployment Guide

## Prerequisites

- A Linux host (or VM) with Docker + Docker Compose installed, for the API/Postgres/Redis/observability stack
- A separate Windows machine/VM per concurrently-active MT5 account, with the real MT5 terminal installed, for `mt5_worker.py` (see `docs/ARCHITECTURE.md` for why this can't run on the same Linux host)
- Domain name + TLS certificate if this will be reachable from the public internet (nothing in this repo terminates TLS itself - put nginx/Caddy/a load balancer in front of it)
- Accounts with whichever payment provider(s) you're using (Paystack/Flutterwave/Stripe), in test/sandbox mode first

## 1. Configure secrets

```bash
cp .env.example .env
```

Fill in, in this order (each has a generation command in `.env.example`):

1. `AEGIS_MASTER_KEY` - do this first; losing this after real credentials are encrypted with it means those credentials become permanently undecryptable
2. `ADMIN_BOOTSTRAP_KEY` - or leave blank and copy the auto-generated one from the logs on first boot (only shown once)
3. `DATABASE_URL`, `REDIS_URL` - defaults work for the bundled docker-compose Postgres/Redis; change if pointing at managed services instead
4. Payment provider keys - use test/sandbox keys until you've verified the webhook flow end to end
5. `ALLOWED_ORIGINS` - your actual admin dashboard / client portal / any other frontend origins, not `*`

## 2. Bring up the stack

```bash
cd docker
docker-compose up --build -d
```

This starts, in dependency order (via healthchecks, not just container
start order - see `docker/docker-compose.yml`): Postgres, Redis, the API
(which runs `alembic upgrade head` automatically before starting),
Prometheus, Grafana, Loki, and Promtail.

Verify:
```bash
curl http://localhost:8000/          # should return service info
docker-compose logs aegis-api | grep "Admin API key"   # if you didn't set ADMIN_BOOTSTRAP_KEY
```

## 3. Set up observability

- Grafana: `http://localhost:3000` (default `admin`/`admin` - **change this immediately**, set via `GF_SECURITY_ADMIN_PASSWORD` in `docker-compose.yml` for anything beyond local testing). The "AEGIS Platform Overview" dashboard is pre-provisioned.
- Prometheus: `http://localhost:9090` - direct query access if you need it beyond Grafana
- Logs: Grafana -> Explore -> Loki datasource, or `docker-compose logs -f <service>` for anything ad hoc

## 4. Deploy MT5 workers

On each Windows machine:
```powershell
git clone <this repo>
cd backend
pip install -r ../requirements-worker.txt
```

Workers are spawned automatically by `WorkerPoolManager` when a
subscriber calls `/api/trading/connect` - you don't run
`mt5_worker.py` manually in normal operation. What you do need to set up
per Windows machine:
- The real MT5 terminal, installed and able to log in
- Network access to the same Redis instance the API uses
- `REDIS_URL` in that machine's environment pointing at it

**Current constraint** (see `worker_pool_manager.py`'s module docstring):
worker spawning is local-subprocess-based, tied to a single API instance
for now. This means MT5 workers currently need to run on the same
machine(s) the API's `WorkerPoolManager` can reach via `subprocess.Popen`
- true remote dispatch to a separate Windows fleet is the documented next
architectural step, not yet implemented.

## 5. Deploy the mobile app

See `mobile_app/README.md` for the build itself. For distribution:
gate the APK behind `/api/download/apk` (already implemented) rather than
attempting Play Store/App Store distribution - see that same README for
why those stores are unlikely to accept this app's core functionality.

## 6. Set up payment webhooks

Point each provider's webhook configuration at
`https://your-domain.com/api/subscriptions/webhook/{provider}`. Test with
each provider's sandbox/test-mode webhook simulator before going live -
`docs/SECURITY.md` and the payment adapter files themselves flag that
this integration was built from documented specs, not verified against a
live provider from this development environment.

## 7. Before real subscribers touch any of this

Read `README.md`'s "Before this goes anywhere near real subscribers"
section and `docs/SECURITY.md`'s "Known gaps" section. Neither is
boilerplate - they list specific, concrete things (rate limiting, TLS
termination, backup strategy, portal token/API key delivery mechanism)
that are genuinely not done yet.

## Rolling back a bad deploy

```bash
docker-compose down
git checkout <previous-known-good-tag>
docker-compose up --build -d
```

Database migrations are forward-only as configured (`alembic upgrade
head` on every boot) - if a bad migration shipped, you'll need
`alembic downgrade -1` run manually against that Postgres instance before
rolling the application code back, not just a `git checkout`.

## Phone-only testing path (no PC/Mac)

`render.yaml` at the repo root deploys just the core three services
(API + Postgres + Redis, skipping the observability stack) via Render's
free tier, entirely through their web dashboard - no CLI required:

1. render.com → New → Blueprint → connect this GitHub repo
2. Fill in the secret values Render prompts for (`AEGIS_MASTER_KEY`,
   `ADMIN_BOOTSTRAP_KEY`, etc. - see comments in `render.yaml`)
3. Watch the deploy log in the dashboard (also viewable from a phone
   browser) for the admin key line on first boot

For the mobile app: download the APK artifact directly from the GitHub
Actions run (Actions tab → workflow run → Artifacts), extract, and
sideload-install - no PC needed, and this is the correct test
environment regardless, since the app needs a real phone with real
sensors and a real MT5 install.

**Not covered by this path:** MT5 trade execution, which requires a
Windows machine (see `docs/ARCHITECTURE.md` for why). A cheap Windows
VPS + the free Microsoft Remote Desktop Android app lets you control
that machine from your phone too, once you're past testing capture/
analyze and ready to test execution.
