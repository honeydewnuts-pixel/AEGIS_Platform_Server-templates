"""
Shared fixtures for router-level tests. Uses FastAPI's dependency_overrides
mechanism to replace verify_api_key with a controllable fake AuthContext,
and mocks app.state services directly - this lets router tests verify
request/response handling and authorization logic without needing a real
Postgres/Redis/MT5 worker running. (test_e2e_*.py tests, by contrast,
deliberately DO use real Postgres/Redis - see that file's docstring for
why both kinds of test exist.)
"""

import os
import base64
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("AEGIS_MASTER_KEY", base64.b64encode(os.urandom(32)).decode())
os.environ.setdefault("ADMIN_BOOTSTRAP_KEY", "test-admin-key")

from app.security import AuthContext, verify_api_key  # noqa: E402


@pytest.fixture
def mock_auth_account():
    """Simulates a request authenticated as a regular subscriber, account 'acc1'."""
    return AuthContext(account_id="acc1", is_admin=False, label="test key")


@pytest.fixture
def mock_auth_admin():
    """Simulates a request authenticated with an admin key."""
    return AuthContext(account_id=None, is_admin=True, label="test admin key")


@pytest.fixture
def app_with_mocks():
    """
    Returns the real FastAPI app with every app.state service replaced by
    an AsyncMock/MagicMock, so router logic (auth checks, status codes,
    response shapes) can be tested in isolation from real infrastructure.
    Import is deferred to inside the fixture so the env vars above are
    set before app.main (and therefore app.config) is ever imported.
    """
    from app.main import app

    app.state.job_queue = AsyncMock()
    app.state.worker_pool = AsyncMock()
    app.state.vault = AsyncMock()
    app.state.subscription_service = AsyncMock()
    app.state.device_health = AsyncMock()
    app.state.credential_reveal = AsyncMock()
    app.state.signal_history = AsyncMock()
    app.state.brain_cv_service = MagicMock()
    app.state.indicator_history = AsyncMock()

    yield app

    app.dependency_overrides.clear()


@pytest.fixture
def client_as_account(app_with_mocks, mock_auth_account):
    app_with_mocks.dependency_overrides[verify_api_key] = lambda: mock_auth_account
    return TestClient(app_with_mocks)


@pytest.fixture
def client_as_admin(app_with_mocks, mock_auth_admin):
    app_with_mocks.dependency_overrides[verify_api_key] = lambda: mock_auth_admin
    return TestClient(app_with_mocks)
