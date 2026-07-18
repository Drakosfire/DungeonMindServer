"""Foundation health and auth coverage for statblocks_v1."""

from __future__ import annotations

import ast
import importlib
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from statblocks_v1 import CONTRACT_NAME, CONTRACT_VERSION
from statblocks_v1.api.dependencies import INTERNAL_KEY_ENV, INTERNAL_KEY_HEADER
from statblocks_v1.testing import create_test_app

HEALTH_PATH = "/api/internal/dungeonbuddy/v1/statblocks/health"
TEST_INTERNAL_KEY = "test-statblocks-v1-internal-key"
PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "statblocks_v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
MINIMAL_UV_WITH = (
    "--with",
    "pytest>=8.3.5",
    "--with",
    "fastapi>=0.115.4",
    "--with",
    "pydantic==2.7.4",
    "--with",
    "httpx>=0.27.0",
)
HEAVY_DEPENDENCY_MODULES = (
    "openai",
    "firebase_admin",
    "google",
    "fal_client",
    "sentence_transformers",
    "generationengine",
)


def _credential_scrubbed_env() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "DUNGEONBUDDY_INTERNAL_API_KEY",
            "OPENAI_API_KEY",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "FIREBASE_CREDENTIALS",
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
        }
    }


def _minimal_uv_run_prefix() -> list[str]:
    """Project-independent uv invocation (ephemeral env, no root dependency sync)."""
    return [
        "uv",
        "run",
        "--isolated",
        "--no-project",
        *MINIMAL_UV_WITH,
    ]


def _minimal_uv_pytest_prefix() -> list[str]:
    return [*_minimal_uv_run_prefix(), "pytest", "--confcutdir=tests/statblocks_v1"]


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
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == "unauthorized_internal_client"
    assert "Missing" in body["error"]["message"]


def test_health_wrong_header_denied(client: TestClient) -> None:
    response = client.get(
        HEALTH_PATH,
        headers={INTERNAL_KEY_HEADER: "wrong-key"},
    )

    assert response.status_code == 403
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == "unauthorized_internal_client"
    assert "Invalid" in body["error"]["message"]


def test_health_missing_server_env_fails_closed(unconfigured_client: TestClient) -> None:
    response = unconfigured_client.get(
        HEALTH_PATH,
        headers={INTERNAL_KEY_HEADER: TEST_INTERNAL_KEY},
    )

    assert response.status_code == 503
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == "internal_service_misconfigured"


def test_create_test_app_does_not_import_production_app() -> None:
    before = set(sys.modules)
    create_test_app()
    newly_loaded = set(sys.modules) - before
    assert "app" not in newly_loaded


def test_clean_process_never_imports_production_app() -> None:
    """Prove isolation in a fresh interpreter (parent conftest cannot preload ``app``)."""
    script = """
import os
import sys

for key in (
    "DUNGEONBUDDY_INTERNAL_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "FIREBASE_CREDENTIALS",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
):
    os.environ.pop(key, None)

assert "app" not in sys.modules

from fastapi.testclient import TestClient
from statblocks_v1.testing import create_test_app

assert "app" not in sys.modules
app = create_test_app()
assert "app" not in sys.modules

os.environ["DUNGEONBUDDY_INTERNAL_API_KEY"] = "isolation-key"
client = TestClient(app)
response = client.get(
    "/api/internal/dungeonbuddy/v1/statblocks/health",
    headers={"X-DungeonBuddy-Internal-Key": "isolation-key"},
)
assert response.status_code == 200, response.text
assert "app" not in sys.modules
print("ok")
"""
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "DUNGEONBUDDY_INTERNAL_API_KEY",
            "OPENAI_API_KEY",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "FIREBASE_CREDENTIALS",
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
        }
    }
    env["PYTHONPATH"] = str(REPO_ROOT)
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "ok" in completed.stdout


def test_focused_lane_skips_parent_conftest() -> None:
    """Advertised lane must not load ``tests/conftest.py`` (imports production ``app``)."""
    env = _credential_scrubbed_env()
    env["PYTHONPATH"] = str(REPO_ROOT)
    completed = subprocess.run(
        [
            *_minimal_uv_pytest_prefix(),
            "--trace-config",
            "tests/statblocks_v1/test_import_boundaries.py",
            "--collect-only",
            "-q",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, output
    assert "tests/conftest.py" not in output
    assert "tests/statblocks_v1/conftest.py" in output


def test_minimal_lane_excludes_full_server_dependencies() -> None:
    """``uv run --isolated --no-project`` must not install the production dependency graph."""
    probe = (
        "import importlib.util as u\n"
        + "\n".join(
            f"assert u.find_spec({module!r}) is None, {module!r}"
            for module in HEAVY_DEPENDENCY_MODULES
        )
        + "\nprint('ok')\n"
    )
    env = _credential_scrubbed_env()
    completed = subprocess.run(
        [
            *_minimal_uv_run_prefix(),
            "python",
            "-c",
            probe,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "ok" in completed.stdout


def test_inner_layers_do_not_construct_firebase_or_openai() -> None:
    """Static guard: only infrastructure adapters may construct external clients."""
    forbidden_tokens = (
        "OpenAI(",
        "firebase_admin",
        "firestore.firebase_config",
        "StatBlockDetails",
        "statblockgenerator",
    )
    protected_roots = (PACKAGE_ROOT / "domain", PACKAGE_ROOT / "application", PACKAGE_ROOT / "api")
    for root in protected_roots:
        for path in root.rglob("*.py"):
            # Infrastructure owns concrete provider SDK construction.
            source = path.read_text()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    assert node.func.id != "OpenAI", f"{path} constructs OpenAI"
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    assert node.func.attr != "OpenAI", f"{path} constructs OpenAI"
            for token in forbidden_tokens:
                assert token not in source, f"{path} contains forbidden token {token!r}"


def test_openapi_declares_typed_auth_error_responses(client: TestClient) -> None:
    schema = client.app.openapi()
    health = schema["paths"][HEALTH_PATH]["get"]
    assert "401" in health["responses"]
    assert "403" in health["responses"]
    assert "503" in health["responses"]
    components = schema["components"]["schemas"]
    assert "ErrorEnvelopeV1" in components
    assert "ErrorDetailV1" in components
    assert "HealthResponseV1" in components
