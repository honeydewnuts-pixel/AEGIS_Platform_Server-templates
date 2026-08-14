"""
AEGIS Security Module — per-account API keys with lifecycle checks.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException, status
from sqlalchemy import select

from app.config import settings
from app.db.base import async_session_factory
from app.db.models import ApiKey


def generate_secret_key(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


@dataclass
class AuthContext:
    account_id: str | None
    is_admin: bool
    label: str | None
    key_id: int | None = None
    force_rotate: bool = False
    expires_at: datetime | None = None
    rotation_due_at: datetime | None = None


def _actor_label(auth: AuthContext | None) -> str | None:
    if auth is None:
        return None
    if auth.label:
        return auth.label
    if auth.is_admin:
        return "admin"
    return auth.account_id


async def verify_api_key(x_api_key: str | None = Header(default=None)) -> AuthContext:
    if x_api_key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-API-Key header.")

    key_hash = _hash_key(x_api_key)
    now = datetime.now(timezone.utc)

    async with async_session_factory() as session:
        result = await session.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
        row = result.scalar_one_or_none()

        if row is None or row.revoked:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key.")

        if row.expires_at is not None and row.expires_at <= now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has expired. Request a new key from your operator.",
            )

        if row.force_rotate:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key rotation required. Contact your operator for a new key.",
            )

        # Soft warning path: rotation_due_at does not block, but is exposed on AuthContext
        # so clients/admin can surface "rotate soon". Forced/expired still hard-block above.

        row.last_used_at = now
        await session.commit()

        return AuthContext(
            account_id=row.account_id,
            is_admin=row.is_admin,
            label=row.label,
            key_id=row.id,
            force_rotate=bool(row.force_rotate),
            expires_at=row.expires_at,
            rotation_due_at=row.rotation_due_at,
        )


def require_account_match(auth: AuthContext, requested_account_id: str) -> None:
    if auth.is_admin:
        return
    if auth.account_id != requested_account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This API key is not authorized for this account.",
        )


def require_admin(auth: AuthContext) -> None:
    if not auth.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires an admin API key.",
        )


async def issue_api_key(
    account_id: str | None,
    is_admin: bool = False,
    label: str | None = None,
    *,
    issued_by: str | None = None,
    expires_in_days: int | None = None,
    rotation_days: int | None = None,
    replaces_key_id: int | None = None,
) -> str:
    """
    Create a new key. Returns raw key once.
    expires_in_days / rotation_days default from settings when None.
    """
    raw_key = secrets.token_urlsafe(32)
    key_hash = _hash_key(raw_key)
    now = datetime.now(timezone.utc)

    exp_days = expires_in_days if expires_in_days is not None else settings.API_KEY_DEFAULT_TTL_DAYS
    rot_days = rotation_days if rotation_days is not None else settings.API_KEY_ROTATION_DAYS

    expires_at = now + timedelta(days=exp_days) if exp_days and exp_days > 0 else None
    rotation_due_at = now + timedelta(days=rot_days) if rot_days and rot_days > 0 else None

    async with async_session_factory() as session:
        session.add(
            ApiKey(
                key_hash=key_hash,
                account_id=account_id,
                is_admin=is_admin,
                label=label,
                revoked=False,
                created_at=now,
                expires_at=expires_at,
                rotation_due_at=rotation_due_at,
                force_rotate=False,
                issued_by=issued_by,
                replaces_key_id=replaces_key_id,
            )
        )
        await session.commit()

    return raw_key


async def revoke_api_key(key_id: int, revoked_by: str | None = None) -> bool:
    async with async_session_factory() as session:
        result = await session.execute(select(ApiKey).where(ApiKey.id == key_id))
        row = result.scalar_one_or_none()
        if row is None:
            return False
        row.revoked = True
        row.revoked_by = revoked_by
        row.revoked_at = datetime.now(timezone.utc)
        await session.commit()
        return True


async def force_rotate_key(key_id: int, actor: str | None = None) -> bool:
    async with async_session_factory() as session:
        result = await session.execute(select(ApiKey).where(ApiKey.id == key_id))
        row = result.scalar_one_or_none()
        if row is None or row.revoked:
            return False
        row.force_rotate = True
        await session.commit()
        return True


def application_security_status() -> dict:
    return {
        "authentication": "Per-account API Key (X-API-Key), SHA-256 at rest",
        "authorization": "Object-level via require_account_match()",
        "key_lifecycle": "expires_at, rotation_due_at, force_rotate",
        "audit": "audit_events table (issue/revoke/rotate/subscription/access)",
        "encryption": "AES-256-GCM for broker credentials",
        "status": "Lifecycle Ready",
    }
