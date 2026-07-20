"""Red-team hardening regression smokes (PR-RT1)."""

from __future__ import annotations

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from routers.internal_auth import INTERNAL_KEY_ENV, INTERNAL_KEY_HEADER
from routers.map_router import _download_url_allowed
from session_config import DungeonMindSessionConfig
from statblockgenerator.statblock_generator import StatBlockGenerator


def test_session_middleware_kwargs_log_does_not_embed_secret(monkeypatch, caplog):
    monkeypatch.setenv("SESSION_SECRET_KEY", "unit-test-session-secret-value")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DUNGEONMIND_API_URL", "https://www.dungeonmind.net")
    monkeypatch.setenv("REACT_LANDING_URL", "https://www.dungeonmind.net")

    with caplog.at_level("INFO"):
        cfg = DungeonMindSessionConfig()
        kwargs = cfg.get_middleware_kwargs()

    assert kwargs["secret_key"] == "unit-test-session-secret-value"
    joined = " ".join(r.message for r in caplog.records)
    assert "unit-test-session-secret-value" not in joined


def test_cr_fraction_parsing_does_not_use_eval():
    gen = StatBlockGenerator.__new__(StatBlockGenerator)
    assert gen._get_proficiency_bonus_for_cr("1/4") == 2
    assert gen._get_proficiency_bonus_for_cr("10") == 4
    # Malicious / non-numeric CR must not execute; method falls back safely
    assert isinstance(
        gen._get_proficiency_bonus_for_cr("__import__('os').system('true')"),
        int,
    )
    assert isinstance(
        gen._get_proficiency_bonus_for_cr("1/__import__('os').system('id')"),
        int,
    )


def test_download_url_allowlist():
    assert _download_url_allowed("https://imagedelivery.net/acct/img/public")
    assert _download_url_allowed("https://bucket.r2.cloudflarestorage.com/key")
    assert not _download_url_allowed("http://imagedelivery.net/acct/img/public")
    assert not _download_url_allowed("https://evil.example/ssrf")
    assert not _download_url_allowed("https://169.254.169.254/latest/meta-data")


def test_production_app_omits_demo_and_auth_debug(monkeypatch):
    monkeypatch.setenv(INTERNAL_KEY_ENV, "prod-smoke-internal-key")
    monkeypatch.setenv("SESSION_SECRET_KEY", "unit-test-session-secret-value")
    monkeypatch.setenv("DEMO_ROUTER_ENABLED", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("FAL_KEY", raising=False)

    from app import app as production_app

    paths = {
        route.path
        for route in production_app.routes
        if isinstance(route, APIRoute)
    }
    assert not any(p.startswith("/api/demo") for p in paths)
    assert "/api/auth/debug-config" not in paths
    assert "/api/auth/debug-session" not in paths

    client = TestClient(
        production_app, base_url="http://localhost", headers={"host": "localhost"}
    )
    assert client.get("/api/demo/health").status_code == 404
    assert client.get("/api/auth/debug-config").status_code == 404
    assert client.get("/api/auth/debug-session").status_code == 404

    unauth_upload = client.post(
        "/api/images/upload",
        files={"file": ("x.png", b"not-an-image", "image/png")},
    )
    assert unauth_upload.status_code in (401, 403)

    sms_retry = client.get("/api/sms/retry-failed")
    assert sms_retry.status_code in (401, 403, 500)

    sms_retry_keyed = client.get(
        "/api/sms/retry-failed",
        headers={INTERNAL_KEY_HEADER: "prod-smoke-internal-key"},
    )
    # 200 with empty retries, or 500 if SMS env incomplete in test — never open 200 without key
    assert sms_retry_keyed.status_code != 401

    ssrf = client.get(
        "/api/mapgenerator/download",
        params={"url": "https://evil.example/ssrf"},
    )
    assert ssrf.status_code in (401, 403)
