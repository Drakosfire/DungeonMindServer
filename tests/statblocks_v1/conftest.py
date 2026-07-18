"""Focused fixtures for the statblocks_v1 bounded context.

These tests intentionally do not import the production ``app`` module.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from routers.internal_auth import INTERNAL_KEY_ENV, INTERNAL_KEY_HEADER
from statblocks_v1.testing import create_test_app

TEST_INTERNAL_KEY = "test-statblocks-v1-internal-key"


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {INTERNAL_KEY_HEADER: TEST_INTERNAL_KEY}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv(INTERNAL_KEY_ENV, TEST_INTERNAL_KEY)
    return TestClient(create_test_app())


@pytest.fixture
def unconfigured_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv(INTERNAL_KEY_ENV, raising=False)
    return TestClient(create_test_app())
