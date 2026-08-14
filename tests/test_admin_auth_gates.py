"""Router-level auth gates using FastAPI TestClient + dependency overrides."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.security import verify_api_key


@pytest.fixture
def admin_client(app_with_mocks, mock_auth_admin):
    app = app_with_mocks
    app.state.audit_service = AsyncMock()
    app.state.upload_diagnostics = AsyncMock()
    app.state.upload_diagnostics.trends = AsyncMock(return_value={"total": 0, "successes": 0, "failures": 0})
    app.state.upload_diagnostics.last_n = AsyncMock(return_value=[])
    app.state.device_bindings = AsyncMock()
    app.state.device_bindings.list_all = AsyncMock(return_value=[])
    app.state.device_bindings.list_download_tokens = AsyncMock(return_value=[])
    app.state.trade_limits = AsyncMock()
    app.state.alert_service = AsyncMock()
    app.state.alert_service.send = AsyncMock(return_value={"email": "skipped"})
    app.state.subscription_service.list_all = AsyncMock(return_value=[])
    app.state.device_health.list_all = AsyncMock(return_value=[])
    app.state.signal_history.get_recent = AsyncMock(return_value=[])
    app.state.worker_pool.active_worker_count = MagicMock(return_value=0)
    app.dependency_overrides[verify_api_key] = lambda: mock_auth_admin
    return TestClient(app)


def test_admin_summary_ok(admin_client):
    r = admin_client.get("/api/admin/summary")
    assert r.status_code == 200
    body = r.json()
    assert "devices" in body
    assert "subscriptions" in body


def test_admin_plans_ok(admin_client):
    r = admin_client.get("/api/admin/plans")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert any(p.get("code") == "enterprise" for p in r.json())


def test_account_cannot_hit_admin(app_with_mocks, mock_auth_account):
    app_with_mocks.dependency_overrides[verify_api_key] = lambda: mock_auth_account
    client = TestClient(app_with_mocks)
    r = client.get("/api/admin/summary")
    assert r.status_code == 403
