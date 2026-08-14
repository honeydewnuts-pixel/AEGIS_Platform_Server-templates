"""
Per-account sliding-window rate limit using Redis when available.
Falls back to in-process counters if Redis is down (single-instance only).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import HTTPException, Request, status

from app.config import settings

# local fallback: account_id -> timestamps
_local: dict[str, Deque[float]] = defaultdict(deque)


async def enforce_account_rate_limit(request: Request, account_id: str) -> None:
    """
    Allow API_RATE_LIMIT_PER_MINUTE requests per account_id per rolling minute.
    Call after account_id is known (e.g. start of analyze / trading).
    """
    limit = int(getattr(settings, "API_RATE_LIMIT_PER_MINUTE", 120) or 120)
    if limit <= 0:
        return
    now = time.time()
    window = 60.0
    key = f"rl:acct:{account_id}"

    redis = None
    try:
        jq = getattr(request.app.state, "job_queue", None)
        if jq is not None:
            redis = jq.get_redis_client()
    except Exception:  # noqa: BLE001
        redis = None

    if redis is not None:
        try:
            pipe = redis.pipeline()
            pipe.zremrangebyscore(key, 0, now - window)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, int(window) + 5)
            results = await pipe.execute()
            count = int(results[2])
            if count > limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Account rate limit exceeded ({limit}/min). Slow down or upgrade plan.",
                )
            return
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001
            pass  # fall through to local

    q = _local[account_id]
    while q and q[0] < now - window:
        q.popleft()
    q.append(now)
    if len(q) > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account rate limit exceeded ({limit}/min).",
        )
