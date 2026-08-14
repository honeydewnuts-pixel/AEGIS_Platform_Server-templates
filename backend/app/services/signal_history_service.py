"""
Project : AEGIS
Company : Honeydewnuts Nigerian Limited
File    : signal_history_service.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, delete

from app.core.logging import configure_logging
from app.db.base import async_session_factory
from app.db.models import SignalHistory

MAX_RESULTS_PER_QUERY = 200


class SignalHistoryService:

    def __init__(self) -> None:
        self.logger = configure_logging(__name__)

    async def record(self, account_id: str, signal: str, confidence: float, rule_name: str, details: str) -> None:
        async with async_session_factory() as session:
            session.add(SignalHistory(
                account_id=account_id,
                signal=signal,
                confidence=confidence,
                rule_name=rule_name,
                details=details,
                created_at=datetime.now(timezone.utc),
            ))
            await session.commit()

    async def get_history(self, account_id: str, limit: int = 50) -> list[dict[str, Any]]:
        limit = min(limit, MAX_RESULTS_PER_QUERY)
        async with async_session_factory() as session:
            result = await session.execute(
                select(SignalHistory)
                .where(SignalHistory.account_id == account_id)
                .order_by(SignalHistory.created_at.desc())
                .limit(limit)
            )
            rows = result.scalars().all()

        return [
            {
                "account_id": r.account_id,
                "signal": r.signal,
                "confidence": r.confidence,
                "rule_name": r.rule_name,
                "details": r.details,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]

    async def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Fleet-wide recent signals for the admin dashboard."""
        limit = min(limit, MAX_RESULTS_PER_QUERY)
        async with async_session_factory() as session:
            result = await session.execute(
                select(SignalHistory)
                .order_by(SignalHistory.created_at.desc())
                .limit(limit)
            )
            rows = result.scalars().all()

        return [
            {
                "account_id": r.account_id,
                "signal": r.signal,
                "confidence": r.confidence,
                "rule_name": r.rule_name,
                "details": r.details,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]

    async def purge_older_than(self, cutoff: datetime) -> int:
        """Not called automatically anywhere yet - this table has no
        retention policy applied by default. Wire this into a scheduled
        task (same pattern as the subscription sweep in core/startup.py)
        if you want one, or run it manually - flagging rather than
        silently letting this grow unbounded forever."""
        async with async_session_factory() as session:
            result = await session.execute(delete(SignalHistory).where(SignalHistory.created_at < cutoff))
            await session.commit()
            return result.rowcount
