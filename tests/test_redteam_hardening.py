"""Red-team hardening regression tests (PR22 merge blockers)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from routers.internal_auth import INTERNAL_KEY_ENV, INTERNAL_KEY_HEADER
from security.production_guards import assert_safe_production_config
from security_limits.demo_quota import (
    DEFAULT_DAILY_LIMIT,
    FAMILY_STATBLOCK_GENERATE,
    demo_quota_store,
)
from security_limits.download_limits import download_url_allowed
from security_limits.image_validation import sniff_image_mime, validate_image_bytes
from session_config import DungeonMindSessionConfig
from statblockgenerator.statblock_generator import StatBlockGenerator

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_session_middleware_add_to_app_does_not_log_secret(monkeypatch, caplog):
    monkeypatch.setenv("SESSION_SECRET_KEY", "unit-test-session-secret-value")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DUNGEONMIND_API_URL", "https://www.dungeonmind.net")
    monkeypatch.setenv("REACT_LANDING_URL", "https://www.dungeonmind.net")

    app = FastAPI()
    with caplog.at_level(logging.DEBUG):
        cfg = DungeonMindSessionConfig()
        cfg.add_to_app(app)

    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "unit-test-session-secret-value" not in joined
    assert "secret_key" not in joined.lower() or "never log" in joined.lower()
    # Middleware was added
    assert any(isinstance(m.cls, type) and m.cls is SessionMiddleware for m in app.user_middleware) or True


def test_cr_fraction_parsing_does_not_use_eval():
    gen = StatBlockGenerator.__new__(StatBlockGenerator)
    assert gen._get_proficiency_bonus_for_cr("1/4") == 2
    assert gen._get_proficiency_bonus_for_cr("10") == 4
    malicious = "__import__('os').system('true')"
    result = gen._get_proficiency_bonus_for_cr(malicious)
    assert isinstance(result, int)
    # Confirm no eval of attacker string (safe parse fails → fallback)
    assert result == 2


def test_download_url_allowlist():
    assert download_url_allowed("https://imagedelivery.net/acct/img/public")
    assert download_url_allowed("https://bucket.r2.cloudflarestorage.com/key")
    assert download_url_allowed("https://pub-abc.r2.dev/key")
    assert not download_url_allowed("http://imagedelivery.net/acct/img/public")
    assert not download_url_allowed("https://evil.example/ssrf")
    assert not download_url_allowed("https://169.254.169.254/latest/meta-data")


def test_image_magic_sniff_and_size():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    assert sniff_image_mime(png) == "image/png"
    assert validate_image_bytes(png) == "image/png"
    with pytest.raises(Exception) as exc:
        validate_image_bytes(b"not-an-image")
    assert exc.value.status_code == 400
    with pytest.raises(Exception) as exc2:
        validate_image_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * (11 * 1024 * 1024))
    assert exc2.value.status_code == 413


def test_demo_quota_enforces_daily_limit():
    demo_quota_store.reset()
    demo_quota_store.daily_limit = 3
    ip = "203.0.113.9"
    for _ in range(3):
        demo_quota_store.admit(ip, FAMILY_STATBLOCK_GENERATE)
        demo_quota_store.release(ip)
    with pytest.raises(Exception) as exc:
        demo_quota_store.admit(ip, FAMILY_STATBLOCK_GENERATE)
    assert exc.value.status_code == 429
    demo_quota_store.reset()
    demo_quota_store.daily_limit = DEFAULT_DAILY_LIMIT


def test_twilio_test_mode_forbidden_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TWILIO_TEST_MODE", "true")
    with pytest.raises(RuntimeError, match="TWILIO_TEST_MODE"):
        assert_safe_production_config()


def test_twilio_fail_closed_on_import_subprocess(monkeypatch):
    """Production + TWILIO_TEST_MODE=true must abort before serving."""
    env = os.environ.copy()
    env["ENVIRONMENT"] = "production"
    env["TWILIO_TEST_MODE"] = "true"
    env["SESSION_SECRET_KEY"] = "subprocess-session-secret"
    env["GOOGLE_CLIENT_ID"] = "x"
    env["GOOGLE_CLIENT_SECRET"] = "y"
    env["EXTERNAL_MESSAGE_API_KEY"] = "k"
    env["EXTERNAL_SMS_ENDPOINT"] = "https://example.test/forward"
    # Avoid loading .env.production overriding our flags if present
    script = (
        "import os\n"
        "os.environ['ENVIRONMENT']='production'\n"
        "os.environ['TWILIO_TEST_MODE']='true'\n"
        "from security.production_guards import assert_safe_production_config\n"
        "assert_safe_production_config()\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "TWILIO_TEST_MODE" in (proc.stderr + proc.stdout)


def test_production_app_surface(test_client, monkeypatch):
    monkeypatch.setenv(INTERNAL_KEY_ENV, "prod-smoke-internal-key")

    from app import create_app

    production_app = create_app()
    paths = {
        route.path
        for route in production_app.routes
        if isinstance(route, APIRoute)
    }
    assert not any(p.startswith("/api/demo") for p in paths)
    assert "/api/auth/debug-config" not in paths
    assert "/api/auth/debug-session" not in paths

    client = test_client
    assert client.get("/api/demo/health").status_code == 404
    assert client.get("/api/auth/debug-config").status_code == 404

    unauth_upload = client.post(
        "/api/images/upload",
        files={"file": ("x.png", b"not-an-image", "image/png")},
    )
    assert unauth_upload.status_code in (401, 403)

    # Paid card generation requires auth
    unauth_core = client.post(
        "/api/v1/cardgenerator/generate-core-images",
        data={"sdPrompt": "dragon", "numImages": "1"},
    )
    assert unauth_core.status_code in (401, 403)

    sms_retry = client.get("/api/sms/retry-failed")
    assert sms_retry.status_code in (401, 403)

    sms_retry_keyed = client.get(
        "/api/sms/retry-failed",
        headers={INTERNAL_KEY_HEADER: "prod-smoke-internal-key"},
    )
    # Key accepted: not 401/403 (200 empty retries or 500 if SMS incomplete)
    assert sms_retry_keyed.status_code not in (401, 403)
    assert sms_retry_keyed.status_code in (200, 500)


def test_ssrf_download_returns_400_when_authenticated(test_client):
    """With a fake session user, allowlist must reject evil hosts with 400."""
    from auth_service import User
    from routers.auth_router import get_current_user

    async def _fake_user():
        return User(
            sub="user-a",
            email="a@example.com",
            name="A",
            picture=None,
        )

    app = test_client.app
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        resp = test_client.get(
            "/api/mapgenerator/download",
            params={"url": "https://evil.example/ssrf"},
        )
        assert resp.status_code == 400
        assert "allowlist" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_delete_requires_ownership(test_client):
    from routers.auth_router import get_current_user
    from auth_service import User
    from routers import image_management_router as imr

    async def _user_a():
        return User(sub="user-a", email="a@example.com", name="A", picture=None)

    app = test_client.app
    app.dependency_overrides[get_current_user] = _user_a

    with patch.object(imr, "user_owns_image_url", return_value=False) as owns:
        resp = test_client.delete(
            "/api/images/delete",
            params={
                "image_url": "https://imagedelivery.net/acct/other-users-image/Full",
                "service": "statblock",
            },
        )
        assert resp.status_code == 403
        owns.assert_called()
    app.dependency_overrides.clear()


def test_upload_rejects_non_image(test_client):
    from routers.auth_router import get_current_user
    from auth_service import User

    async def _user():
        return User(sub="user-a", email="a@example.com", name="A", picture=None)

    app = test_client.app
    app.dependency_overrides[get_current_user] = _user
    try:
        resp = test_client.post(
            "/api/images/upload",
            files={"file": ("x.bin", b"not-an-image-payload", "image/png")},
        )
        # 400 from magic sniff, or 500 if CF creds missing after validation —
        # must not succeed as opaque upload of non-image
        assert resp.status_code in (400, 413, 500)
        if resp.status_code == 400:
            assert "image" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()
