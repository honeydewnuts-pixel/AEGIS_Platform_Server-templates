"""
Project : AEGIS
Company : Honeydewnuts Nigerian Limited
File    : payment_providers/stripe_adapter.py

Uses the official `stripe` package for webhook signature verification
(stripe.Webhook.construct_event) rather than hand-rolling HMAC - Stripe's
scheme includes a timestamp-tolerance check that's easy to get subtly
wrong by hand, and their SDK is the documented, supported way to do it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import stripe

from app.config import settings
from app.core.logging import configure_logging
from app.services.payment_providers.base import (
    CheckoutSession,
    PaymentEvent,
    PaymentEventType,
    PaymentProviderAdapter,
)

PLAN_PRICE_IDS = {
    # Create these Price objects in the Stripe dashboard first, then paste the IDs here.
    "monthly": "price_REPLACE_WITH_REAL_PRICE_ID",
}

EVENT_MAP = {
    "checkout.session.completed": PaymentEventType.PAYMENT_SUCCEEDED,
    "invoice.paid": PaymentEventType.PAYMENT_SUCCEEDED,
    "invoice.payment_failed": PaymentEventType.PAYMENT_FAILED,
    "customer.subscription.deleted": PaymentEventType.SUBSCRIPTION_CANCELED,
}


class StripeAdapter(PaymentProviderAdapter):
    name = "stripe"

    def __init__(self) -> None:
        self.logger = configure_logging(__name__)
        stripe.api_key = settings.STRIPE_SECRET_KEY
        self.webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    def verify_webhook_signature(self, raw_body: bytes, headers: dict[str, str]) -> bool:
        sig_header = headers.get("stripe-signature", "")
        try:
            stripe.Webhook.construct_event(raw_body, sig_header, self.webhook_secret)
            return True
        except (stripe.error.SignatureVerificationError, ValueError):
            return False

    def parse_webhook_event(self, raw_body: bytes) -> PaymentEvent:
        import json
        # Signature already verified by verify_webhook_signature before this is
        # called (see subscription_router.py) - just parse the JSON here.
        event = json.loads(raw_body)

        event_type_str = event.get("type", "")
        obj = event.get("data", {}).get("object", {})
        metadata = obj.get("metadata", {}) or {}

        period_end = None
        if obj.get("current_period_end"):
            period_end = datetime.fromtimestamp(obj["current_period_end"], tz=timezone.utc)

        return PaymentEvent(
            provider=self.name,
            provider_event_id=event.get("id", str(uuid.uuid4())),
            event_type=EVENT_MAP.get(event_type_str, PaymentEventType.UNKNOWN),
            account_id=metadata.get("account_id") or obj.get("client_reference_id", ""),
            provider_customer_id=obj.get("customer"),
            provider_subscription_id=obj.get("subscription") or obj.get("id"),
            current_period_end=period_end,
            raw_payload=event,
        )

    async def create_checkout_session(self, account_id: str, email: str, plan: str, reveal_token: str) -> CheckoutSession:
        price_id = PLAN_PRICE_IDS.get(plan, PLAN_PRICE_IDS["monthly"])

        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=email,
            client_reference_id=account_id,
            metadata={"account_id": account_id, "plan": plan},
            success_url=f"{settings.PORTAL_BASE_URL}/success.html?account_id={account_id}&reveal_token={reveal_token}",
            cancel_url=f"{settings.PORTAL_BASE_URL}/index.html",
        )
        return CheckoutSession(checkout_url=session.url, reference=session.id)

    async def cancel_subscription(self, provider_subscription_id: str, provider_customer_id: str | None = None) -> bool:
        try:
            stripe.Subscription.delete(provider_subscription_id)
            return True
        except stripe.error.StripeError as exc:
            self.logger.error("Stripe cancel failed: %s", exc)
            return False
