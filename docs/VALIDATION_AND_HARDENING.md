# Validation boundaries & production hardening

## What static review / unit tests can confirm

| Area | Status |
|------|--------|
| Plan catalog (devices / trades / live flag) | Unit tested |
| API key expiry & force-rotate enforcement | Unit tested (mocked DB) |
| Admin route auth gates | Router tests with TestClient |
| Account rate limit code path | Wired on `/aegis/analyze` |
| Audit retention job | Daily purge (`AUDIT_RETENTION_DAYS`) |
| Key expiration | Enforced in `verify_api_key` |

Run offline unit tests:

```bash
cd backend  # or repo root with pythonpath=backend
pip install -r ../requirements.txt -r ../requirements-dev.txt
pytest tests/test_plan_catalog.py tests/test_security_lifecycle.py -q
# Full suite needs more deps; router tests need FastAPI TestClient:
pytest tests/ -q --ignore=tests/load
```

Coverage percentage is **not** claimed until you run `pytest --cov=app` in CI against this tree.

## What requires a live environment (cannot verify here)

| Area | How to validate |
|------|-----------------|
| Integration tests (Postgres + Redis) | Staging compose + pytest markers |
| Load 100 / 1k / 10k clients | `tests/load/bench_analyze.py`, then k6/Locust |
| Horizontal API replicas | 2+ Render instances, shared Redis registry |
| Multi-broker MT5 | Windows workers per broker demo accounts |
| Live execution / failover | Controlled demo account, kill worker, ensure reconnect |
| WAF | Put Cloudflare / AWS WAF / nginx in front; not in-app |

## Horizontal scaling checklist

1. API: multiple instances OK for **brain analyze** (stateless + Redis history).
2. `WorkerPoolManager`: local subprocess workers are **per instance**; production scale uses remote Windows workers on shared Redis (see module docstring).
3. `MAX_CONCURRENT_WORKERS` is per host; raise via env.
4. Postgres + Redis managed services with connection pooling.
5. Rate limit uses Redis when available so limits are global across replicas.

## Security hardening shipped

- Per-account rate limit (`API_RATE_LIMIT_PER_MINUTE`, default 120)
- Key TTL / force rotate / expiry hard-fail
- Audit + upload diagnostic retention (`AUDIT_RETENTION_DAYS`, default 90)
- Admin-only tenant/key routes
- Download tokens + device binding

Still recommended outside the app: TLS termination, WAF, secrets manager, network policies, backup/PITR for Postgres.
