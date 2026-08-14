import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.security import _hash_key, generate_secret_key


def test_hash_is_sha256():
    raw = "hello"
    assert _hash_key(raw) == hashlib.sha256(raw.encode()).hexdigest()


def test_generate_secret_key_length():
    k = generate_secret_key(16)
    assert len(k) >= 16


@pytest.mark.asyncio
async def test_expired_key_rejected():
    from app.security import verify_api_key
    from app.db.models import ApiKey
    from fastapi import HTTPException

    expired = MagicMock()
    expired.revoked = False
    expired.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    expired.force_rotate = False
    expired.account_id = "acc1"
    expired.is_admin = False
    expired.label = "old"
    expired.id = 1
    expired.rotation_due_at = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = expired

    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)
    session.commit = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    with patch("app.security.async_session_factory", return_value=session):
        with pytest.raises(HTTPException) as ei:
            await verify_api_key(x_api_key="any-key")
        assert ei.value.status_code == 401
        assert "expired" in ei.value.detail.lower()


@pytest.mark.asyncio
async def test_force_rotate_rejected():
    from app.security import verify_api_key
    from fastapi import HTTPException

    row = MagicMock()
    row.revoked = False
    row.expires_at = None
    row.force_rotate = True
    row.account_id = "acc1"
    row.is_admin = False
    row.label = "rot"
    row.id = 2
    row.rotation_due_at = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row
    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)
    session.commit = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    with patch("app.security.async_session_factory", return_value=session):
        with pytest.raises(HTTPException) as ei:
            await verify_api_key(x_api_key="any-key")
        assert ei.value.status_code == 401
        assert "rotation" in ei.value.detail.lower()
