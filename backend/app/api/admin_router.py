"""
Admin dashboard aggregates, key lifecycle, audit log, upload diagnostics.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.base import async_session_factory
from app.db.models import ApiKey
from app.security import (
    verify_api_key,
    require_admin,
    AuthContext,
    issue_api_key,
    revoke_api_key,
    force_rotate_key,
)

router = APIRouter(prefix="/api/admin", tags=["Admin"])


def _actor(auth: AuthContext) -> str:
    if auth.label:
        return auth.label
    if auth.key_id is not None:
        return f"key:{auth.key_id}"
    return "admin"


@router.get("/summary")
async def get_summary(request: Request, auth: AuthContext = Depends(verify_api_key)):
    require_admin(auth)
    from app.config import settings

    device_health = request.app.state.device_health
    subscription_service = request.app.state.subscription_service
    worker_pool = request.app.state.worker_pool

    devices = await device_health.list_all()
    subscriptions = await subscription_service.list_all()

    status_counts: dict[str, int] = {}
    for s in subscriptions:
        status_counts[s["status"]] = status_counts.get(s["status"], 0) + 1

    return {
        "devices": {
            "total": len(devices),
            "online": sum(1 for d in devices if d.get("status") == "online"),
            "offline": sum(1 for d in devices if d.get("status") == "offline"),
        },
        "subscriptions": {
            "total": len(subscriptions),
            "by_status": status_counts,
        },
        "active_workers_this_instance": worker_pool.active_worker_count(),
        "max_concurrent_workers": settings.MAX_CONCURRENT_WORKERS,
    }


@router.get("/signals/recent")
async def get_recent_signals(
    request: Request,
    limit: int = 40,
    auth: AuthContext = Depends(verify_api_key),
):
    require_admin(auth)
    return await request.app.state.signal_history.get_recent(min(limit, 200))


class IssueClientKeyRequest(BaseModel):
    account_id: str | None = None
    label: str | None = None
    expires_in_days: int | None = Field(default=None, description="Override default TTL; 0 = never")
    rotation_days: int | None = Field(default=None, description="Days until rotation_due_at; 0 = none")


@router.post("/keys/issue")
async def issue_client_key(
    body: IssueClientKeyRequest,
    request: Request,
    auth: AuthContext = Depends(verify_api_key),
):
    require_admin(auth)
    account_id = (body.account_id or "").strip() or f"ACC-{uuid.uuid4().hex[:10].upper()}"
    actor = _actor(auth)
    raw = await issue_api_key(
        account_id=account_id,
        is_admin=False,
        label=body.label or f"mobile key for {account_id}",
        issued_by=actor,
        expires_in_days=body.expires_in_days,
        rotation_days=body.rotation_days,
    )
    await request.app.state.audit_service.record(
        action="key.issue",
        actor_type="admin_key",
        actor_id=str(auth.key_id) if auth.key_id else None,
        actor_label=actor,
        target_type="api_key",
        target_id=account_id,
        account_id=account_id,
        detail=f"label={body.label or ''}",
        ip=request.client.host if request.client else None,
    )
    return {
        "account_id": account_id,
        "api_key": raw,
        "label": body.label,
        "note": "Copy api_key now — only the hash is stored server-side.",
    }


@router.post("/keys/issue-admin")
async def issue_admin_key(
    request: Request,
    label: str | None = None,
    auth: AuthContext = Depends(verify_api_key),
):
    require_admin(auth)
    actor = _actor(auth)
    raw = await issue_api_key(
        account_id=None,
        is_admin=True,
        label=label or "additional admin key",
        issued_by=actor,
    )
    await request.app.state.audit_service.record(
        action="key.issue",
        actor_type="admin_key",
        actor_id=str(auth.key_id) if auth.key_id else None,
        actor_label=actor,
        target_type="api_key",
        target_id="admin",
        detail="admin key issued",
        ip=request.client.host if request.client else None,
    )
    return {"api_key": raw, "is_admin": True, "note": "Copy api_key now."}


@router.get("/keys")
async def list_keys(auth: AuthContext = Depends(verify_api_key)):
    require_admin(auth)
    async with async_session_factory() as session:
        rows = (await session.execute(select(ApiKey).order_by(ApiKey.created_at.desc()).limit(200))).scalars().all()
    return [
        {
            "id": r.id,
            "account_id": r.account_id,
            "is_admin": r.is_admin,
            "label": r.label,
            "revoked": r.revoked,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "rotation_due_at": r.rotation_due_at.isoformat() if r.rotation_due_at else None,
            "force_rotate": r.force_rotate,
            "issued_by": r.issued_by,
            "revoked_by": r.revoked_by,
            "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None,
        }
        for r in rows
    ]


@router.post("/keys/{key_id}/revoke")
async def revoke_key(
    key_id: int,
    request: Request,
    auth: AuthContext = Depends(verify_api_key),
):
    require_admin(auth)
    actor = _actor(auth)
    ok = await revoke_api_key(key_id, revoked_by=actor)
    if not ok:
        raise HTTPException(status_code=404, detail="Key not found")
    await request.app.state.audit_service.record(
        action="key.revoke",
        actor_type="admin_key",
        actor_id=str(auth.key_id) if auth.key_id else None,
        actor_label=actor,
        target_type="api_key",
        target_id=str(key_id),
        detail="revoked",
        ip=request.client.host if request.client else None,
    )
    return {"status": "revoked", "key_id": key_id}


@router.post("/keys/{key_id}/force-rotate")
async def force_rotate(
    key_id: int,
    request: Request,
    auth: AuthContext = Depends(verify_api_key),
):
    """Mark key as must-rotate; next API use returns 401 until a new key is issued."""
    require_admin(auth)
    actor = _actor(auth)
    ok = await force_rotate_key(key_id, actor=actor)
    if not ok:
        raise HTTPException(status_code=404, detail="Key not found or already revoked")
    await request.app.state.audit_service.record(
        action="key.force_rotate",
        actor_type="admin_key",
        actor_id=str(auth.key_id) if auth.key_id else None,
        actor_label=actor,
        target_type="api_key",
        target_id=str(key_id),
        detail="force_rotate set",
        ip=request.client.host if request.client else None,
    )
    return {"status": "force_rotate", "key_id": key_id}


class RotateKeyRequest(BaseModel):
    key_id: int
    label: str | None = None
    expires_in_days: int | None = None
    rotation_days: int | None = None


@router.post("/keys/rotate")
async def rotate_key(
    body: RotateKeyRequest,
    request: Request,
    auth: AuthContext = Depends(verify_api_key),
):
    """
    Issue a replacement key for the same account, revoke the old one.
    Returns the new raw key once.
    """
    require_admin(auth)
    actor = _actor(auth)
    async with async_session_factory() as session:
        result = await session.execute(select(ApiKey).where(ApiKey.id == body.key_id))
        old = result.scalar_one_or_none()
        if old is None:
            raise HTTPException(status_code=404, detail="Key not found")
        account_id = old.account_id
        is_admin = old.is_admin
        old_label = old.label

    raw = await issue_api_key(
        account_id=account_id,
        is_admin=is_admin,
        label=body.label or old_label or "rotated key",
        issued_by=actor,
        expires_in_days=body.expires_in_days,
        rotation_days=body.rotation_days,
        replaces_key_id=body.key_id,
    )
    await revoke_api_key(body.key_id, revoked_by=actor)
    await request.app.state.audit_service.record(
        action="key.rotate",
        actor_type="admin_key",
        actor_id=str(auth.key_id) if auth.key_id else None,
        actor_label=actor,
        target_type="api_key",
        target_id=str(body.key_id),
        account_id=account_id,
        detail=f"rotated; old_key_id={body.key_id}",
        ip=request.client.host if request.client else None,
    )
    return {
        "account_id": account_id,
        "api_key": raw,
        "replaced_key_id": body.key_id,
        "note": "Old key revoked. Copy new api_key now.",
    }


@router.get("/audit")
async def list_audit(
    request: Request,
    limit: int = Query(100, le=500),
    action: str | None = None,
    account_id: str | None = None,
    auth: AuthContext = Depends(verify_api_key),
):
    require_admin(auth)
    return await request.app.state.audit_service.list_events(
        limit=limit, action=action, account_id=account_id
    )


@router.get("/uploads/recent")
async def uploads_recent(
    request: Request,
    limit: int = Query(100, le=200),
    account_id: str | None = None,
    auth: AuthContext = Depends(verify_api_key),
):
    """Last N upload attempts (success and failure) across the fleet or one account."""
    require_admin(auth)
    return await request.app.state.upload_diagnostics.last_n(limit=limit, account_id=account_id)


@router.get("/uploads/trends")
async def uploads_trends(
    request: Request,
    hours: int = Query(24, le=168),
    account_id: str | None = None,
    auth: AuthContext = Depends(verify_api_key),
):
    require_admin(auth)
    return await request.app.state.upload_diagnostics.trends(hours=hours, account_id=account_id)


@router.get("/uploads/latency")
async def uploads_latency(
    request: Request,
    limit: int = Query(100, le=200),
    account_id: str | None = None,
    auth: AuthContext = Depends(verify_api_key),
):
    require_admin(auth)
    return await request.app.state.upload_diagnostics.latency_series(limit=limit, account_id=account_id)


@router.get("/diagnostics")
async def admin_diagnostics(request: Request, auth: AuthContext = Depends(verify_api_key)):
    require_admin(auth)
    from app.config import settings

    redis_ok = False
    try:
        client = request.app.state.job_queue.get_redis_client()
        if client is not None:
            await client.ping()
            redis_ok = True
    except Exception:  # noqa: BLE001
        redis_ok = False

    trends = await request.app.state.upload_diagnostics.trends(hours=24)
    return {
        "redis_ok": redis_ok,
        "max_concurrent_workers": settings.MAX_CONCURRENT_WORKERS,
        "active_workers_this_instance": request.app.state.worker_pool.active_worker_count(),
        "debug": settings.DEBUG,
        "app_version": settings.APP_VERSION,
        "upload_trends_24h": trends,
        "api_key_default_ttl_days": settings.API_KEY_DEFAULT_TTL_DAYS,
        "api_key_rotation_days": settings.API_KEY_ROTATION_DAYS,
    }


class AlertTestRequest(BaseModel):
    subject: str = "AEGIS test alert"
    body: str = "Test message from admin dashboard."
    channels: list[str] | None = None


@router.post("/alerts/test")
async def test_alerts(
    body: AlertTestRequest,
    request: Request,
    auth: AuthContext = Depends(verify_api_key),
):
    require_admin(auth)
    results = await request.app.state.alert_service.send(
        body.subject, body.body, severity="info", channels=body.channels
    )
    await request.app.state.audit_service.record(
        action="alert.test",
        actor_type="admin_key",
        actor_id=str(auth.key_id) if auth.key_id else None,
        actor_label=auth.label,
        detail=str(results),
        ip=request.client.host if request.client else None,
    )
    return {"results": results}


from app.services.plan_catalog import PLAN_CATALOG, resolve_plan
from app.db.models import Subscription
from datetime import datetime, timezone


@router.get("/plans")
async def list_plans(auth: AuthContext = Depends(verify_api_key)):
    require_admin(auth)
    return [{"code": k, **v} for k, v in PLAN_CATALOG.items()]


class SetPlanRequest(BaseModel):
    account_id: str
    plan: str
    status: str | None = "active"


@router.post("/tenants/set-plan")
async def set_tenant_plan(
    body: SetPlanRequest,
    request: Request,
    auth: AuthContext = Depends(verify_api_key),
):
    """Assign a commercial tier (devices + daily trade caps) to an account."""
    require_admin(auth)
    meta = resolve_plan(body.plan)
    now = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.account_id == body.account_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = Subscription(
                account_id=body.account_id,
                provider="manual",
                status=body.status or "active",
                plan=meta["code"],
                max_devices=meta["max_devices"],
                max_trades_per_day=meta["max_trades_per_day"],
                updated_at=now,
            )
            session.add(row)
        else:
            row.plan = meta["code"]
            row.max_devices = meta["max_devices"]
            row.max_trades_per_day = meta["max_trades_per_day"]
            row.status = body.status or row.status
            row.updated_at = now
        await session.commit()
    await request.app.state.audit_service.record(
        action="subscription.set_plan",
        actor_type="admin_key",
        actor_id=str(auth.key_id) if auth.key_id else None,
        actor_label=auth.label,
        account_id=body.account_id,
        detail=f"plan={meta['code']} devices={meta['max_devices']} trades/day={meta['max_trades_per_day']}",
        ip=request.client.host if request.client else None,
    )
    return {"account_id": body.account_id, "plan": meta}


@router.get("/tenants")
async def list_tenants(request: Request, auth: AuthContext = Depends(verify_api_key)):
    require_admin(auth)
    subs = await request.app.state.subscription_service.list_all()
    devices = await request.app.state.device_bindings.list_all(limit=500)
    by_acct: dict[str, int] = {}
    for d in devices:
        by_acct[d["account_id"]] = by_acct.get(d["account_id"], 0) + 1
    out = []
    for s in subs:
        aid = s.get("account_id")
        st = await request.app.state.trade_limits.status(aid) if hasattr(request.app.state, "trade_limits") else {}
        out.append({
            **s,
            "bound_devices": by_acct.get(aid, 0),
            "trades_today": st,
        })
    return out


@router.get("/devices")
async def admin_list_devices(request: Request, auth: AuthContext = Depends(verify_api_key)):
    require_admin(auth)
    return await request.app.state.device_bindings.list_all()


@router.get("/download-tokens")
async def admin_list_tokens(request: Request, auth: AuthContext = Depends(verify_api_key)):
    require_admin(auth)
    return await request.app.state.device_bindings.list_download_tokens()
