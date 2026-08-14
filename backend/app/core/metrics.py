"""
Project : AEGIS
Company : Honeydewnuts Nigerian Limited
File    : app/core/metrics.py

HTTP request count/latency/status metrics come for free from
prometheus-fastapi-instrumentator (wired in main.py). This file adds
the business-specific gauges that actually matter for operating a
fleet of subscribers - active workers, subscription status breakdown,
device fleet health.

These are polled on scrape (Gauge.set_function) rather than pushed on
every event, since that keeps them always-consistent with current
Redis/DB state even if an update event was somehow missed.
"""

from __future__ import annotations

import asyncio

from prometheus_client import Gauge

from app.core.logging import configure_logging

logger = configure_logging(__name__)

active_workers_gauge = Gauge("aegis_active_workers", "MT5 worker processes currently running on this instance")
devices_online_gauge = Gauge("aegis_devices_online", "Mobile devices with a heartbeat within the TTL window")
devices_total_gauge = Gauge("aegis_devices_total", "Mobile devices that have ever reported in")
subscriptions_active_gauge = Gauge("aegis_subscriptions_active", "Subscriptions currently active or in grace period")


async def refresh_metrics_loop(app) -> None:
    """
    Background task, mirrors the pattern used by the subscription sweep -
    periodically recomputes gauges from the real source of truth (Redis/DB)
    rather than trying to keep them updated inline at every call site,
    which is easy to miss and get out of sync.
    """
    while True:
        try:
            worker_pool = getattr(app.state, "worker_pool", None)
            if worker_pool is not None:
                active_workers_gauge.set(worker_pool.active_worker_count())

            device_health = getattr(app.state, "device_health", None)
            if device_health is not None:
                devices = await device_health.list_all()
                devices_total_gauge.set(len(devices))
                devices_online_gauge.set(sum(1 for d in devices if d.get("status") == "online"))

            subscription_service = getattr(app.state, "subscription_service", None)
            if subscription_service is not None:
                subscriptions = await subscription_service.list_all()
                subscriptions_active_gauge.set(
                    sum(1 for s in subscriptions if s["status"] in ("active", "past_due"))
                )

        except Exception:
            logger.exception("Metrics refresh iteration failed.")

        await asyncio.sleep(30)
