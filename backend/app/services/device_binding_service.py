"""Multi-device bindings limited by subscription.max_devices."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func, delete

from app.db.base import async_session_factory
from app.db.models import DeviceBinding, DownloadToken, Subscription
from app.services.plan_catalog import resolve_plan


class DeviceBindingService:
    async def _max_devices(self, account_id: str) -> int:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.account_id == account_id)
            )
            row = result.scalar_one_or_none()
        if row is None:
            return 1
        if getattr(row, "max_devices", None):
            return int(row.max_devices)
        return int(resolve_plan(getattr(row, "plan", "starter")).get("max_devices", 1))

    async def list_for_account(self, account_id: str) -> list[dict[str, Any]]:
        async with async_session_factory() as session:
            rows = (
                await session.execute(
                    select(DeviceBinding).where(DeviceBinding.account_id == account_id)
                )
            ).scalars().all()
        return [
            {
                "id": r.id,
                "account_id": r.account_id,
                "device_id": r.device_id,
                "device_label": r.device_label,
                "bound_at": r.bound_at.isoformat() if r.bound_at else None,
                "last_seen_at": r.last_seen_at.isoformat() if r.last_seen_at else None,
            }
            for r in rows
        ]

    async def list_all(self, limit: int = 200) -> list[dict[str, Any]]:
        async with async_session_factory() as session:
            rows = (
                await session.execute(
                    select(DeviceBinding).order_by(DeviceBinding.bound_at.desc()).limit(limit)
                )
            ).scalars().all()
        return [
            {
                "id": r.id,
                "account_id": r.account_id,
                "device_id": r.device_id,
                "device_label": r.device_label,
                "bound_at": r.bound_at.isoformat() if r.bound_at else None,
                "last_seen_at": r.last_seen_at.isoformat() if r.last_seen_at else None,
            }
            for r in rows
        ]

    async def register(self, account_id: str, device_id: str, device_label: str | None = None) -> dict[str, Any]:
        device_id = device_id.strip()
        if not device_id:
            raise ValueError("device_id required")

        now = datetime.now(timezone.utc)
        max_dev = await self._max_devices(account_id)

        async with async_session_factory() as session:
            existing = (
                await session.execute(
                    select(DeviceBinding).where(
                        DeviceBinding.account_id == account_id,
                        DeviceBinding.device_id == device_id,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.last_seen_at = now
                if device_label:
                    existing.device_label = device_label
                await session.commit()
                return {
                    "status": "ok",
                    "account_id": account_id,
                    "device_id": device_id,
                    "max_devices": max_dev,
                }

            count = (
                await session.execute(
                    select(func.count()).select_from(DeviceBinding).where(
                        DeviceBinding.account_id == account_id
                    )
                )
            ).scalar_one()

            if count >= max_dev:
                return {
                    "status": "rejected",
                    "reason": "device_limit_reached",
                    "max_devices": max_dev,
                    "bound_count": count,
                }

            session.add(
                DeviceBinding(
                    account_id=account_id,
                    device_id=device_id,
                    device_label=device_label,
                    bound_at=now,
                    last_seen_at=now,
                )
            )
            await session.commit()
            return {
                "status": "bound",
                "account_id": account_id,
                "device_id": device_id,
                "max_devices": max_dev,
                "bound_count": count + 1,
            }

    async def clear(self, account_id: str) -> int:
        async with async_session_factory() as session:
            result = await session.execute(
                delete(DeviceBinding).where(DeviceBinding.account_id == account_id)
            )
            await session.commit()
            return result.rowcount or 0

    async def remove_device(self, account_id: str, device_id: str) -> bool:
        async with async_session_factory() as session:
            result = await session.execute(
                select(DeviceBinding).where(
                    DeviceBinding.account_id == account_id,
                    DeviceBinding.device_id == device_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def issue_download_token(
        self,
        account_id: str,
        plan: str = "starter",
        max_uses: int = 1,
        ttl_hours: int = 48,
    ) -> str:
        token = secrets.token_urlsafe(24)
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            session.add(
                DownloadToken(
                    token=token,
                    account_id=account_id,
                    plan=plan,
                    max_uses=max_uses,
                    uses=0,
                    expires_at=now + timedelta(hours=ttl_hours),
                    created_at=now,
                    revoked=False,
                )
            )
            await session.commit()
        return token

    async def consume_download_token(self, token: str) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            result = await session.execute(
                select(DownloadToken).where(DownloadToken.token == token)
            )
            row = result.scalar_one_or_none()
            if row is None or row.revoked:
                return None
            if row.expires_at and row.expires_at <= now:
                return None
            if row.uses >= row.max_uses:
                return None
            row.uses += 1
            await session.commit()
            return {
                "account_id": row.account_id,
                "plan": row.plan,
                "uses": row.uses,
                "max_uses": row.max_uses,
            }

    async def list_download_tokens(self, limit: int = 100) -> list[dict[str, Any]]:
        async with async_session_factory() as session:
            rows = (
                await session.execute(
                    select(DownloadToken).order_by(DownloadToken.created_at.desc()).limit(limit)
                )
            ).scalars().all()
        return [
            {
                "token_suffix": r.token[-8:],
                "account_id": r.account_id,
                "plan": r.plan,
                "uses": r.uses,
                "max_uses": r.max_uses,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "revoked": r.revoked,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
