# Ops: recovery, keys, scaling, uptime

## Lost admin API key (Render)

1. In Render → web service → Environment, set:
   - `ADMIN_BOOTSTRAP_KEY` = a long random secret you choose (e.g. 32+ chars)
   - `FORCE_ADMIN_KEY_RESET` = `true`
2. Redeploy / restart the service.
3. Log in to `/admin` with that bootstrap value as the API key.
4. Set `FORCE_ADMIN_KEY_RESET` back to `false` and save.

Alternatively call (once you have *any* valid admin path) or use the bootstrap sync:
if `ADMIN_BOOTSTRAP_KEY` is set and no matching key exists, startup registers it as an extra admin key without wiping others.

## Issue per-client mobile keys

```bash
curl -X POST https://YOUR.onrender.com/api/admin/keys/issue \
  -H "X-API-Key: ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"account_id":"ACC-CLIENT01","label":"phone-1"}'
```

Response includes `account_id` + `api_key` (shown once). Enter both in the mobile app Settings.

Omit `account_id` to auto-generate one (`ACC-…`).

## Worker capacity (100 → 100k+)

- Env `MAX_CONCURRENT_WORKERS` (default **100**) caps local subprocess workers on one API host.
- Brain analysis (`/aegis/analyze`) does **not** require MT5 on the server — only screenshots + rulebook.
- Server-side MT5 execution is optional and Windows-only; one terminal can serve testing; production scale uses many Windows workers all sharing Redis (see `worker_pool_manager.py`).

## Uptime monitoring

- Render health check: `/health` (process + Redis ping).
- External: UptimeRobot / Better Stack / Cronitor hitting `GET /health` every 1–5 minutes (also keeps free-tier warm).
- Self-hosted: Prometheus + `docker/prometheus/alerts.yml` + Grafana.

## Environment variables recognized on Render

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Postgres (auto from blueprint) |
| `REDIS_URL` | Redis (auto from blueprint) |
| `AEGIS_MASTER_KEY` | Credential encryption |
| `ADMIN_BOOTSTRAP_KEY` | Admin API key material |
| `FORCE_ADMIN_KEY_RESET` | One-shot admin key reset |
| `SECRET_KEY` | App secret |
| `DEBUG` | FastAPI debug (keep false) |
| `ALLOWED_ORIGINS` | CORS |
| `MAX_CONCURRENT_WORKERS` | Worker pool size |
| Payment keys | Optional until billing goes live |
