"""
One-time post-payment credential claim.

Contract (enforced here):
  - reveal_token / activation_ref is random, single-use, short TTL
  - successful claim DELETEs the token and pending credentials permanently
  - replay after claim → None (404)
  - expire after TTL → None
  - webhook must stash credentials before claim succeeds

Preferred public name: activation_ref (opaque claim ticket, not a portal credential).
"""

from __future__ import annotations

import json
import secrets
from typing import Any

import redis.asyncio as redis

from app.core.logging import configure_logging

# Short windows: reduces risk if activation_ref appears in logs/history briefly
REVEAL_TOKEN_TTL_SECONDS = 60 * 60  # 1h
PENDING_CREDENTIALS_TTL_SECONDS = 60 * 60  # 1h after activation


class CredentialRevealService:

    def __init__(self, redis_client: "redis.Redis") -> None:
        self.logger = configure_logging(__name__)
        self._redis = redis_client

    def _reveal_key(self, token: str) -> str:
        return f"reveal_token:{token}"

    def _pending_key(self, account_id: str) -> str:
        return f"pending_credentials:{account_id}"

    async def create_reveal_token(self, account_id: str) -> str:
        """Issue opaque activation_ref for payment success_url (not a credential)."""
        token = secrets.token_urlsafe(32)
        await self._redis.set(self._reveal_key(token), account_id, ex=REVEAL_TOKEN_TTL_SECONDS)
        return token

    # Alias for commercial naming
    async def create_activation_ref(self, account_id: str) -> str:
        return await self.create_reveal_token(account_id)

    async def stash_credentials(self, account_id: str, portal_token: str, mobile_api_key: str) -> None:
        payload = json.dumps({
            "portal_token": portal_token,
            "mobile_api_key": mobile_api_key,
            "account_id": account_id,
        })
        await self._redis.set(
            self._pending_key(account_id),
            payload,
            ex=PENDING_CREDENTIALS_TTL_SECONDS,
        )

    async def reveal(self, account_id: str, reveal_token: str) -> dict[str, Any] | None:
        """
        Single-use claim. Deletes activation_ref and pending credentials on success.
        """
        key = self._reveal_key(reveal_token)
        # Atomic get+delete of token
        stored_account = await self._redis.get(key)
        if stored_account is None:
            return None
        if isinstance(stored_account, bytes):
            stored_account = stored_account.decode("utf-8")
        if stored_account != account_id:
            return None
        await self._redis.delete(key)

        pending_raw = await self._redis.get(self._pending_key(account_id))
        if pending_raw is None:
            # Token was valid but webhook not ready — restore token briefly so client can retry
            await self._redis.set(key, account_id, ex=min(120, REVEAL_TOKEN_TTL_SECONDS))
            return None
        if isinstance(pending_raw, bytes):
            pending_raw = pending_raw.decode("utf-8")
        await self._redis.delete(self._pending_key(account_id))
        data = json.loads(pending_raw)
        self.logger.info("Activation claimed once for account_id=%s", account_id)
        return {
            "account_id": account_id,
            "portal_token": data["portal_token"],
            "mobile_api_key": data["mobile_api_key"],
        }
