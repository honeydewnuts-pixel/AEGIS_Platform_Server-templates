"""
====================================================================
Project : AEGIS
Company : Honeydewnuts Nigerian Limited
File    : subscription_service.py

Tracks subscription status per account and enforces the grace-period
policy when payment fails. Backed by Postgres via SQLAlchemy (async) -
previously SQLite-file-backed; moved for the same multi-instance
reason as CredentialVaultService.

Status lifecycle:
    none -> active -> (payment fails) -> past_due -> (grace period
    expires) -> suspended -> (payment succeeds again) -> active
    active -> (canceled) -> canceled
====================================================================
"""

from __future__ import annotations

from app.services.plan_catalog import resolve_plan

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.core.logging import configure_logging
from app.db.base import async_session_factory
from app.db.models import ProcessedPaymentEvent, Subscription
from app.services.payment_providers.base import PaymentEvent, PaymentEventType
from app.security import issue_api_key


class SubscriptionService:

    def __init__(self) -> None:
        self.logger = configure_logging(__name__)

    # ------------------------------------------------------------
    # Idempotency - webhooks can be delivered more than once
    # ------------------------------------------------------------

    async def already_processed(self, provider: str, provider_event_id: str) -> bool:
        async with async_session_factory() as session:
            result = await session.execute(
                select(ProcessedPaymentEvent).where(
                    ProcessedPaymentEvent.provider == provider,
                    ProcessedPaymentEvent.provider_event_id == provider_event_id,
                )
            )
            return result.scalar_one_or_none() is not None

    # ------------------------------------------------------------
    # Event application
    # ------------------------------------------------------------

    async def apply_event(self, event: PaymentEvent) -> dict[str, str] | None:
        """
        Returns {"account_id", "portal_token", "mobile_api_key"} if this
        call represents a FIRST activation (new credentials were just
        issued) - the caller (subscription_router's webhook handler) uses
        this to stash them for one-time reveal via CredentialRevealService.
        Returns None for renewals, failures, or cancellations, since
        there's nothing new to reveal in those cases.
        """
        if not event.account_id:
            self.logger.warning("Payment event with no account_id, ignoring: %s", event.provider_event_id)
            return None

        now = datetime.now(timezone.utc)
        newly_issued: dict[str, str] | None = None

        async with async_session_factory() as session:
            if event.event_type == PaymentEventType.PAYMENT_SUCCEEDED:
                existing = await session.get(Subscription, event.account_id)
                is_first_activation = existing is None
                # Preserve the existing portal token across renewals - only
                # generate a new one the first time this account activates.
                portal_token = existing.portal_token if existing and existing.portal_token else secrets.token_urlsafe(24)

                stmt = pg_insert(Subscription).values(
                    account_id=event.account_id,
                    provider=event.provider,
                    provider_customer_id=event.provider_customer_id,
                    provider_subscription_id=event.provider_subscription_id,
                    status="active",
                    current_period_end=event.current_period_end,
                    grace_period_ends_at=None,
                    portal_token=portal_token,
                    updated_at=now,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["account_id"],
                    set_={
                        "provider": event.provider,
                        "provider_customer_id": event.provider_customer_id,
                        "provider_subscription_id": event.provider_subscription_id,
                        "status": "active",
                        "current_period_end": event.current_period_end,
                        "grace_period_ends_at": None,
                        "portal_token": portal_token,
                        "updated_at": now,
                    },
                )
                await session.execute(stmt)
                self.logger.info("Subscription activated/renewed: %s (%s)", event.account_id, event.provider)

                if is_first_activation:
                    # Issued after commit (outside this session) since
                    # issue_api_key opens its own session - keeps the two
                    # concerns (subscription state vs. credential issuance)
                    # decoupled rather than sharing a transaction.
                    await session.commit()
                    mobile_api_key = await issue_api_key(
                        account_id=event.account_id,
                        is_admin=False,
                        label=f"mobile app - {event.account_id}",
                    )
                    newly_issued = {
                        "account_id": event.account_id,
                        "portal_token": portal_token,
                        "mobile_api_key": mobile_api_key,
                    }
                    self.logger.info(
                        "First activation for %s - credentials issued, handed back for one-time reveal staging.",
                        event.account_id,
                    )

            elif event.event_type == PaymentEventType.PAYMENT_FAILED:
                grace_end = now + timedelta(days=settings.SUBSCRIPTION_GRACE_PERIOD_DAYS)
                row = await session.get(Subscription, event.account_id)
                if row is not None:
                    row.status = "past_due"
                    row.grace_period_ends_at = grace_end
                    row.updated_at = now
                self.logger.warning(
                    "Payment failed for %s - grace period until %s", event.account_id, grace_end.isoformat()
                )

            elif event.event_type == PaymentEventType.SUBSCRIPTION_CANCELED:
                row = await session.get(Subscription, event.account_id)
                if row is not None:
                    row.status = "canceled"
                    row.updated_at = now
                self.logger.info("Subscription canceled: %s", event.account_id)

            session.add(ProcessedPaymentEvent(
                provider=event.provider,
                provider_event_id=event.provider_event_id,
                processed_at=now,
            ))
            await session.commit()

        return newly_issued

    # ------------------------------------------------------------
    # Status checks
    # ------------------------------------------------------------

    async def get_status(self, account_id: str) -> dict[str, Any] | None:
        async with async_session_factory() as session:
            row = await session.get(Subscription, account_id)

        if row is None:
            return None

        return {
            "account_id": row.account_id,
            "provider": row.provider,
            "provider_customer_id": row.provider_customer_id,
            "provider_subscription_id": row.provider_subscription_id,
            "status": row.status,
            "current_period_end": row.current_period_end.isoformat() if row.current_period_end else None,
            "grace_period_ends_at": row.grace_period_ends_at.isoformat() if row.grace_period_ends_at else None,
            "updated_at": row.updated_at.isoformat(),
        }

    async def list_all(self) -> list[dict[str, Any]]:
        """Admin-dashboard-facing: every subscription record, most recently updated first."""
        async with async_session_factory() as session:
            result = await session.execute(select(Subscription).order_by(Subscription.updated_at.desc()))
            rows = result.scalars().all()

        return [
            {
                "account_id": r.account_id,
                "provider": r.provider,
                "status": r.status,
                "current_period_end": r.current_period_end.isoformat() if r.current_period_end else None,
                "grace_period_ends_at": r.grace_period_ends_at.isoformat() if r.grace_period_ends_at else None,
                "updated_at": r.updated_at.isoformat(),
            }
            for r in rows
        ]

    async def verify_portal_token(self, account_id: str, token: str) -> bool:
        async with async_session_factory() as session:
            row = await session.get(Subscription, account_id)
        if row is None or row.portal_token is None:
            return False
        return secrets.compare_digest(row.portal_token, token)

    async def is_active(self, account_id: str) -> bool:
        """
        True if the account can use the platform right now - either
        a clean 'active' subscription, or 'past_due' but still inside
        the grace period.
        """
        async with async_session_factory() as session:
            row = await session.get(Subscription, account_id)

        if row is None:
            return False
        if row.status == "active":
            return True
        if row.status == "past_due" and row.grace_period_ends_at:
            return datetime.now(timezone.utc) < row.grace_period_ends_at
        return False

    async def get_lapsed_accounts(self) -> list[str]:
        """Accounts whose grace period has expired but are still 'past_due'."""
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            result = await session.execute(
                select(Subscription.account_id).where(
                    Subscription.status == "past_due",
                    Subscription.grace_period_ends_at < now,
                )
            )
            return [row[0] for row in result.all()]

    async def mark_suspended(self, account_id: str) -> None:
        async with async_session_factory() as session:
            row = await session.get(Subscription, account_id)
            if row is not None:
                row.status = "suspended"
                row.updated_at = datetime.now(timezone.utc)
                await session.commit()

    async def mark_canceled(self, account_id: str) -> None:
        async with async_session_factory() as session:
            row = await session.get(Subscription, account_id)
            if row is not None:
                row.status = "canceled"
                row.updated_at = datetime.now(timezone.utc)
                await session.commit()

    async def get_plan(self, account_id: str) -> str:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.account_id == account_id)
            )
            row = result.scalar_one_or_none()
        if row is None:
            return "none"
        plan = getattr(row, "plan", None) or "live"
        if row.status in ("active", "past_due", "demo"):
            if row.status == "demo":
                return "demo"
            return plan or "starter"
        return "none"

    async def allows_brain(self, account_id: str) -> bool:
        return (await self.get_plan(account_id)) in ("live", "demo")

    async def allows_live_trading(self, account_id: str) -> bool:
        plan_code = await self.get_plan(account_id)
        if plan_code in ("none",):
            return False
        if not await self.is_active(account_id) and plan_code != "demo":
            return False
        return bool(resolve_plan(plan_code).get("live_trading"))

    async def activate_demo(self, account_id: str) -> dict[str, str]:
        from datetime import datetime, timedelta, timezone
        import secrets as sec
        now = datetime.now(timezone.utc)
        portal_token = sec.token_urlsafe(24)
        async with async_session_factory() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.account_id == account_id)
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.status = "active"
                existing.plan = "demo"
                existing.max_devices = 1
                existing.max_trades_per_day = 5
                existing.updated_at = now
                existing.current_period_end = now + timedelta(days=14)
                if not existing.portal_token:
                    existing.portal_token = portal_token
                else:
                    portal_token = existing.portal_token
            else:
                session.add(Subscription(
                    account_id=account_id,
                    provider="demo",
                    status="active",
                    plan="demo",
                    max_devices=1,
                    max_trades_per_day=5,
                    portal_token=portal_token,
                    current_period_end=now + timedelta(days=14),
                    updated_at=now,
                ))
            await session.commit()
        mobile_api_key = await issue_api_key(
            account_id=account_id,
            is_admin=False,
            label=f"demo mobile key for {account_id}",
            issued_by="demo_signup",
        )
        return {
            "account_id": account_id,
            "portal_token": portal_token,
            "mobile_api_key": mobile_api_key,
            "plan": "demo",
        }
