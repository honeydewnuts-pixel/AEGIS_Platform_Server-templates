"""
Tests for payment provider webhook signature verification. This is the
one piece of each adapter that's fully testable offline (it's pure crypto/
comparison logic, no network call needed) and it's also the piece where a
bug means either rejecting real webhooks or - worse - accepting forged ones.
"""

import hashlib
import hmac
import json
from unittest.mock import patch

import pytest

from app.services.payment_providers.paystack_adapter import PaystackAdapter
from app.services.payment_providers.flutterwave_adapter import FlutterwaveAdapter


@pytest.fixture
def paystack_adapter():
    with patch("app.services.payment_providers.paystack_adapter.settings") as mock_settings:
        mock_settings.PAYSTACK_SECRET_KEY = "sk_test_12345"
        yield PaystackAdapter()


class TestPaystackSignature:

    def test_valid_signature_accepted(self, paystack_adapter):
        body = json.dumps({"event": "charge.success", "data": {"id": 1}}).encode()
        valid_sig = hmac.new(b"sk_test_12345", body, hashlib.sha512).hexdigest()
        assert paystack_adapter.verify_webhook_signature(body, {"x-paystack-signature": valid_sig}) is True

    def test_invalid_signature_rejected(self, paystack_adapter):
        body = json.dumps({"event": "charge.success", "data": {"id": 1}}).encode()
        assert paystack_adapter.verify_webhook_signature(body, {"x-paystack-signature": "wrong"}) is False

    def test_missing_signature_header_rejected(self, paystack_adapter):
        body = json.dumps({"event": "charge.success"}).encode()
        assert paystack_adapter.verify_webhook_signature(body, {}) is False

    def test_tampered_body_rejected(self, paystack_adapter):
        original_body = json.dumps({"event": "charge.success", "data": {"amount": 5000}}).encode()
        valid_sig = hmac.new(b"sk_test_12345", original_body, hashlib.sha512).hexdigest()
        tampered_body = json.dumps({"event": "charge.success", "data": {"amount": 999999}}).encode()
        # Signature was computed over the ORIGINAL body - must not validate against tampered data.
        assert paystack_adapter.verify_webhook_signature(tampered_body, {"x-paystack-signature": valid_sig}) is False

    def test_parse_webhook_event_extracts_account_id_from_metadata(self, paystack_adapter):
        body = json.dumps({
            "event": "charge.success",
            "data": {
                "id": 123,
                "reference": "aegis-acc1-abc123",
                "metadata": {"account_id": "acc1"},
                "customer": {"customer_code": "CUS_xyz"},
            },
        }).encode()
        event = paystack_adapter.parse_webhook_event(body)
        assert event.account_id == "acc1"
        assert event.provider == "paystack"
        assert event.provider_customer_id == "CUS_xyz"


@pytest.fixture
def flutterwave_adapter():
    with patch("app.services.payment_providers.flutterwave_adapter.settings") as mock_settings:
        mock_settings.FLUTTERWAVE_SECRET_KEY = "FLWSECK_test"
        mock_settings.FLUTTERWAVE_WEBHOOK_HASH = "my-configured-hash"
        yield FlutterwaveAdapter()


class TestFlutterwaveSignature:

    def test_valid_hash_accepted(self, flutterwave_adapter):
        body = b'{"event": "charge.completed"}'
        assert flutterwave_adapter.verify_webhook_signature(body, {"verif-hash": "my-configured-hash"}) is True

    def test_invalid_hash_rejected(self, flutterwave_adapter):
        body = b'{"event": "charge.completed"}'
        assert flutterwave_adapter.verify_webhook_signature(body, {"verif-hash": "wrong-hash"}) is False

    def test_missing_hash_rejected(self, flutterwave_adapter):
        body = b'{"event": "charge.completed"}'
        assert flutterwave_adapter.verify_webhook_signature(body, {}) is False

    def test_parse_successful_charge(self, flutterwave_adapter):
        body = json.dumps({
            "event": "charge.completed",
            "data": {"id": 99, "status": "successful", "meta": {"account_id": "acc2"}},
        }).encode()
        event = flutterwave_adapter.parse_webhook_event(body)
        assert event.account_id == "acc2"
        assert event.event_type.name == "PAYMENT_SUCCEEDED"
