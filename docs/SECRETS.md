# Secrets Management

## Current state

Every secret in this codebase is read from environment variables via
`app/config.py` (pydantic-settings), sourced from a `.env` file locally or
your orchestrator's env injection in deployment. Nothing is hardcoded in
source. `.gitignore`/`.dockerignore` both exclude `.env`.

**Secrets in play:**

| Secret | Purpose | Where it's used |
|---|---|---|
| `AEGIS_MASTER_KEY` | Encrypts broker credentials at rest (AES-256-GCM) | `credential_vault_service.py` |
| `ADMIN_BOOTSTRAP_KEY` | Seeds the first admin API key | `core/startup.py` |
| `SECRET_KEY` | Reserved, not currently used for anything - see note below | `config.py` |
| `PAYSTACK_SECRET_KEY` / `FLUTTERWAVE_SECRET_KEY` / `FLUTTERWAVE_WEBHOOK_HASH` / `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` | Payment provider auth + webhook signature verification | `services/payment_providers/` |
| `DATABASE_URL` | Postgres connection string (includes the DB password) | `db/base.py` |
| Per-account API keys, portal tokens | Subscriber authentication | Generated at runtime, stored hashed (API keys) or plain (portal tokens - see note below) in Postgres |

**Note on `SECRET_KEY`:** this was carried over from the original scaffold
and isn't actually wired into anything right now (no session/JWT signing
uses it). Either remove it or wire it in if you add session-based auth
later - leaving unused secrets in config is its own small risk (one more
value to accidentally leak for no benefit).

**Note on portal tokens:** unlike API keys (hashed) and broker credentials
(AES-GCM encrypted), `Subscription.portal_token` is stored in plaintext in
Postgres. This was a deliberate tradeoff - the client portal needs to
*display* or *email* this token to the subscriber, which a one-way hash
would prevent. If this bothers you for defense-in-depth reasons, the fix
is application-level encryption (not hashing) so it can still be decrypted
for display, at the cost of needing the master key to read it back.

## What this is NOT (and what "real" secrets management would add)

This is environment-variable-based secrets management - fine for a single
operator running their own deployment, not a full secrets management
system. It's missing:

- **Rotation without downtime.** Rotating `AEGIS_MASTER_KEY` today means
  every previously-encrypted credential becomes undecryptable the moment
  you change it, unless you write a migration that decrypts-with-old-key
  then re-encrypts-with-new-key for every row first. No such migration
  exists yet.
- **Audit trail of who accessed which secret when.** Env vars give you
  nothing here - a real secrets manager (Vault, AWS Secrets Manager, GCP
  Secret Manager) logs every read.
- **Automatic injection without ever touching disk.** `.env` files sit on
  disk in plaintext (permissions aside) wherever they're deployed.
- **Centralized revocation across multiple servers.** If you ever run more
  than one API instance, updating a secret means updating `.env` (or your
  orchestrator's secret store) on every instance and restarting all of
  them - there's no push-based propagation.

## Recommended next step, when you're ready

Swap `app/config.py`'s `pydantic-settings` env-var loading for a thin
adapter that fetches from a real secrets manager instead - AWS Secrets
Manager, GCP Secret Manager, HashiCorp Vault, or even something lighter
like Doppler or Infisical, depending on where you deploy. Because every
secret is already centralized in one `Settings` class rather than scattered
`os.getenv()` calls throughout the codebase, this is a contained change:
one file, not a search-and-replace across the whole app.
