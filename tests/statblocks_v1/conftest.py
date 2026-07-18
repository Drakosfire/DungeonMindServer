"""Focused fixtures for the statblocks_v1 bounded context.

These tests intentionally do not import the production ``app`` module.

Run with the project-independent lane (no full-server dependency sync)::

    ./scripts/run_statblocks_v1_tests.sh

Or::

    PYTHONPATH=. uv run --isolated --no-project \\
      --with 'pytest>=8.3.5' --with 'fastapi>=0.115.4' \\
      --with 'pydantic>=2.0' --with 'httpx>=0.27.0' \\
      pytest --confcutdir=tests/statblocks_v1 tests/statblocks_v1 -q

``--confcutdir`` prevents loading ``tests/conftest.py``, which imports the
full production app at collection time. ``--isolated --no-project`` prevents
``uv`` from using the project ``.venv`` or synchronizing OpenAI, Firebase,
sentence-transformers, generationengine, etc.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from statblocks_v1.api.dependencies import INTERNAL_KEY_ENV, INTERNAL_KEY_HEADER
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
