"""
====================================================================
Project : AEGIS
Company : Honeydewnuts Nigerian Limited

File    : worker_pool_manager.py

Purpose
-------
Manages the lifecycle of MT5 worker processes - one process per
connected broker account, since the MetaTrader5 Python package only
supports one logged-in session per process.

TEST-PHASE DESIGN (what this file implements now)
---------------------------------------------------
Workers are spawned as local subprocesses on the same machine as the
API, tracked in memory here. This is fine for testing with a small
number of accounts, and keeps everything runnable without extra
infrastructure.

AUDIT FINDING (fixed): is_running() used to check only this process's
local `self._workers` dict. If the API ever runs as more than one
process (uvicorn --workers > 1) or more than one container replica,
each instance has its own separate view - a request handled by
instance B would incorrectly report "not connected" for a worker
instance A actually spawned, since B's local dict never saw it. Every
trading_router endpoint gates on is_running(), so this would have
silently blocked legitimate requests as soon as you scaled the API
past one process.

Fixed by adding a Redis-backed registry (account_id -> spawning
instance) that is_running() checks instead of local memory alone.
This makes READS (is_running) correct across instances. WRITES
(ensure_worker/stop_worker actually spawning or killing a local
subprocess) still only work correctly when called on the same
instance that owns the process - that part of the constraint is
inherent to local subprocess.Popen and goes away entirely once you
follow the "scaling up later" step below (dispatch to remote Windows
workers instead of local subprocesses).

SCALING UP LATER (how to grow this without changing worker code)
---------------------------------------------------
mt5_worker.py only needs network access to Redis - it doesn't care
whether it's a local subprocess or a process on a completely separate
Windows machine/VM. To scale past what one host can run:

  1. Deploy mt5_worker.py to a fleet of Windows worker machines/VMs
     (MetaTrader5's Python package is Windows-only and needs the real
     MT5 terminal installed), all pointed at the same Redis instance.
  2. Replace this class's start_worker()/stop_worker() with calls to
     whatever you use to provision those machines (a simple internal
     dispatch API, a VM pool manager, Windows containers, etc.)
     instead of local subprocess.Popen.
  3. Everything else (JobQueueService, trading_router.py) stays the
     same, because they only talk to Redis, not to worker processes
     directly.
====================================================================
"""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.logging import configure_logging
from app.services.job_queue_service import JobQueueService

WORKER_MODULE = "app.worker.mt5_worker"
REGISTRY_KEY = "worker_registry"   # Redis hash: account_id -> json({instance, started_at})


class WorkerPoolManager:

    def __init__(self, job_queue: JobQueueService) -> None:
        self.logger = configure_logging(__name__)
        self.job_queue = job_queue
        self._workers: dict[str, subprocess.Popen] = {}
        self._lock = asyncio.Lock()
        self._instance_id = f"{socket.gethostname()}:{id(self)}"

    async def _registry_set(self, account_id: str) -> None:
        redis_client = self.job_queue.get_redis_client()
        payload = json.dumps({"instance": self._instance_id, "started_at": time.time()})
        await redis_client.hset(REGISTRY_KEY, account_id, payload)

    async def _registry_remove(self, account_id: str) -> None:
        redis_client = self.job_queue.get_redis_client()
        await redis_client.hdel(REGISTRY_KEY, account_id)

    async def ensure_worker(self, account_id: str, credentials: dict[str, Any]) -> bool:
        """
        Make sure a worker process is running and connected for this
        account. Spawns one if needed. Returns True if a worker is (or
        becomes) available, False if the pool is full or spawn failed.
        """
        async with self._lock:
            existing = self._workers.get(account_id)
            if existing is not None and existing.poll() is None:
                # Already running.
                return True

            if existing is not None:
                # Process died - clean up before respawning.
                self.logger.warning("Worker for %s exited, respawning.", account_id)
                self._workers.pop(account_id, None)

            if len(self._workers) >= settings.MAX_CONCURRENT_WORKERS:
                self.logger.error(
                    "Worker pool full (%s/%s). Refusing to start worker for %s.",
                    len(self._workers), settings.MAX_CONCURRENT_WORKERS, account_id,
                )
                return False

            # Hand off credentials via Redis (one-time key, short TTL)
            # rather than argv/env, so they don't sit in `ps` output.
            await self.job_queue.stash_worker_credentials(account_id, credentials)

            process = subprocess.Popen(
                [sys.executable, "-m", WORKER_MODULE, "--account-id", account_id],
                cwd=str(Path(__file__).resolve().parents[2]),  # backend/ directory
            )
            self._workers[account_id] = process
            await self._registry_set(account_id)
            self.logger.info("Spawned worker pid=%s for account %s", process.pid, account_id)
            return True

    async def stop_worker(self, account_id: str) -> bool:
        async with self._lock:
            process = self._workers.pop(account_id, None)
            await self._registry_remove(account_id)

            if process is None:
                # Not spawned by this instance - still push the STOP job
                # (the worker listens on Redis regardless of which API
                # instance sends it), but we can't wait/kill a process
                # handle we don't have. Log this clearly rather than
                # silently no-op - see module docstring's AUDIT FINDING.
                await self.job_queue.submit_job(account_id, "STOP", {})
                self.logger.warning(
                    "stop_worker(%s) called on an instance that didn't spawn it - "
                    "sent STOP via queue but cannot confirm the process actually exited.",
                    account_id,
                )
                return True

            # Ask nicely first via a STOP sentinel job, then hard-kill
            # if it doesn't exit within a few seconds.
            await self.job_queue.submit_job(account_id, "STOP", {})
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.logger.warning("Worker for %s did not stop gracefully, killing.", account_id)
                process.kill()

            self.logger.info("Stopped worker for account %s", account_id)
            return True

    async def stop_all(self) -> None:
        for account_id in list(self._workers.keys()):
            await self.stop_worker(account_id)

    async def is_running(self, account_id: str) -> bool:
        """
        Redis-backed so this is correct regardless of which API instance
        handles the request - see AUDIT FINDING in the module docstring.
        """
        redis_client = self.job_queue.get_redis_client()
        raw = await redis_client.hget(REGISTRY_KEY, account_id)
        return raw is not None

    def active_worker_count(self) -> int:
        """
        Local-only count (workers spawned BY THIS instance). Under a
        single-instance deployment this equals the true total; under
        multiple instances it undercounts - MAX_CONCURRENT_WORKERS is
        therefore enforced per-instance, not globally, until the
        "scaling up later" step in the module docstring replaces local
        subprocess spawning with remote dispatch.
        """
        return sum(1 for p in self._workers.values() if p.poll() is None)
