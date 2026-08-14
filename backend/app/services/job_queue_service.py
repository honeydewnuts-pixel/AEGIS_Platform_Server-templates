"""
====================================================================
Project : AEGIS
Company : Honeydewnuts Nigerian Limited

File    : job_queue_service.py

Purpose
-------
Redis-backed job queue connecting the FastAPI API to the MT5
worker-pool. This exists because the MetaTrader5 Python package can
only hold one logged-in session per OS process - so instead of the
API calling MT5 directly (which would mean one global connection for
every user, the bug in the original code), the API enqueues a job
for a specific account's worker process and waits for the result.

Design
------
Each account gets its own Redis list acting as a queue:

    queue:account:{account_id}   <- worker BRPOPs jobs from here

Each job gets a unique job_id, and the worker pushes its result to:

    result:{job_id}               <- API BRPOPs (with timeout) from here,
                                      key expires automatically so results
                                      don't pile up if nobody collects them

This lets you scale by simply pointing more worker machines at the
same Redis instance - no API code changes needed to add workers.
====================================================================
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import redis.asyncio as redis

from app.config import settings
from app.core.logging import configure_logging

RESULT_KEY_TTL_SECONDS = 60


class JobQueueService:

    def __init__(self) -> None:
        self.logger = configure_logging(__name__)
        self._redis: redis.Redis | None = None

    async def connect(self) -> None:
        self._redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
        await self._redis.ping()
        self.logger.info("Connected to Redis at %s", settings.REDIS_URL)

    async def disconnect(self) -> None:
        if self._redis is not None:
            await self._redis.close()

    def get_redis_client(self):
        """Reused by IndicatorHistoryService so it doesn't open a second connection pool."""
        return self._redis

    def _queue_key(self, account_id: str) -> str:
        return f"queue:account:{account_id}"

    def _result_key(self, job_id: str) -> str:
        return f"result:{job_id}"

    # ------------------------------------------------------------
    # Producer side (called by trading_router)
    # ------------------------------------------------------------

    async def submit_job(
        self,
        account_id: str,
        job_type: str,
        payload: dict[str, Any],
    ) -> str:
        """Enqueue a job for the given account's worker. Returns job_id."""
        job_id = str(uuid.uuid4())
        job = {
            "job_id": job_id,
            "job_type": job_type,
            "payload": payload,
        }
        await self._redis.lpush(self._queue_key(account_id), json.dumps(job))
        return job_id

    async def await_result(
        self,
        job_id: str,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any] | None:
        """
        Block (async) until the worker publishes a result for job_id,
        or timeout_seconds elapses. Returns None on timeout.
        """
        timeout = timeout_seconds or settings.WORKER_JOB_TIMEOUT_SECONDS
        result = await self._redis.blpop([self._result_key(job_id)], timeout=timeout)
        if result is None:
            return None
        _, raw = result
        return json.loads(raw)

    async def submit_and_wait(
        self,
        account_id: str,
        job_type: str,
        payload: dict[str, Any],
        timeout_seconds: int | None = None,
    ) -> dict[str, Any] | None:
        job_id = await self.submit_job(account_id, job_type, payload)
        return await self.await_result(job_id, timeout_seconds)

    # ------------------------------------------------------------
    # Consumer side (called by mt5_worker.py)
    # ------------------------------------------------------------

    async def pop_job(self, account_id: str, timeout_seconds: int) -> dict[str, Any] | None:
        """Worker-side: block up to timeout_seconds waiting for the next job."""
        result = await self._redis.brpop([self._queue_key(account_id)], timeout=timeout_seconds)
        if result is None:
            return None
        _, raw = result
        return json.loads(raw)

    async def push_result(self, job_id: str, result: dict[str, Any]) -> None:
        key = self._result_key(job_id)
        await self._redis.lpush(key, json.dumps(result))
        await self._redis.expire(key, RESULT_KEY_TTL_SECONDS)

    # ------------------------------------------------------------
    # One-time credential handoff (avoids passing secrets via argv/env
    # where they'd be visible to anything reading process listings)
    # ------------------------------------------------------------

    async def stash_worker_credentials(self, account_id: str, credentials: dict[str, Any]) -> None:
        key = f"worker_creds:{account_id}"
        await self._redis.set(key, json.dumps(credentials), ex=60)

    async def fetch_worker_credentials(self, account_id: str) -> dict[str, Any] | None:
        key = f"worker_creds:{account_id}"
        raw = await self._redis.get(key)
        if raw is None:
            return None
        await self._redis.delete(key)
        return json.loads(raw)
