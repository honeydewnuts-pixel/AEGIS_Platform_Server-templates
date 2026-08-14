"""Daily trade quota enforcement per commercial plan."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.db.base import async_session_factory
from app.db.models import Subscription, TradeDailyCounter
from app.services.plan_catalog import resolve_plan


class TradeLimitService:
    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    async def _limit_for(self, account_id: str) -> int:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.account_id == account_id)
            )
            row = result.scalar_one_or_none()
        if row is None:
            return 0
        if getattr(row, "max_trades_per_day", None) is not None:
            return int(row.max_trades_per_day)
        return int(resolve_plan(getattr(row, "plan", "starter")).get("max_trades_per_day", 10))

    async def status(self, account_id: str) -> dict[str, Any]:
        limit = await self._limit_for(account_id)
        day = self._today()
        async with async_session_factory() as session:
            result = await session.execute(
                select(TradeDailyCounter).where(
                    TradeDailyCounter.account_id == account_id,
                    TradeDailyCounter.day == day,
                )
            )
            row = result.scalar_one_or_none()
        used = row.trade_count if row else 0
        remaining = None if limit == 0 else max(0, limit - used)
        return {
            "account_id": account_id,
            "day": day,
            "used": used,
            "limit": limit,
            "remaining": remaining,
            "unlimited": limit == 0,
        }

    async def consume(self, account_id: str, n: int = 1) -> dict[str, Any]:
        """Increment daily counter; raise ValueError if over quota."""
        limit = await self._limit_for(account_id)
        day = self._today()
        async with async_session_factory() as session:
            result = await session.execute(
                select(TradeDailyCounter).where(
                    TradeDailyCounter.account_id == account_id,
                    TradeDailyCounter.day == day,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = TradeDailyCounter(account_id=account_id, day=day, trade_count=0)
                session.add(row)
            if limit > 0 and row.trade_count + n > limit:
                await session.rollback()
                raise ValueError(
                    f"Daily trade limit reached ({row.trade_count}/{limit}). Upgrade your plan."
                )
            row.trade_count += n
            used = row.trade_count
            await session.commit()
        remaining = None if limit == 0 else max(0, limit - used)
        return {"used": used, "limit": limit, "remaining": remaining, "unlimited": limit == 0}
