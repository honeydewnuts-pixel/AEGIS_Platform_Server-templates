# API Reference

**Live, always-current reference:** `GET /docs` (Swagger UI) or `GET
/redoc` on any running instance - FastAPI generates these automatically
from the actual route definitions and Pydantic schemas, so they can never
drift out of sync with the code the way a hand-written reference can. This
document is a map of what exists and how auth applies to each area; for
exact request/response schemas, use the live docs.

## Authentication

Every endpoint below except where noted requires an `X-API-Key` header.
See `docs/SECURITY.md` for the full authorization model. Short version:
a key is bound to one `account_id` (or is an admin key) - endpoints that
take an `account_id` parameter will reject requests where it doesn't
match the authenticated key's account, with `403 Forbidden`.

## Trading (`/api/trading`)

All require a per-account key matching the `account_id` in the request.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Check a specific account's MT5 worker connection |
| POST | `/connect` | Register broker credentials, start/reuse the account's MT5 worker |
| POST | `/disconnect/{account_id}` | Stop the account's MT5 worker |
| POST | `/market-order` | Execute a market order |
| POST | `/pending-order` | Place a pending order |
| POST | `/modify-position` | Modify SL/TP on an open position |
| POST | `/close-position` | Close an open position |
| POST | `/cancel-order/{account_id}/{ticket}` | Cancel a pending order |
| GET | `/account` | Account balance/equity/margin |
| GET | `/positions` | Open positions |
| GET | `/orders` | Pending orders |
| GET | `/symbol/{account_id}/{symbol}` | Symbol info (spread, digits, etc.) |

## Brain / Vision Analysis

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/aegis/analyze` | Per-account key | Screenshot in, signal out. Requires `account_id` and `captured_at_ms` form fields alongside the image. |

## Subscriptions (`/api/subscriptions`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/checkout/{provider}` | **None** (see endpoint docstring - no key exists yet for a brand-new subscriber) | Create a payment provider checkout session. `provider` is `paystack`, `flutterwave`, or `stripe`. |
| POST | `/webhook/{provider}` | Provider signature, not API key | Payment provider webhook receiver |
| GET | `/status/{account_id}` | Per-account key | Subscription status for one account |
| GET | `` (list) | **Admin key required** | Every subscription, for the admin dashboard |

## Devices (`/api/devices`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/heartbeat` | Per-account key | Mobile app reports battery/capture-health status |
| GET | `/health/{account_id}` | Per-account key | One device's latest heartbeat |
| GET | `/health` (list) | **Admin key required** | Every device's status, for the admin dashboard |

## Admin (`/api/admin`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/summary` | **Admin key required** | Aggregate counts for dashboard cards |

## Client Portal (`/api/portal`)

Deliberately **not** behind `X-API-Key` / the admin-vs-per-account model
above - subscribers authenticate with `account_id` + `token` (their
`portal_token`, separate from their mobile API key) as query parameters
instead. See `portal_router.py`'s module docstring for why.

| Method | Path | Purpose |
|---|---|---|
| GET | `/status?account_id=&token=` | Subscription status |
| GET | `/device?account_id=&token=` | Device health for this subscriber |
| GET | `/download-url?account_id=&token=` | Gated APK download link |

## Download

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/download/apk?account_id=` | None directly - gated by active subscription status instead | Serves the APK file |

## Observability

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/metrics` | None (see note) | Prometheus scrape endpoint |
| GET | `/` | None | Service info / liveness |

`/metrics` is intentionally not behind `X-API-Key` - this matches how
Prometheus scraping conventionally works (network-level access control,
i.e. your reverse proxy/firewall, rather than an application-level key).
Make sure it isn't reachable from the public internet in your deployment.
