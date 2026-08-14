"""Public + admin APIs for indicator stack and rulebook versions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.security import verify_api_key, require_admin, AuthContext

router = APIRouter(prefix="/api/templates", tags=["Templates"])


@router.get("/active")
async def get_active_templates(request: Request):
    """Mobile and portal: current indicator install checklist + rulebook version."""
    return request.app.state.templates.get_active_bundle()


@router.get("/indicator-stacks")
async def list_stacks(request: Request, auth: AuthContext = Depends(verify_api_key)):
    require_admin(auth)
    return request.app.state.templates.list_indicator_stacks()


@router.get("/rulebooks")
async def list_books(request: Request, auth: AuthContext = Depends(verify_api_key)):
    require_admin(auth)
    return request.app.state.templates.list_rulebooks()


@router.get("/indicator-stacks/{version}")
async def get_stack(version: str, request: Request, auth: AuthContext = Depends(verify_api_key)):
    try:
        return request.app.state.templates.get_indicator_stack(version)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/rulebooks/{version}")
async def get_book(version: str, request: Request, auth: AuthContext = Depends(verify_api_key)):
    try:
        return request.app.state.templates.get_rulebook(version)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


class ActivateRequest(BaseModel):
    indicator_stack_version: str = Field(..., examples=["v1", "v2"])
    rulebook_version: str = Field(..., examples=["v1", "v2"])


@router.post("/activate")
async def activate_profile(
    body: ActivateRequest,
    request: Request,
    auth: AuthContext = Depends(verify_api_key),
):
    require_admin(auth)
    try:
        ptr = request.app.state.templates.activate(
            body.indicator_stack_version, body.rulebook_version
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    # Hot-reload brain vision config
    brain = getattr(request.app.state, "brain_cv_service", None)
    if brain is not None and hasattr(brain, "reload_config"):
        brain.reload_config()

    audit = getattr(request.app.state, "audit_service", None)
    if audit:
        await audit.record(
            action="templates.activate",
            actor_type="admin_key",
            actor_id=str(auth.key_id) if auth.key_id else None,
            actor_label=auth.label,
            detail=f"stack={ptr['indicator_stack_version']} rulebook={ptr['rulebook_version']}",
            ip=request.client.host if request.client else None,
        )
    return {"status": "activated", **ptr}
