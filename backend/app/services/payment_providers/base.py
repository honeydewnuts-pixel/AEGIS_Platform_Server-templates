"""
====================================================================
Project : AEGIS
Company : Honeydewnuts Nigerian Limited

File    : payment_providers/base.py

Purpose
-------
Common interface for payment providers, mirroring the existing
BrokerAdapter pattern (broker_adapter_interface.py). Each provider
(Paystack, Flutterwave, Stripe) implements this so SubscriptionService
and the webhook router don't need provider-specific branching.

CAVEAT: The checkout-session-creation HTTP calls in each adapter are
built from documented API shapes, but this sandbox has no internet
access to test them against live provider APIs. Treat them the same
way as the MT5 .tpl file - verify against a real sandbox/test API key
before going live, and tell me the exact error if something doesn't
match what the provider actually expects.
====================================================================
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class PaymentEventType(str, Enum):
    PAYMENT_SUCCEEDED = "PAYMENT_SUCCEEDED"          # subscription activated/renewed
    PAYMENT_FAILED = "PAYMENT_FAILED"                # renewal attempt failed
    SUBSCRIPTION_CANCELED = "SUBSCRIPTION_CANCELED"  # canceled by user or provider
    UNKNOWN = "UNKNOWN"                              # event type we don't act on


@dataclass
class PaymentEvent:
    """Normalized shape every provider's webhook gets translated into."""
    provider: str
    provider_event_id: str          # for idempotency - each provider gives a unique event/tx id
    event_type: PaymentEventType
    account_id: str                 # your internal identifier (passed as metadata/reference at checkout)
    provider_customer_id: str | None
    provider_subscription_id: str | None
    current_period_end: datetime | None
    raw_payload: dict


@dataclass
class CheckoutSession:
    checkout_url: str
    reference: str                  # provider's transaction/session reference


class PaymentProviderAdapter(ABC):

    name: str

    @abstractmethod
    def verify_webhook_signature(self, raw_body: bytes, headers: dict[str, str]) -> bool:
        """Return True only if the webhook is authentically from this provider."""
        raise NotImplementedError

    @abstractmethod
    def parse_webhook_event(self, raw_body: bytes) -> PaymentEvent:
        """Convert the provider's raw webhook payload into a PaymentEvent."""
        raise NotImplementedError

    @abstractmethod
    async def create_checkout_session(self, account_id: str, email: str, plan: str, reveal_token: str) -> CheckoutSession:
        raise NotImplementedError

    @abstractmethod
    async def cancel_subscription(self, provider_subscription_id: str, provider_customer_id: str | None = None) -> bool:
        raise NotImplementedError
