"""
Project : AEGIS
Company : Honeydewnuts Nigerian Limited
File    : payment_providers/paystack_adapter.py

Paystack webhook signature: HMAC-SHA512 of the raw request body using
your secret key, compared against the 'x-paystack-signature' header.
Docs: https://paystack.com/docs/payments/webhooks/
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime

import httpx

from app.config import settings
from app.core.logging import configure_logging
from app.services.payment_providers.base import (
    CheckoutSession,
    PaymentEvent,
    PaymentEventType,
    PaymentProviderAdapter,
)

PAYSTACK_BASE_URL = "https://api.paystack.co"

# event -> PaymentEventType
EVENT_MAP = {
    "charge.success": PaymentEventType.PAYMENT_SUCCEEDED,
    "subscription.create": PaymentEventType.PAYMENT_SUCCEEDED,
    "invoice.payment_failed": PaymentEventType.PAYMENT_FAILED,
    "subscription.disable": PaymentEventType.SUBSCRIPTION_CANCELED,
}

# plan -> (amount in Kobo, i.e. Naira * 100)
PLAN_AMOUNTS_KOBO = {
    "monthly": 500000,   # NGN 5,000.00 - adjust to your real pricing
}


class PaystackAdapter(PaymentProviderAdapter):
    name = "paystack"

    def __init__(self) -> None:
        self.logger = configure_logging(__name__)
        self.secret_key = settings.PAYSTACK_SECRET_KEY

    def verify_webhook_signature(self, raw_body: bytes, headers: dict[str, str]) -> bool:
        received = headers.get("x-paystack-signature", "")
        expected = hmac.new(self.secret_key.encode(), raw_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(received, expected)

    def parse_webhook_event(self, raw_body: bytes) -> PaymentEvent:
        payload = json.loads(raw_body)
        event = payload.get("event", "")
        data = payload.get("data", {})
        metadata = data.get("metadata", {}) or {}

        current_period_end = None
        if data.get("next_payment_date"):
            try:
                current_period_end = datetime.fromisoformat(data["next_payment_date"].replace("Z", "+00:00"))
            except ValueError:
                pass

        return PaymentEvent(
            provider=self.name,
            provider_event_id=str(data.get("id") or data.get("reference") or uuid.uuid4()),
            event_type=EVENT_MAP.get(event, PaymentEventType.UNKNOWN),
            account_id=metadata.get("account_id", ""),
            provider_customer_id=(data.get("customer") or {}).get("customer_code"),
            provider_subscription_id=data.get("subscription_code"),
            current_period_end=current_period_end,
            raw_payload=payload,
        )

    async def create_checkout_session(self, account_id: str, email: str, plan: str, reveal_token: str) -> CheckoutSession:
        reference = f"aegis-{account_id}-{uuid.uuid4().hex[:10]}"
        amount = PLAN_AMOUNTS_KOBO.get(plan, PLAN_AMOUNTS_KOBO["monthly"])

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{PAYSTACK_BASE_URL}/transaction/initialize",
                headers={"Authorization": f"Bearer {self.secret_key}"},
                json={
                    "email": email,
                    "amount": amount,
                    "reference": reference,
                    "callback_url": f"{settings.PORTAL_BASE_URL}/success.html?account_id={account_id}&reveal_token={reveal_token}",
                    "metadata": {"account_id": account_id, "plan": plan},
                },
                timeout=15,
            )
            resp.raise_for_status()
            body = resp.json()

        return CheckoutSession(
            checkout_url=body["data"]["authorization_url"],
            reference=body["data"]["reference"],
        )

    async def cancel_subscription(self, provider_subscription_id: str, provider_customer_id: str | None = None) -> bool:
        """
        Paystack's /subscription/disable endpoint needs both the
        subscription code AND its email_token - the token isn't something
        you already have from checkout, it only comes back from a GET on
        the subscription itself. So this is a real two-step flow, not a
        single call - previously stubbed because it needed a live
        subscription to verify the response shape against.
        """
        async with httpx.AsyncClient() as client:
            fetch_resp = await client.get(
                f"{PAYSTACK_BASE_URL}/subscription/{provider_subscription_id}",
                headers={"Authorization": f"Bearer {self.secret_key}"},
                timeout=15,
            )
            if fetch_resp.status_code != 200:
                self.logger.error(
                    "Could not fetch Paystack subscription %s: HTTP %s",
                    provider_subscription_id, fetch_resp.status_code,
                )
                return False

            fetch_body = fetch_resp.json()
            email_token = fetch_body.get("data", {}).get("email_token")
            if not email_token:
                self.logger.error(
                    "Paystack subscription %s has no email_token in response - cannot disable.",
                    provider_subscription_id,
                )
                return False

            disable_resp = await client.post(
                f"{PAYSTACK_BASE_URL}/subscription/disable",
                headers={"Authorization": f"Bearer {self.secret_key}"},
                json={"code": provider_subscription_id, "token": email_token},
                timeout=15,
            )

        if disable_resp.status_code != 200:
            self.logger.error(
                "Paystack disable failed for %s: HTTP %s - %s",
                provider_subscription_id, disable_resp.status_code, disable_resp.text,
            )
            return False

        self.logger.info("Paystack subscription canceled: %s", provider_subscription_id)
        return True
