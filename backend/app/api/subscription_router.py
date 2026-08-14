"""
Project : AEGIS
Company : Honeydewnuts Nigerian Limited
File    : subscription_router.py
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from app.security import verify_api_key, require_account_match, require_admin, AuthContext
from app.core.rate_limit import limiter
from app.services.payment_providers.paystack_adapter import PaystackAdapter
from app.services.payment_providers.flutterwave_adapter import FlutterwaveAdapter
from app.services.payment_providers.stripe_adapter import StripeAdapter

router = APIRouter(prefix="/api/subscriptions", tags=["Subscriptions"])

ADAPTERS = {
    "paystack": PaystackAdapter,
    "flutterwave": FlutterwaveAdapter,
    "stripe": StripeAdapter,
}


class CheckoutRequest(BaseModel):
    account_id: str
    email: EmailStr
    plan: str = "monthly"


def get_subscription_service(request: Request):
    return request.app.state.subscription_service


def get_credential_reveal_service(request: Request):
    return request.app.state.credential_reveal


@router.post("/checkout/{provider}")
@limiter.limit("5/minute")
async def create_checkout(
    provider: str,
    checkout_request: CheckoutRequest,
    request: Request,  # required by @limiter.limit - slowapi inspects this for the client IP
    credential_reveal=Depends(get_credential_reveal_service),
):
    """
    Deliberately NOT behind verify_api_key: a brand-new subscriber has no
    AEGIS API key yet (keys are issued on first successful activation -
    see SubscriptionService.apply_event), so there's nothing to check them
    against at this point in the flow. This just creates a payment
    provider checkout session/URL - no AEGIS account data is exposed by
    letting an anonymous caller do that.

    Rate-limited (5/minute per IP) since it's the one endpoint in this
    API with no auth at all - see app/core/rate_limit.py for the shared
    Limiter instance.
    """
    adapter_cls = ADAPTERS.get(provider)
    if adapter_cls is None:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    # This reveal_token is how the subscriber's browser will claim their
    # portal_token + mobile API key after payment completes - see
    # CredentialRevealService and client_portal/signup.html.
    reveal_token = await credential_reveal.create_reveal_token(checkout_request.account_id)

    adapter = adapter_cls()
    session = await adapter.create_checkout_session(
        checkout_request.account_id, checkout_request.email, checkout_request.plan, reveal_token
    )
    return {"checkout_url": session.checkout_url, "reference": session.reference}


@router.post("/webhook/{provider}")
async def receive_webhook(provider: str, request: Request):
    """
    No verify_api_key here either - these are called by the payment
    provider, not your clients. Authenticity is established by the
    provider-specific signature check instead (see each adapter's
    verify_webhook_signature).
    """
    adapter_cls = ADAPTERS.get(provider)
    if adapter_cls is None:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    adapter = adapter_cls()
    raw_body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    if not adapter.verify_webhook_signature(raw_body, headers):
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")

    event = adapter.parse_webhook_event(raw_body)

    subscription_service = request.app.state.subscription_service
    if await subscription_service.already_processed(event.provider, event.provider_event_id):
        return {"status": "already_processed"}

    newly_issued = await subscription_service.apply_event(event)

    if newly_issued is not None:
        # First activation - stage the new credentials so the subscriber's
        # browser can claim them via GET /reveal once it's redirected back
        # from the payment provider (see checkout's reveal_token above).
        credential_reveal = request.app.state.credential_reveal
        await credential_reveal.stash_credentials(
            newly_issued["account_id"], newly_issued["portal_token"], newly_issued["mobile_api_key"]
        )

    # If payment failed or subscription was canceled, immediately try to
    # disconnect any live MT5 worker rather than waiting for the next
    # background sweep cycle.
    if event.account_id and event.event_type.name in ("PAYMENT_FAILED", "SUBSCRIPTION_CANCELED"):
        worker_pool = request.app.state.worker_pool
        if await worker_pool.is_running(event.account_id) and not await subscription_service.is_active(event.account_id):
            await worker_pool.stop_worker(event.account_id)

    return {"status": "processed"}


@router.get("/reveal")
async def reveal_credentials(
    account_id: str,
    reveal_token: str,
    credential_reveal=Depends(get_credential_reveal_service),
):
    """
    One-time claim of a brand-new subscriber's portal_token + mobile API
    key, using the reveal_token embedded in the payment provider's
    success redirect URL (see create_checkout above). Returns 404 if the
    token is wrong, already used, expired, or the webhook hasn't arrived
    yet - client_portal/success.html retries a few times to cover that
    last case, since webhooks can take a few seconds.
    """
    result = await credential_reveal.reveal(account_id, reveal_token)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Not ready yet, or already claimed. If you just paid, wait a few seconds and retry.",
        )
    return result


@router.get("/status/{account_id}")
async def get_subscription_status(
    account_id: str,
    subscription_service=Depends(get_subscription_service),
    auth: AuthContext = Depends(verify_api_key),
):
    require_account_match(auth, account_id)
    record = await subscription_service.get_status(account_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No subscription found for this account.")
    record["is_active"] = await subscription_service.is_active(account_id)
    return record


@router.get("")
async def list_subscriptions(
    subscription_service=Depends(get_subscription_service),
    auth: AuthContext = Depends(verify_api_key),
):
    """Admin-facing: every subscription, for the admin dashboard."""
    require_admin(auth)
    return await subscription_service.list_all()


@router.post("/{account_id}/cancel")
async def cancel_subscription(
    account_id: str,
    request: Request,
    subscription_service=Depends(get_subscription_service),
    auth: AuthContext = Depends(verify_api_key),
):
    """
    Admin-only for now - previously cancel_subscription() existed on every
    payment adapter but nothing anywhere actually called it, so there was
    no way to cancel a subscription at all. Subscriber self-service
    cancellation (from client_portal) is a reasonable next step but
    deliberately not added here yet, since "can a subscriber cancel their
    own subscription" has billing/refund policy implications worth a
    deliberate decision, not a default.
    """
    require_admin(auth)

    record = await subscription_service.get_status(account_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No subscription found for this account.")

    adapter_cls = ADAPTERS.get(record.get("provider"))
    if adapter_cls is None:
        raise HTTPException(status_code=400, detail=f"Unknown or missing provider on this subscription record: {record.get('provider')}")

    adapter = adapter_cls()
    success = await adapter.cancel_subscription(
        record["provider_subscription_id"], record.get("provider_customer_id")
    )
    if not success:
        raise HTTPException(status_code=502, detail="Payment provider did not confirm cancellation - check server logs for the specific reason.")

    await subscription_service.mark_canceled(account_id)  # local status update; the provider's own webhook will also arrive and confirm independently

    worker_pool = request.app.state.worker_pool
    if await worker_pool.is_running(account_id):
        await worker_pool.stop_worker(account_id)

    return {"status": "canceled", "account_id": account_id}


import uuid


class DemoSignupRequest(BaseModel):
    account_id: str | None = Field(default=None, description="Optional; auto-generated if omitted")


@router.post("/demo/signup")
async def demo_signup(body: DemoSignupRequest, request: Request):
    """
    Public endpoint: create a 14-day demo plan (brain + chart analysis).
    Live market orders remain blocked until a paid subscription is active.
    Returns account_id, portal_token, mobile_api_key, and a one-time APK download URL.
    """
    account_id = (body.account_id or "").strip() or f"DEMO-{uuid.uuid4().hex[:10].upper()}"
    sub = request.app.state.subscription_service
    issued = await sub.activate_demo(account_id)
    token = await request.app.state.device_bindings.issue_download_token(
        account_id=account_id, plan="demo", max_uses=1, ttl_hours=72
    )
    base = str(request.base_url).rstrip("/")
    if hasattr(request.app.state, "audit_service"):
        await request.app.state.audit_service.record(
            action="subscription.demo_signup",
            actor_type="system",
            account_id=account_id,
            detail="demo plan activated",
            ip=request.client.host if request.client else None,
        )
    return {
        **issued,
        "download_url": f"{base}/api/download/apk?token={token}",
        "download_token": token,
        "limits": {
            "brain_analysis": True,
            "live_trading": False,
            "device_binding": True,
            "demo_days": 14,
        },
    }
