"""Support tickets / in-app report issue (never store API keys)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.base import async_session_factory
from app.db.models import SupportTicket
from app.security import AuthContext, require_admin, verify_api_key

router = APIRouter(prefix="/api/support", tags=["Support"])


class ReportIssueBody(BaseModel):
    account_id: str | None = None
    email: str | None = None
    subject: str = Field(min_length=3, max_length=200)
    message: str = Field(min_length=5, max_length=4000)
    last_http_code: int | None = None
    device_model: str | None = None
    app_version: str | None = None
    android_version: str | None = None


@router.post("/report")
async def report_issue(body: ReportIssueBody, request: Request):
    msg = body.message
    lower = msg.lower()
    if any(x in lower for x in ("api_key", "api-key", "x-api-key", "bearer ")):
        msg = "[redacted possible secret] " + msg[:200]
    now = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        ticket = SupportTicket(
            created_at=now,
            account_id=body.account_id,
            email=body.email,
            subject=body.subject[:200],
            message=msg[:4000],
            last_http_code=body.last_http_code,
            device_model=(body.device_model or "")[:120] or None,
            app_version=(body.app_version or "")[:40] or None,
            android_version=(body.android_version or "")[:40] or None,
            status="open",
        )
        session.add(ticket)
        await session.commit()
        tid = ticket.id
    return {
        "ticket_id": tid,
        "status": "open",
        "message": "Issue reported. Support will follow up.",
    }


@router.get("/tickets")
async def list_tickets(
    limit: int = 50,
    auth: AuthContext = Depends(verify_api_key),
):
    require_admin(auth)
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(SupportTicket).order_by(SupportTicket.created_at.desc()).limit(min(limit, 200))
            )
        ).scalars().all()
        return [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "account_id": r.account_id,
                "subject": r.subject,
                "message": r.message[:500],
                "last_http_code": r.last_http_code,
                "device_model": r.device_model,
                "status": r.status,
            }
            for r in rows
        ]
