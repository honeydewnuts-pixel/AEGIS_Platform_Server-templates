"""
Project : AEGIS
Company : Honeydewnuts Nigerian Limited
File    : portal_router.py

Subscriber-facing endpoints for client_portal/. Deliberately NOT gated
by verify_api_key (the shared service key) - subscribers authenticate
with their own account_id + portal_token instead, which is generated
once when their subscription first activates (see
SubscriptionService.apply_event) and would typically be shown on the
checkout success page or emailed to them.

This is intentionally minimal - account_id + a long random token, not
email/password with reset flows. Documented as a foundation to build
real subscriber accounts on top of later, not a finished auth system.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/api/portal", tags=["Client Portal"])


async def _authenticate(request: Request, account_id: str, token: str) -> dict:
    subscription_service = request.app.state.subscription_service
    if not await subscription_service.verify_portal_token(account_id, token):
        raise HTTPException(status_code=401, detail="Invalid account ID or portal token.")
    record = await subscription_service.get_status(account_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No subscription found.")
    record["is_active"] = await subscription_service.is_active(account_id)
    return record


@router.get("/status")
async def portal_status(
    request: Request,
    account_id: str = Query(...),
    token: str = Query(...),
):
    return await _authenticate(request, account_id, token)


@router.get("/device")
async def portal_device_health(
    request: Request,
    account_id: str = Query(...),
    token: str = Query(...),
):
    await _authenticate(request, account_id, token)  # raises if invalid
    device_health = request.app.state.device_health
    health = await device_health.get_health(account_id)
    if health is None:
        return {"status": "offline", "reason": "no heartbeat within TTL"}
    return {"status": "online", **health}


@router.get("/signals")
async def portal_signal_history(
    request: Request,
    account_id: str = Query(...),
    token: str = Query(...),
    limit: int = Query(50, le=200),
):
    await _authenticate(request, account_id, token)
    signal_history = request.app.state.signal_history
    return await signal_history.get_history(account_id, limit)


@router.get("/download-url")
async def portal_download_url(
    request: Request,
    account_id: str = Query(...),
    token: str = Query(...),
):
    """
    Issues a short-lived single-use download token and returns the absolute
    APK URL. Aligns with /api/download/apk?token=… gating.
    """
    record = await _authenticate(request, account_id, token)
    if not record["is_active"]:
        raise HTTPException(status_code=402, detail="Subscription is not active.")
    plan = record.get("plan") or "starter"
    if plan in ("live",):
        plan = "starter"
    bindings = request.app.state.device_bindings
    dl_token = await bindings.issue_download_token(
        account_id=account_id, plan=plan, max_uses=1, ttl_hours=24
    )
    base = str(request.base_url).rstrip("/")
    return {
        "download_url": f"{base}/api/download/apk?token={dl_token}",
        "token": dl_token,
        "plan": plan,
        "expires_hours": 24,
        "note": "Single-use link. Open on the phone that will run AEGIS.",
    }


@router.get("/trade-quota")
async def portal_trade_quota(
    request: Request,
    account_id: str = Query(...),
    token: str = Query(...),
):
    await _authenticate(request, account_id, token)
    limits = getattr(request.app.state, "trade_limits", None)
    if limits is None:
        return {"account_id": account_id, "available": False}
    return await limits.status(account_id)


@router.post("/mobile-key")
async def portal_issue_mobile_key(
    request: Request,
    account_id: str = Query(...),
    token: str = Query(...),
):
    """
    Issue (or re-issue) a mobile API key for this account.
    Raw key returned ONCE. Previous non-admin keys for the account are revoked
    so only the latest key works on the device.
    """
    record = await _authenticate(request, account_id, token)
    if not record.get("is_active"):
        raise HTTPException(
            status_code=402,
            detail="Subscription is not active. Start a free demo or complete payment first.",
        )

    from app.security import issue_api_key, revoke_account_keys
    from app.db.base import async_session_factory
    from app.db.models import ApiKey
    from sqlalchemy import select, update
    from datetime import datetime, timezone

    # Revoke existing non-admin keys for this account
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(ApiKey).where(
                    ApiKey.account_id == account_id,
                    ApiKey.is_admin == False,  # noqa: E712
                    ApiKey.revoked == False,  # noqa: E712
                )
            )
        ).scalars().all()
        now = datetime.now(timezone.utc)
        for row in rows:
            row.revoked = True
            row.revoked_at = now
            row.revoked_by = "portal.mobile-key"
        await session.commit()

    raw = await issue_api_key(
        account_id=account_id,
        is_admin=False,
        label="mobile",
        issued_by=f"portal:{account_id}",
    )
    try:
        audit = getattr(request.app.state, "audit_service", None)
        if audit:
            await audit.record(
                actor_type="account",
                actor_id=account_id,
                action="key.issue",
                target_type="api_key",
                account_id=account_id,
                detail="mobile key issued via portal",
                success=True,
            )
    except Exception:
        pass

    return {
        "account_id": account_id,
        "mobile_api_key": raw,
        "plan": record.get("plan"),
        "server_url_hint": "Use your AEGIS API origin (https://…onrender.com) in the mobile app — not the marketing website URL.",
        "instructions": [
            "Open AEGIS Mobile → Settings",
            "Server URL = your AEGIS API HTTPS origin",
            "Account ID = the account_id below",
            "API key = the mobile_api_key shown (copy now)",
            "Save → return to main screen → START with MT5 visible",
        ],
        "once": True,
        "warning": "This key is shown once. Generating again revokes the previous mobile key.",
    }
