"""
====================================================================
Project : AEGIS
Company : Honeydewnuts Nigerian Limited

File    : indicator_history_service.py

Purpose
-------
A single screenshot tells you WHERE each indicator line is right now.
Most of the rulebook's language - "has crossed", "makes higher/high",
"makes divergence" - is about how that position CHANGED over recent
frames. This service keeps a short rolling history per account so
SignalRuleEngine can compare "now" against "a few frames ago" instead
of only ever seeing a single instant.

Storage: a Redis SORTED SET, one per account_id, scored by the
frame's actual CAPTURE timestamp (not server-receive time). This
matters because of offline caching on the mobile side: if the phone
loses connectivity, it queues screenshots locally and replays them
later, possibly interleaved with fresh live captures. A plain list
(ordered by arrival) would let a late-arriving old frame corrupt the
chronological sequence the rule engine depends on. A sorted set fixes
this by construction - frames always come back out in true capture
order (ZRANGE by score), and trimming removes the chronologically
oldest entries (ZREMRANGEBYRANK), regardless of send order.

Requires the mobile app to send an account_id and a captured_at_ms
timestamp with each screenshot - see brain_router.py.
====================================================================
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import redis.asyncio as redis

from app.core.logging import configure_logging


class IndicatorHistoryService:

    def __init__(self, redis_client: "redis.Redis", config: dict[str, Any]) -> None:
        self.logger = configure_logging(__name__)
        self._redis = redis_client
        history_cfg = config.get("history", {})
        self.max_frames = history_cfg.get("max_frames_kept", 60)
        self.ttl_seconds = history_cfg.get("ttl_seconds", 600)

    def _key(self, account_id: str) -> str:
        return f"indicator_history:{account_id}"

    async def append_frame(
        self,
        account_id: str,
        frame_state: dict[str, Any],
        captured_at_ms: int | None = None,
    ) -> None:
        """
        captured_at_ms should be the client's original capture time
        (System.currentTimeMillis() on the phone), not now(). Falls
        back to server-receive time only if the client didn't send one
        (e.g. an older app build) - live traffic won't hit this case
        once the mobile app is updated to always send it.
        """
        ts = (captured_at_ms / 1000.0) if captured_at_ms is not None else time.time()

        # ZSET members must be unique strings; two frames could in theory
        # share a millisecond timestamp, so tag on a short nonce.
        frame_state = {**frame_state, "_ts": ts}
        member = json.dumps({**frame_state, "_nonce": uuid.uuid4().hex[:8]})

        key = self._key(account_id)
        await self._redis.zadd(key, {member: ts})
        # Keep only the max_frames most recent BY TIMESTAMP (rank order in a
        # sorted set is score order, so this correctly trims the chronologically
        # oldest entries even if they were the most recently *sent*).
        await self._redis.zremrangebyrank(key, 0, -(self.max_frames + 1))
        await self._redis.expire(key, self.ttl_seconds)

    async def get_history(self, account_id: str) -> list[dict[str, Any]]:
        key = self._key(account_id)
        raw_frames = await self._redis.zrange(key, 0, -1)  # ascending score = chronological order
        frames = []
        for raw in raw_frames:
            parsed = json.loads(raw)
            parsed.pop("_nonce", None)
            frames.append(parsed)
        return frames

    async def clear(self, account_id: str) -> None:
        await self._redis.delete(self._key(account_id))
