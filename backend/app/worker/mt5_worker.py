"""
====================================================================
Project : AEGIS
Company : Honeydewnuts Nigerian Limited

File    : app/worker/mt5_worker.py

Purpose
-------
Runs as its own OS process. Owns exactly ONE MT5 terminal connection
for exactly ONE broker account - this is a hard constraint of the
MetaTrader5 Python package (Windows-only, one session per process),
not a choice made here.

Run directly (this is what WorkerPoolManager does for you):

    python -m app.worker.mt5_worker --account-id 12345678

Requirements
------------
This process must run on a Windows machine with the real MT5
terminal installed, and with requirements-worker.txt installed
(NOT requirements.txt - MetaTrader5 has no Linux wheels).

Lifecycle
---------
1. Fetch this account's credentials from Redis (one-time key, pushed
   by WorkerPoolManager.ensure_worker() just before spawning us).
2. Connect to MT5.
3. Loop: block waiting for jobs on this account's queue.
   - "STOP" job -> disconnect and exit.
   - Any other job_type -> dispatch to MT5ExecutionService, push result.
   - No job within WORKER_IDLE_TIMEOUT_SECONDS -> disconnect and exit
     (WorkerPoolManager will simply respawn us on the next request).
====================================================================
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.config import settings
from app.core.logging import configure_logging
from app.schemas.trading import (
    MarketOrderRequest,
    PendingOrderRequest,
    ModifyPositionRequest,
    ClosePositionRequest,
)
from app.services.job_queue_service import JobQueueService
from app.services.mt5_execution_service import MT5ExecutionService

logger = configure_logging(__name__)

# job_type -> (schema class or None, execution_service method name)
JOB_DISPATCH = {
    "market_order": (MarketOrderRequest, "execute_market_order"),
    "pending_order": (PendingOrderRequest, "execute_pending_order"),
    "modify_position": (ModifyPositionRequest, "modify_trade"),
    "close_position": (ClosePositionRequest, "close_trade"),
    "cancel_order": (None, "cancel_order"),        # payload: {"ticket": int}
    "get_positions": (None, "get_positions"),
    "get_orders": (None, "get_pending_orders"),
    "get_account": (None, "get_account"),
    "get_symbol": (None, "get_symbol"),             # payload: {"symbol": str}
    "health": (None, "health_check"),
}


async def run_worker(account_id: str) -> None:
    job_queue = JobQueueService()
    await job_queue.connect()

    credentials = await job_queue.fetch_worker_credentials(account_id)
    if credentials is None:
        logger.error(
            "No credentials found for account %s (one-time key expired or "
            "already consumed). Exiting.", account_id,
        )
        return

    execution_service = MT5ExecutionService()

    connected = await execution_service.connect(credentials)
    if not connected:
        logger.error("Failed to connect MT5 for account %s. Exiting.", account_id)
        return

    logger.info("Worker ready for account %s. Waiting for jobs.", account_id)

    try:
        while True:
            job = await job_queue.pop_job(
                account_id, timeout_seconds=settings.WORKER_IDLE_TIMEOUT_SECONDS
            )

            if job is None:
                logger.info(
                    "No jobs for account %s in %ss - idling out.",
                    account_id, settings.WORKER_IDLE_TIMEOUT_SECONDS,
                )
                break

            if job["job_type"] == "STOP":
                logger.info("Received STOP for account %s.", account_id)
                break

            await handle_job(execution_service, job_queue, job)

    finally:
        await execution_service.disconnect()
        await job_queue.disconnect()
        logger.info("Worker for account %s shut down.", account_id)


async def handle_job(execution_service: MT5ExecutionService, job_queue: JobQueueService, job: dict) -> None:
    job_id = job["job_id"]
    job_type = job["job_type"]
    payload = job.get("payload", {})

    entry = JOB_DISPATCH.get(job_type)
    if entry is None:
        await job_queue.push_result(job_id, {"success": False, "message": f"Unknown job_type: {job_type}"})
        return

    schema_cls, method_name = entry
    method = getattr(execution_service, method_name)

    try:
        if schema_cls is not None:
            request_obj = schema_cls(**payload)
            result = await method(request_obj)
        elif payload:
            result = await method(**payload)
        else:
            result = await method()

        # Result may be a Pydantic model, a list of them, or a plain dict/None.
        if hasattr(result, "model_dump"):
            result_payload = result.model_dump(mode="json")
        elif isinstance(result, list):
            result_payload = [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in result
            ]
        else:
            result_payload = result

        await job_queue.push_result(job_id, {"success": True, "result": result_payload})

    except Exception as exc:  # noqa: BLE001 - must always push a result, even on failure
        logger.exception("Job %s (%s) failed", job_id, job_type)
        await job_queue.push_result(job_id, {"success": False, "message": str(exc)})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", required=True)
    args = parser.parse_args()

    if sys.platform != "win32":
        logger.warning(
            "This worker is designed to run on Windows with the MT5 "
            "terminal installed. Current platform: %s. Continuing anyway "
            "since MetaTrader5 import will fail loudly if unsupported.",
            sys.platform,
        )

    asyncio.run(run_worker(args.account_id))


if __name__ == "__main__":
    main()
