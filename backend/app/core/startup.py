"""
Project: AEGIS
Company: Honeydewnuts Nigerian Limited

Application startup / shutdown lifecycle events.

Shared singletons (job queue, worker pool manager) are attached to
app.state rather than module-level globals, so they're accessed
through FastAPI's request object / dependency system instead of
relying on import-time ordering.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI

from app.config import settings
from app.services.job_queue_service import JobQueueService
from app.services.worker_pool_manager import WorkerPoolManager
from app.services.credential_vault_service import CredentialVaultService
from app.services.indicator_history_service import IndicatorHistoryService
from app.services.brain_cv_service import BrainCVService
from app.services.subscription_service import SubscriptionService
from app.services.device_health_service import DeviceHealthService
from app.services.credential_reveal_service import CredentialRevealService
from app.services.signal_history_service import SignalHistoryService
from app.services.audit_service import AuditService
from app.services.upload_diagnostic_service import UploadDiagnosticService
from app.services.alert_service import AlertService
from app.services.device_binding_service import DeviceBindingService
from app.services.trade_limit_service import TradeLimitService
from app.services.retention_service import purge_old_records
from app.services.template_profile_service import TemplateProfileService
from app.core.metrics import refresh_metrics_loop
from app.security import issue_api_key
from app.db.base import async_session_factory
from app.db.models import ApiKey
from sqlalchemy import select

logger = logging.getLogger("AEGIS")


async def _subscription_sweep_loop(app: FastAPI) -> None:
    """
    Background task: periodically disconnect any account whose grace
    period has expired but is still connected. Without this, an account
    could stay connected indefinitely as long as it never happens to
    call an endpoint that checks subscription status.
    """
    subscription_service: SubscriptionService = app.state.subscription_service
    worker_pool: WorkerPoolManager = app.state.worker_pool

    while True:
        try:
            lapsed = await subscription_service.get_lapsed_accounts()
            for account_id in lapsed:
                if await worker_pool.is_running(account_id):
                    logger.warning("Subscription grace period expired for %s - disconnecting.", account_id)
                    await worker_pool.stop_worker(account_id)
                await subscription_service.mark_suspended(account_id)
        except Exception:
            logger.exception("Subscription sweep iteration failed.")

        await asyncio.sleep(settings.SUBSCRIPTION_SWEEP_INTERVAL_SECONDS)


async def on_startup(app: FastAPI) -> None:
    logger.info("========================================")
    logger.info("AEGIS Backend Starting...")
    logger.info("Company: Honeydewnuts Nigerian Limited")
    logger.info("========================================")

    app.state.vault = CredentialVaultService()
    app.state.subscription_service = SubscriptionService()

    app.state.job_queue = JobQueueService()
    await app.state.job_queue.connect()

    app.state.worker_pool = WorkerPoolManager(app.state.job_queue)

    app.state.brain_cv_service = BrainCVService()
    app.state.indicator_history = IndicatorHistoryService(
        app.state.job_queue.get_redis_client(), app.state.brain_cv_service.config
    )
    app.state.device_health = DeviceHealthService(app.state.job_queue.get_redis_client())
    app.state.credential_reveal = CredentialRevealService(app.state.job_queue.get_redis_client())
    app.state.signal_history = SignalHistoryService()
    app.state.audit_service = AuditService()
    app.state.upload_diagnostics = UploadDiagnosticService()
    app.state.alert_service = AlertService()
    app.state.device_bindings = DeviceBindingService()
    app.state.trade_limits = TradeLimitService()
    app.state.templates = TemplateProfileService()

    app.state.subscription_sweep_task = asyncio.create_task(_subscription_sweep_loop(app))
    app.state.metrics_task = asyncio.create_task(refresh_metrics_loop(app))

    async def _retention_loop():
        while True:
            try:
                await purge_old_records()
            except Exception:
                logger.exception("Retention purge failed")
            await asyncio.sleep(24 * 3600)

    app.state.retention_task = asyncio.create_task(_retention_loop())


    # Identity / support tables (create_all is idempotent for existing tables)
    try:
        from app.services.auth_service import AuthService
        await AuthService().ensure_tables()
        logger.info("Auth/support tables ensured")
    except Exception:
        logger.exception("Auth table ensure failed")

    await _bootstrap_admin_key()

    logger.info("Job queue + worker pool manager + indicator history + subscriptions + metrics ready.")


async def _bootstrap_admin_key() -> None:
    """
    Ensure an admin API key exists.

    - If FORCE_ADMIN_KEY_RESET is true and ADMIN_BOOTSTRAP_KEY is set:
      revoke all existing admin keys and register the bootstrap value.
      Use this once on Render after losing the original key.
    - Else if no admin key exists:
      register ADMIN_BOOTSTRAP_KEY if set, otherwise auto-generate and log once.
    - Else: leave existing admin keys alone.
    """
    from app.config import settings
    import hashlib
    from datetime import datetime, timezone
    from app.db.models import ApiKey as ApiKeyModel

    force = bool(settings.FORCE_ADMIN_KEY_RESET)
    bootstrap = (settings.ADMIN_BOOTSTRAP_KEY or "").strip()

    async with async_session_factory() as session:
        result = await session.execute(
            select(ApiKey).where(ApiKey.is_admin == True)  # noqa: E712
        )
        existing_admins = list(result.scalars().all())

    if force:
        if not bootstrap:
            logger.error(
                "FORCE_ADMIN_KEY_RESET=true but ADMIN_BOOTSTRAP_KEY is empty - refusing to wipe admin keys."
            )
            return
        async with async_session_factory() as session:
            result = await session.execute(
                select(ApiKeyModel).where(ApiKeyModel.is_admin == True)  # noqa: E712
            )
            for row in result.scalars().all():
                row.revoked = True
            session.add(
                ApiKeyModel(
                    key_hash=hashlib.sha256(bootstrap.encode()).hexdigest(),
                    account_id=None,
                    is_admin=True,
                    label="admin key reset from ADMIN_BOOTSTRAP_KEY",
                    revoked=False,
                    created_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
        logger.warning(
            "Admin keys reset from ADMIN_BOOTSTRAP_KEY (FORCE_ADMIN_KEY_RESET=true). "
            "Set FORCE_ADMIN_KEY_RESET=false after verifying login."
        )
        return

    if existing_admins:
        # Optionally ensure bootstrap key is ALSO valid as admin (if set and not already present)
        if bootstrap:
            bh = hashlib.sha256(bootstrap.encode()).hexdigest()
            async with async_session_factory() as session:
                result = await session.execute(
                    select(ApiKeyModel).where(ApiKeyModel.key_hash == bh)
                )
                row = result.scalar_one_or_none()
                if row is None:
                    session.add(
                        ApiKeyModel(
                            key_hash=bh,
                            account_id=None,
                            is_admin=True,
                            label="bootstrap admin key (synced from ADMIN_BOOTSTRAP_KEY)",
                            revoked=False,
                            created_at=datetime.now(timezone.utc),
                        )
                    )
                    await session.commit()
                    logger.info("Synced ADMIN_BOOTSTRAP_KEY as an additional admin API key.")
                elif row.revoked:
                    row.revoked = False
                    row.is_admin = True
                    await session.commit()
                    logger.info("Re-activated ADMIN_BOOTSTRAP_KEY admin API key.")
        return

    if bootstrap:
        async with async_session_factory() as session:
            session.add(
                ApiKeyModel(
                    key_hash=hashlib.sha256(bootstrap.encode()).hexdigest(),
                    account_id=None,
                    is_admin=True,
                    label="bootstrap admin key (from ADMIN_BOOTSTRAP_KEY env)",
                    revoked=False,
                    created_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
        logger.info("Admin API key registered from ADMIN_BOOTSTRAP_KEY.")
    else:
        raw_key = await issue_api_key(
            account_id=None,
            is_admin=True,
            label="auto-generated bootstrap admin key",
        )
        logger.warning(
            "========================================\n"
            "No admin API key existed - generated one:\n"
            "  %s\n"
            "This is the ONLY time it will be shown in plaintext. Save it now.\n"
            "Or set ADMIN_BOOTSTRAP_KEY in the environment and redeploy.\n"
            "========================================",
            raw_key,
        )


async def on_shutdown(app: FastAPI) -> None:
    logger.info("AEGIS Backend shutting down...")

    sweep_task = getattr(app.state, "subscription_sweep_task", None)
    if sweep_task is not None:
        sweep_task.cancel()

    metrics_task = getattr(app.state, "metrics_task", None)
    if metrics_task is not None:
        metrics_task.cancel()

    worker_pool: WorkerPoolManager | None = getattr(app.state, "worker_pool", None)
    if worker_pool is not None:
        await worker_pool.stop_all()

    job_queue: JobQueueService | None = getattr(app.state, "job_queue", None)
    if job_queue is not None:
        await job_queue.disconnect()

    logger.info("AEGIS Backend stopped.")
