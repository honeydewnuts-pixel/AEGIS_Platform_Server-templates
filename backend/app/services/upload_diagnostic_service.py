"""
Upload attempt history for diagnostics: last N, failure trends, latency.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from app.db.base import async_session_factory
from app.db.models import UploadDiagnostic


class UploadDiagnosticService:
    async def record(
        self,
        *,
        account_id: str,
        success: bool,
        http_status: int | None = None,
        latency_ms: float | None = None,
        image_bytes: int | None = None,
        error_code: str | None = None,
        detail: str | None = None,
    ) -> None:
        async with async_session_factory() as session:
            session.add(
                UploadDiagnostic(
                    created_at=datetime.now(timezone.utc),
                    account_id=account_id,
                    success=success,
                    http_status=http_status,
                    latency_ms=latency_ms,
                    image_bytes=image_bytes,
                    error_code=error_code,
                    detail=(detail or "")[:500] or None,
                )
            )
            await session.commit()

    async def last_n(self, limit: int = 100, account_id: str | None = None) -> list[dict[str, Any]]:
        limit = min(max(limit, 1), 200)
        async with async_session_factory() as session:
            q = select(UploadDiagnostic).order_by(UploadDiagnostic.created_at.desc()).limit(limit)
            if account_id:
                q = q.where(UploadDiagnostic.account_id == account_id)
            rows = (await session.execute(q)).scalars().all()
        return [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "account_id": r.account_id,
                "success": r.success,
                "http_status": r.http_status,
                "latency_ms": r.latency_ms,
                "image_bytes": r.image_bytes,
                "error_code": r.error_code,
                "detail": r.detail,
            }
            for r in rows
        ]

    async def trends(self, hours: int = 24, account_id: str | None = None) -> dict[str, Any]:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        async with async_session_factory() as session:
            q = select(UploadDiagnostic).where(UploadDiagnostic.created_at >= since)
            if account_id:
                q = q.where(UploadDiagnostic.account_id == account_id)
            rows = (await session.execute(q)).scalars().all()

        total = len(rows)
        successes = sum(1 for r in rows if r.success)
        failures = total - successes
        latencies = [r.latency_ms for r in rows if r.latency_ms is not None]
        by_status: dict[str, int] = {}
        by_error: dict[str, int] = {}
        for r in rows:
            key = str(r.http_status or ("ok" if r.success else "unknown"))
            by_status[key] = by_status.get(key, 0) + 1
            if r.error_code:
                by_error[r.error_code] = by_error.get(r.error_code, 0) + 1

        avg_latency = sum(latencies) / len(latencies) if latencies else None
        p95 = None
        if latencies:
            s = sorted(latencies)
            p95 = s[min(len(s) - 1, int(len(s) * 0.95))]

        return {
            "window_hours": hours,
            "total": total,
            "successes": successes,
            "failures": failures,
            "success_rate": (successes / total) if total else None,
            "avg_latency_ms": avg_latency,
            "p95_latency_ms": p95,
            "by_http_status": by_status,
            "by_error_code": by_error,
        }

    async def latency_series(self, limit: int = 100, account_id: str | None = None) -> list[dict[str, Any]]:
        rows = await self.last_n(limit=limit, account_id=account_id)
        return [
            {
                "created_at": r["created_at"],
                "latency_ms": r["latency_ms"],
                "success": r["success"],
                "http_status": r["http_status"],
            }
            for r in reversed(rows)
        ]
