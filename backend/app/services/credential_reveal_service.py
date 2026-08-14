"""
====================================================================
Project : AEGIS
Company : Honeydewnuts Nigerian Limited

File    : credential_reveal_service.py

Purpose
-------
Solves a real gap: a brand-new subscriber has no way to receive their
portal_token or mobile API key. Previously these were only logged
server-side (see SubscriptionService.apply_event) - fine for you
testing your own account, useless for an actual subscriber.

This implements the standard SaaS pattern instead:
  1. At checkout creation, issue a random "reveal token" tied to the
     account_id the subscriber is signing up for, and include both in
     the payment provider's success_url as query params.
  2. When the webhook activates the subscription, stash the newly
     issued portal_token + mobile_api_key in Redis, keyed by account_id,
     with a short claim window.
  3. The subscriber's browser, redirected back after payment, calls
     GET /api/subscriptions/reveal with the account_id + reveal_token
     from the URL. If they match, the stashed credentials are returned
     ONCE and immediately deleted - a replayed/leaked URL after that
     point returns nothing.

This is still not real subscriber account management (no password reset,
no email delivery as a backup channel if the browser tab is closed
before claiming) - see docs/SECURITY.md for what's still a documented
gap versus what this actually solves.
====================================================================
"""

from __future__ import annotations

import json
import secrets
from typing import Any

import redis.asyncio as redis

from app.core.logging import configure_logging

REVEAL_TOKEN_TTL_SECONDS = 24 * 60 * 60      # 24h - covers checkout abandonment and return
PENDING_CREDENTIALS_TTL_SECONDS = 60 * 60    # 1h claim window after activation


class CredentialRevealService:

    def __init__(self, redis_client: "redis.Redis") -> None:
        self.logger = configure_logging(__name__)
        self._redis = redis_client

    def _reveal_key(self, token: str) -> str:
        return f"reveal_token:{token}"

    def _pending_key(self, account_id: str) -> str:
        return f"pending_credentials:{account_id}"

    async def create_reveal_token(self, account_id: str) -> str:
        token = secrets.token_urlsafe(24)
        await self._redis.set(self._reveal_key(token), account_id, ex=REVEAL_TOKEN_TTL_SECONDS)
        return token

    async def stash_credentials(self, account_id: str, portal_token: str, mobile_api_key: str) -> None:
        payload = json.dumps({"portal_token": portal_token, "mobile_api_key": mobile_api_key})
        await self._redis.set(self._pending_key(account_id), payload, ex=PENDING_CREDENTIALS_TTL_SECONDS)
        self.logger.info("Credentials staged for one-time reveal: %s", account_id)

    async def reveal(self, account_id: str, token: str) -> dict[str, Any] | None:
        """Returns credentials once, or None if the token is wrong/expired/
        already used, or the subscription hasn't activated yet."""
        stored_account_id = await self._redis.get(self._reveal_key(token))
        if stored_account_id is None or stored_account_id != account_id:
            return None

        pending_raw = await self._redis.get(self._pending_key(account_id))
        if pending_raw is None:
            return None  # not activated yet, or claim window expired

        # Single-use: delete both immediately after a successful read.
        await self._redis.delete(self._reveal_key(token))
        await self._redis.delete(self._pending_key(account_id))

        return json.loads(pending_raw)
