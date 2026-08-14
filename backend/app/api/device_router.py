"""
Project : AEGIS
Company : Honeydewnuts Nigerian Limited
File    : device_router.py
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.schemas.device_health import HeartbeatRequest
from app.security import verify_api_key, require_account_match, require_admin, AuthContext

router = APIRouter(prefix="/api/devices", tags=["Device Health"])


def get_device_health_service(request: Request):
    return request.app.state.device_health


@router.post("/heartbeat")
async def receive_heartbeat(
    heartbeat: HeartbeatRequest,
    device_health=Depends(get_device_health_service),
    auth: AuthContext = Depends(verify_api_key),
):
    require_account_match(auth, heartbeat.account_id)
    await device_health.record_heartbeat(heartbeat.account_id, heartbeat.model_dump(by_alias=False))
    return {"status": "recorded"}


@router.get("/health/{account_id}")
async def get_device_health(
    account_id: str,
    device_health=Depends(get_device_health_service),
    auth: AuthContext = Depends(verify_api_key),
):
    require_account_match(auth, account_id)
    health = await device_health.get_health(account_id)
    if health is None:
        raise HTTPException(status_code=404, detail="No recent heartbeat for this account - device may be offline.")
    return health


@router.get("/health")
async def list_device_health(
    device_health=Depends(get_device_health_service),
    auth: AuthContext = Depends(verify_api_key),
):
    """Operator dashboard endpoint - status of every device. Admin-only,
    since this is fleet-wide data, not scoped to one account."""
    require_admin(auth)
    return await device_health.list_all()


from pydantic import BaseModel, Field


class DeviceRegisterRequest(BaseModel):
    account_id: str
    device_id: str = Field(..., description="ANDROID_ID or stable device fingerprint")
    device_label: str | None = None


@router.post("/register")
async def register_device(
    body: DeviceRegisterRequest,
    request: Request,
    auth: AuthContext = Depends(verify_api_key),
):
    """
    Bind this install to one phone. First successful call wins.
    Another phone using the same account_id + API key is rejected.
    """
    require_account_match(auth, body.account_id)
    result = await request.app.state.device_bindings.register(
        body.account_id, body.device_id, body.device_label
    )
    if result.get("status") == "rejected":
        await request.app.state.audit_service.record(
            action="device.bind_rejected",
            actor_type="account_key",
            actor_id=str(auth.key_id) if auth.key_id else None,
            account_id=body.account_id,
            detail=result.get("reason"),
            success=False,
            ip=request.client.host if request.client else None,
        )
        raise HTTPException(
            status_code=403,
            detail="This subscription is already bound to another device. Contact support to transfer.",
        )
    if result.get("status") == "bound":
        await request.app.state.audit_service.record(
            action="device.bind",
            actor_type="account_key",
            actor_id=str(auth.key_id) if auth.key_id else None,
            account_id=body.account_id,
            target_type="device",
            target_id=body.device_id[-6:],
            ip=request.client.host if request.client else None,
        )
    return result


@router.delete("/binding/{account_id}")
async def clear_device_binding(
    account_id: str,
    request: Request,
    auth: AuthContext = Depends(verify_api_key),
):
    """Admin: allow the subscriber to install on a new phone."""
    require_admin(auth)
    ok = await request.app.state.device_bindings.clear(account_id)
    if not ok:
        raise HTTPException(status_code=404, detail="No binding found")
    await request.app.state.audit_service.record(
        action="device.unbind",
        actor_type="admin_key",
        actor_id=str(auth.key_id) if auth.key_id else None,
        actor_label=auth.label,
        account_id=account_id,
        ip=request.client.host if request.client else None,
    )
    return {"status": "cleared", "account_id": account_id}
