"""Public status page API — distinguishes platform vs client issues."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

router = APIRouter(tags=["Status"])


@router.get("/status")
@router.get("/api/status")
async def public_status(request: Request):
    """
    Public health summary for status.leveragefx.co / website status page.
    If this responds, the API process is up. Component checks are best-effort.
    """
    now = datetime.now(timezone.utc).isoformat()
    components = {
        "api": {"status": "operational", "detail": "process up"},
        "database": {"status": "unknown", "detail": ""},
        "redis": {"status": "unknown", "detail": ""},
    }
    overall = "operational"

    # DB
    try:
        from app.db.base import engine
        from sqlalchemy import text

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        components["database"] = {"status": "operational", "detail": "ping ok"}
    except Exception as e:
        components["database"] = {"status": "degraded", "detail": type(e).__name__}
        overall = "degraded"

    # Redis
    try:
        jq = getattr(request.app.state, "job_queue", None)
        if jq is not None:
            client = jq.get_redis_client()
            await client.ping()
            components["redis"] = {"status": "operational", "detail": "ping ok"}
        else:
            components["redis"] = {"status": "unknown", "detail": "not initialized"}
    except Exception as e:
        components["redis"] = {"status": "degraded", "detail": type(e).__name__}
        overall = "degraded"

    return {
        "service": "AEGIS",
        "overall": overall,
        "checked_at": now,
        "components": components,
        "notes": [
            "If this page loads but the mobile app fails, check API key, Server URL, and phone network.",
            "Render free-tier cold starts can cause temporary timeouts — retry after 30–60s.",
        ],
    }
