"""
====================================================================
Project : AEGIS
Company : Honeydewnuts Nigerian Limited

File    : device_health_service.py

Purpose
-------
Tracks the latest heartbeat per account/device so you (the operator)
have visibility into which of your subscribers' phones are actually
alive and capturing, at scale. Backed by Redis (same connection as
the job queue) since this is high-frequency, ephemeral data - not
worth a SQL table.
====================================================================
"""

from __future__ import annotations

import json
import time
from typing import Any

import redis.asyncio as redis

from app.core.logging import configure_logging

HEARTBEAT_TTL_SECONDS = 180   # ~3 missed heartbeats (heartbeat interval is 60s) before considered stale
DEVICE_SET_KEY = "devices:known"


class DeviceHealthService:

    def __init__(self, redis_client: "redis.Redis") -> None:
        self.logger = configure_logging(__name__)
        self._redis = redis_client

    def _key(self, account_id: str) -> str:
        return f"device_health:{account_id}"

    async def record_heartbeat(self, account_id: str, data: dict[str, Any]) -> None:
        payload = {**data, "received_at": time.time()}
        await self._redis.set(self._key(account_id), json.dumps(payload), ex=HEARTBEAT_TTL_SECONDS)
        await self._redis.sadd(DEVICE_SET_KEY, account_id)

    async def get_health(self, account_id: str) -> dict[str, Any] | None:
        raw = await self._redis.get(self._key(account_id))
        if raw is None:
            return None
        return json.loads(raw)

    async def list_all(self) -> list[dict[str, Any]]:
        """
        Operator-facing: every known device's latest status. Devices whose
        heartbeat expired (key TTL'd out) show as offline rather than
        vanishing silently, since knowing "this one went dark" matters.
        """
        account_ids = await self._redis.smembers(DEVICE_SET_KEY)
        results = []
        for account_id in account_ids:
            health = await self.get_health(account_id)
            if health is None:
                results.append({"account_id": account_id, "status": "offline", "reason": "no heartbeat within TTL"})
            else:
                age = time.time() - health.get("received_at", 0)
                results.append({"account_id": account_id, "status": "online", "seconds_since_heartbeat": round(age, 1), **health})
        return results
