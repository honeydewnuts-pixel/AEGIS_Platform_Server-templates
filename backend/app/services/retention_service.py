"""Purge old audit + upload diagnostic rows per retention policy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.config import settings
from app.db.base import async_session_factory
from app.db.models import AuditEvent, UploadDiagnostic
from app.core.logging import configure_logging

logger = configure_logging(__name__)


async def purge_old_records() -> dict[str, int]:
    days = int(getattr(settings, "AUDIT_RETENTION_DAYS", 90) or 90)
    if days <= 0:
        return {"audit": 0, "uploads": 0}
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with async_session_factory() as session:
        a = await session.execute(delete(AuditEvent).where(AuditEvent.created_at < cutoff))
        u = await session.execute(delete(UploadDiagnostic).where(UploadDiagnostic.created_at < cutoff))
        await session.commit()
        counts = {"audit": a.rowcount or 0, "uploads": u.rowcount or 0}
    if counts["audit"] or counts["uploads"]:
        logger.info("Retention purge: %s", counts)
    return counts
