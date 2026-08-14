"""
Gated APK download for the marketing / portal website.

Requires a download token (issued after subscribe or demo signup).
Tokens are single-use by default so a link cannot be freely shared.
Device binding is enforced later when the app registers ANDROID_ID.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.security import verify_api_key, require_admin, AuthContext

router = APIRouter(prefix="/api/download", tags=["Download"])


@router.get("/apk")
async def download_apk(
    request: Request,
    token: str = Query(..., description="One-time download token from portal/checkout"),
):
    bindings = request.app.state.device_bindings
    consumed = await bindings.consume_download_token(token)
    if consumed is None:
        raise HTTPException(
            status_code=403,
            detail="Invalid, expired, revoked, or already-used download token. Subscribe or request a new link.",
        )

    apk_path = Path(settings.APK_FILE_PATH)
    if not apk_path.exists():
        raise HTTPException(
            status_code=500,
            detail="APK file not found on server — build and place it at APK_FILE_PATH.",
        )

    audit = getattr(request.app.state, "audit_service", None)
    if audit:
        await audit.record(
            action="apk.download",
            actor_type="download_token",
            actor_id=token[:8] + "…",
            account_id=consumed["account_id"],
            target_type="apk",
            target_id=consumed["plan"],
            detail=f"uses={consumed['uses']}/{consumed['max_uses']}",
            ip=request.client.host if request.client else None,
        )

    return FileResponse(
        path=str(apk_path),
        media_type="application/vnd.android.package-archive",
        filename=f"AEGIS-{consumed['plan']}.apk",
        headers={
            "X-AEGIS-Account-Id": consumed["account_id"],
            "X-AEGIS-Plan": consumed["plan"],
        },
    )


class IssueDownloadTokenRequest(BaseModel):
    account_id: str
    plan: str = Field(default="live", pattern="^(live|demo)$")
    max_uses: int = Field(default=1, ge=1, le=5)
    ttl_hours: int = Field(default=48, ge=1, le=720)


@router.post("/token")
async def issue_token(
    body: IssueDownloadTokenRequest,
    request: Request,
    auth: AuthContext = Depends(verify_api_key),
):
    """Admin or active portal flow issues a short-lived download token."""
    require_admin(auth)
    token = await request.app.state.device_bindings.issue_download_token(
        account_id=body.account_id,
        plan=body.plan,
        max_uses=body.max_uses,
        ttl_hours=body.ttl_hours,
    )
    await request.app.state.audit_service.record(
        action="download_token.issue",
        actor_type="admin_key",
        actor_id=str(auth.key_id) if auth.key_id else None,
        actor_label=auth.label,
        account_id=body.account_id,
        target_type="download_token",
        detail=f"plan={body.plan} max_uses={body.max_uses}",
        ip=request.client.host if request.client else None,
    )
    base = str(request.base_url).rstrip("/")
    return {
        "token": token,
        "account_id": body.account_id,
        "plan": body.plan,
        "download_url": f"{base}/api/download/apk?token={token}",
        "note": "Single-use by default. Share only with the subscriber.",
    }
