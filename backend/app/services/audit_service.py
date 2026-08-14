"""
Append-only audit trail for security-sensitive actions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.db.base import async_session_factory
from app.db.models import AuditEvent


class AuditService:
    async def record(
        self,
        *,
        action: str,
        actor_type: str = "system",
        actor_id: str | None = None,
        actor_label: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        account_id: str | None = None,
        detail: str | None = None,
        ip: str | None = None,
        success: bool = True,
    ) -> None:
        async with async_session_factory() as session:
            session.add(
                AuditEvent(
                    created_at=datetime.now(timezone.utc),
                    actor_type=actor_type,
                    actor_id=actor_id,
                    actor_label=actor_label,
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    account_id=account_id,
                    detail=detail,
                    ip=ip,
                    success=success,
                )
            )
            await session.commit()

    async def list_events(
        self,
        *,
        limit: int = 100,
        action: str | None = None,
        account_id: str | None = None,
        actor_id: str | None = None,
    ) -> list[dict[str, Any]]:
        limit = min(max(limit, 1), 500)
        async with async_session_factory() as session:
            q = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
            if action:
                q = q.where(AuditEvent.action == action)
            if account_id:
                q = q.where(AuditEvent.account_id == account_id)
            if actor_id:
                q = q.where(AuditEvent.actor_id == actor_id)
            rows = (await session.execute(q)).scalars().all()
        return [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "actor_type": r.actor_type,
                "actor_id": r.actor_id,
                "actor_label": r.actor_label,
                "action": r.action,
                "target_type": r.target_type,
                "target_id": r.target_id,
                "account_id": r.account_id,
                "detail": r.detail,
                "ip": r.ip,
                "success": r.success,
            }
            for r in rows
        ]
