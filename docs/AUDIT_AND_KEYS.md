# Audit subsystem & API key lifecycle

## Audit events (`audit_events`)

Append-only. Actions include:

| Action | When |
|--------|------|
| `key.issue` | Admin issues client or admin key |
| `key.revoke` | Admin revokes a key |
| `key.rotate` | Admin rotates (new key + revoke old) |
| `key.force_rotate` | Admin marks key must-rotate |

Query: `GET /api/admin/audit?limit=100&action=key.issue&account_id=ACC-…`

Fields: actor_type, actor_id, actor_label, action, target_*, account_id, detail, ip, success, created_at.

## Key lifecycle

| Field | Meaning |
|-------|---------|
| `expires_at` | Hard reject after this time (401) |
| `rotation_due_at` | Soft schedule marker (does not block by default) |
| `force_rotate` | Hard reject until rotated (401) |

Defaults (env):

- `API_KEY_DEFAULT_TTL_DAYS` = 365 (0 = never)
- `API_KEY_ROTATION_DAYS` = 90 (0 = none)

Endpoints:

- `POST /api/admin/keys/issue` — optional `expires_in_days`, `rotation_days`
- `POST /api/admin/keys/{id}/revoke`
- `POST /api/admin/keys/{id}/force-rotate`
- `POST /api/admin/keys/rotate` — body `{ "key_id": N }` returns new raw key once
- `GET /api/admin/keys` — list metadata (no secrets)

## Upload diagnostics

Table `upload_diagnostics` records every `/aegis/analyze` attempt:

- success, http_status, latency_ms, image_bytes, error_code

APIs:

- `GET /api/admin/uploads/recent?limit=100`
- `GET /api/admin/uploads/trends?hours=24`
- `GET /api/admin/uploads/latency?limit=100`

Mobile keeps a **local** ring buffer of the last 100 attempts (shown on the diagnostics panel with fail rate and avg latency).
