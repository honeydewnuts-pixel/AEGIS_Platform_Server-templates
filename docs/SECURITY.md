# Security

## Authentication & Authorization

**Authentication:** every request (except payment webhooks and the
pre-subscription checkout endpoint - see below) requires an `X-API-Key`
header. Keys are stored as SHA-256 hashes in the `api_keys` table, never
in plaintext - reading the table doesn't hand out usable credentials.

**Authorization:** this is the part that's easy to get wrong and was, in
fact, wrong in an earlier version of this codebase. Authentication alone
("is this a real AEGIS key") is not authorization ("is this key allowed
to touch *this* account"). Every key is bound to exactly one
`account_id` (or `is_admin=True` for operator/service keys), and every
endpoint that takes an `account_id` calls `require_account_match(auth,
account_id)` before doing anything - a subscriber's key can only ever
act on their own account, regardless of what `account_id` they put in
the request. Fleet-wide endpoints (`/api/devices/health`,
`/api/subscriptions`, `/api/admin/summary`) require `is_admin=True` via
`require_admin(auth)`.

**Why this matters specifically for a mobile app:** API keys embedded in
a distributed APK are not really secret - anyone can decompile the app
and extract the key. Under a shared-key model (which this codebase used
earlier), extracting the key from your own app would grant access to
*every* subscriber's account. Under the current per-account model,
extracting a key only grants access to the one account it was issued to
- which that person could already control anyway (it's their own
account). This is the actual security boundary that matters here, not
"can the key be extracted" (assume yes, always, for anything embedded in
a mobile client).

## Secrets

See `docs/SECRETS.md` for the full breakdown of what's stored where and
how. Summary: environment-variable-based, `.env` excluded from git/docker
build context, broker credentials AES-256-GCM encrypted at rest, API keys
hashed at rest, portal tokens stored plaintext (documented tradeoff, see
that doc).

## Dependency vulnerabilities

`pip-audit` runs in CI on every push to `requirements*.txt` and weekly on
a schedule (`.github/workflows/backend-ci.yml`) - this actually executes
against live vulnerability databases on GitHub's runners, which this
development environment could not do (no network access). Treat a CI
failure from this step as blocking, not advisory.

No equivalent exists yet for the mobile app's Gradle dependencies -
consider adding `./gradlew dependencyCheckAnalyze` (OWASP Dependency-Check
Gradle plugin) to `mobile-ci.yml` once the Gradle wrapper situation is
resolved (see `mobile_app/README.md`).

## Known gaps (not fixed, flagged deliberately rather than silently left)

- **No rate limiting anywhere.** `/api/subscriptions/checkout/{provider}`
  is the most exposed (no auth required, by necessity - see that
  endpoint's docstring), but nothing stops repeated calls to any endpoint.
  Add `slowapi` or handle it at your reverse proxy before this is public.
- **CORS `allow_credentials=True` with a configured origin list** - fine
  as configured (an explicit allowlist, not `*`), but re-verify
  `ALLOWED_ORIGINS` in `.env` is actually restricted to real frontend
  origins before deploying, not left at the `.env.example` default.
- **No WAF / DDoS protection** - this is infrastructure, not application
  code (Cloudflare, AWS Shield, etc., sit in front of the load balancer).
- **No security headers middleware** (HSTS, X-Content-Type-Options,
  etc.) - typically added at the reverse proxy layer (nginx/Caddy) rather
  than in FastAPI, but flagging since nothing here or in the proxy config
  (there is no proxy config - see `docs/DEPLOYMENT.md`) currently sets
  these.
- **Portal token and mobile API key delivery has no channel.** Both are
  currently only written to application logs on first subscription
  activation (see `subscription_service.py`). There is no email/SMS/in-app
  delivery mechanism - you must build this before real subscribers can
  actually receive their credentials. Treat "it's in the logs" as a
  development-only stopgap, not a delivery mechanism, since production
  log access shouldn't be how subscribers get their own credentials.

## File-by-file audit notes (security-relevant subset)

The full engineering audit touched every file in `backend/app/` for
syntax validity, import resolution, and async/await correctness (see CI,
which now also runs this class of check via `pip-audit` and `ruff`).
Security-specific findings from that pass, beyond the authorization
rewrite above:

| File | Finding | Status |
|---|---|---|
| `services/broker_connection_service.py` | Missing `await` on a credential lookup call | Fixed - this class is currently dead code (never wired to a router), so it was a latent bug, not an active one |
| `core/metrics.py` | `aegis_subscriptions_active` gauge was defined but never actually set - would show 0 forever on any dashboard | Fixed |
| `config.py` | `DEBUG` defaulted to `True` and wasn't wired to anything | Fixed - defaults `False`, wired into `FastAPI(debug=...)` |
| `docker/Dockerfile` | Container ran as root, no `USER` instruction | Fixed - runs as a dedicated non-root user |
| `docker/docker-compose.yml` | Postgres/Redis ports published to `0.0.0.0` | Fixed - bound to `127.0.0.1` |
| repo root | No `.gitignore` - `.env` had no guard against being committed | Fixed |
