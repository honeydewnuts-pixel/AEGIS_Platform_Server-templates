"""
Project : AEGIS
Company : Honeydewnuts Nigerian Limited
File    : payment_providers/flutterwave_adapter.py

Flutterwave webhook verification is a simple equality check: the
'verif-hash' header must match the secret hash string YOU configure
in the Flutterwave dashboard (not an HMAC of the body).
Docs: https://developer.flutterwave.com/docs/integration-guides/webhooks
"""

from __future__ import annotations

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

FLUTTERWAVE_BASE_URL = "https://api.flutterwave.com/v3"

PLAN_AMOUNTS_NGN = {
    "monthly": 5000,   # adjust to your real pricing
}


class FlutterwaveAdapter(PaymentProviderAdapter):
    name = "flutterwave"

    def __init__(self) -> None:
        self.logger = configure_logging(__name__)
        self.secret_key = settings.FLUTTERWAVE_SECRET_KEY
        self.webhook_hash = settings.FLUTTERWAVE_WEBHOOK_HASH

    def verify_webhook_signature(self, raw_body: bytes, headers: dict[str, str]) -> bool:
        received = headers.get("verif-hash", "")
        return hmac.compare_digest(received, self.webhook_hash)

    def parse_webhook_event(self, raw_body: bytes) -> PaymentEvent:
        payload = json.loads(raw_body)
        event = payload.get("event", "")
        data = payload.get("data", {})
        meta = data.get("meta", {}) or {}
        status = (data.get("status") or "").lower()

        if event.startswith("charge.") and status == "successful":
            event_type = PaymentEventType.PAYMENT_SUCCEEDED
        elif event.startswith("charge.") and status in ("failed", "cancelled"):
            event_type = PaymentEventType.PAYMENT_FAILED
        elif "subscription" in event and "cancel" in event:
            event_type = PaymentEventType.SUBSCRIPTION_CANCELED
        else:
            event_type = PaymentEventType.UNKNOWN

        return PaymentEvent(
            provider=self.name,
            provider_event_id=str(data.get("id") or data.get("tx_ref") or uuid.uuid4()),
            event_type=event_type,
            account_id=meta.get("account_id", ""),
            provider_customer_id=(data.get("customer") or {}).get("id"),
            # NOTE: this is the plan code, not Flutterwave's own numeric
            # subscription id - their charge webhook doesn't reliably include
            # that id directly. cancel_subscription() below looks it up via
            # GET /subscriptions using the customer email instead, since
            # that's what's actually available at cancel-time.
            provider_subscription_id=data.get("plan"),
            current_period_end=None,   # Flutterwave doesn't send this in the charge webhook - track via subscription.get if needed
            raw_payload=payload,
        )

    async def create_checkout_session(self, account_id: str, email: str, plan: str, reveal_token: str) -> CheckoutSession:
        tx_ref = f"aegis-{account_id}-{uuid.uuid4().hex[:10]}"
        amount = PLAN_AMOUNTS_NGN.get(plan, PLAN_AMOUNTS_NGN["monthly"])

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{FLUTTERWAVE_BASE_URL}/payments",
                headers={"Authorization": f"Bearer {self.secret_key}"},
                json={
                    "tx_ref": tx_ref,
                    "amount": amount,
                    "currency": "NGN",
                    "redirect_url": f"{settings.PORTAL_BASE_URL}/success.html?account_id={account_id}&reveal_token={reveal_token}",
                    "customer": {"email": email},
                    "meta": {"account_id": account_id, "plan": plan},
                },
                timeout=15,
            )
            resp.raise_for_status()
            body = resp.json()

        return CheckoutSession(
            checkout_url=body["data"]["link"],
            reference=tx_ref,
        )

    async def cancel_subscription(self, provider_subscription_id: str, provider_customer_id: str | None = None) -> bool:
        """
        Flutterwave's charge webhook doesn't hand back a numeric
        subscription id directly - what's stored as provider_subscription_id
        is actually the plan code (see parse_webhook_event above), which
        alone can't identify ONE specific subscriber's subscription if
        multiple subscribers share a plan. provider_customer_id (also
        captured from the webhook) is what actually disambiguates - this
        looks up that customer's subscriptions and cancels the one
        matching the plan code.

        CAVEAT: the exact response shape of GET /v3/subscriptions and
        whether it accepts a customer_id filter directly were not
        verified against a live Flutterwave account (no network access
        in the environment this was written in). If this 404s or returns
        an unexpected shape, check Flutterwave's current API docs for
        the exact query parameter name and response structure, and tell
        me what changed - this is a documented best-effort, not a
        guarantee.
        """
        if provider_customer_id is None:
            self.logger.error(
                "Cannot cancel Flutterwave subscription - no provider_customer_id on record. "
                "This shouldn't happen for any subscription created after this fix; older "
                "records predating it won't have one stored."
            )
            return False

        async with httpx.AsyncClient() as client:
            list_resp = await client.get(
                f"{FLUTTERWAVE_BASE_URL}/subscriptions",
                headers={"Authorization": f"Bearer {self.secret_key}"},
                params={"customer_id": provider_customer_id},
                timeout=15,
            )
            if list_resp.status_code != 200:
                self.logger.error(
                    "Could not list Flutterwave subscriptions for customer %s: HTTP %s",
                    provider_customer_id, list_resp.status_code,
                )
                return False

            subscriptions = list_resp.json().get("data", [])
            match = next((s for s in subscriptions if s.get("plan") == provider_subscription_id), None)
            if match is None:
                self.logger.error(
                    "No matching Flutterwave subscription found for customer %s, plan %s",
                    provider_customer_id, provider_subscription_id,
                )
                return False

            cancel_resp = await client.put(
                f"{FLUTTERWAVE_BASE_URL}/subscriptions/{match['id']}/cancel",
                headers={"Authorization": f"Bearer {self.secret_key}"},
                timeout=15,
            )

        if cancel_resp.status_code != 200:
            self.logger.error(
                "Flutterwave cancel failed for subscription %s: HTTP %s - %s",
                match["id"], cancel_resp.status_code, cancel_resp.text,
            )
            return False

        self.logger.info("Flutterwave subscription canceled: %s (customer %s)", match["id"], provider_customer_id)
        return True
