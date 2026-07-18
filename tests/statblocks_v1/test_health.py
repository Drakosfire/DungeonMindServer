"""Foundation health and auth coverage for statblocks_v1."""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from routers.internal_auth import INTERNAL_KEY_ENV, INTERNAL_KEY_HEADER
from statblocks_v1 import CONTRACT_NAME, CONTRACT_VERSION
from statblocks_v1.testing import create_test_app

HEALTH_PATH = "/api/internal/dungeonbuddy/v1/statblocks/health"
TEST_INTERNAL_KEY = "test-statblocks-v1-internal-key"
PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "statblocks_v1"


def test_domain_package_imports_without_external_env(monkeypatch) -> None:
    monkeypatch.delenv(INTERNAL_KEY_ENV, raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    for name in list(sys.modules):
        if name == "statblocks_v1" or name.startswith("statblocks_v1."):
            del sys.modules[name]

    domain_errors = importlib.import_module("statblocks_v1.domain.errors")
    domain_protocols = importlib.import_module("statblocks_v1.domain.protocols")

    assert domain_errors.UnauthorizedInternalClientError().code == "unauthorized_internal_client"
    assert domain_protocols.Clock is not None


def test_health_returns_foundation_contract(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get(HEALTH_PATH, headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {
        "status": "foundation",
        "contract": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "capabilities": [],
    }


def test_health_missing_header_denied(client: TestClient) -> None:
    response = client.get(HEALTH_PATH)

    assert response.status_code == 401
    body = response.json()["detail"]["error"]
    assert body["code"] == "unauthorized_internal_client"
    assert "Missing" in body["message"]


def test_health_wrong_header_denied(client: TestClient) -> None:
    response = client.get(
        HEALTH_PATH,
        headers={INTERNAL_KEY_HEADER: "wrong-key"},
    )

    assert response.status_code == 403
    body = response.json()["detail"]["error"]
    assert body["code"] == "unauthorized_internal_client"
    assert "Invalid" in body["message"]


def test_health_missing_server_env_fails_closed(unconfigured_client: TestClient) -> None:
    response = unconfigured_client.get(
        HEALTH_PATH,
        headers={INTERNAL_KEY_HEADER: TEST_INTERNAL_KEY},
    )

    assert response.status_code == 500
    body = response.json()["detail"]["error"]
    assert body["code"] == "internal_service_misconfigured"


def test_create_test_app_does_not_import_production_app() -> None:
    before = set(sys.modules)
    create_test_app()
    newly_loaded = set(sys.modules) - before
    assert "app" not in newly_loaded


def test_package_source_does_not_construct_firebase_or_openai() -> None:
    """Static guard: foundation code never constructs Firebase/OpenAI clients."""
    forbidden_tokens = (
        "OpenAI(",
        "firebase_admin",
        "firestore.firebase_config",
        "StatBlockDetails",
        "statblockgenerator",
    )
    for path in PACKAGE_ROOT.rglob("*.py"):
        # api/dependencies may import routers.internal_auth only.
        source = path.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "OpenAI", f"{path} constructs OpenAI"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr != "OpenAI", f"{path} constructs OpenAI"
        for token in forbidden_tokens:
            assert token not in source, f"{path} contains forbidden token {token!r}"
