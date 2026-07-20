"""Red-team hardening regression tests (PR22 round-2 merge blockers)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.routing import APIRoute
from starlette.middleware.sessions import SessionMiddleware
from starlette.testclient import TestClient

# Import constants — routers.internal_auth is a submodule; import path still
# runs routers/__init__.py. FIREBASE_SKIP_INIT + conftest stub keep CI green.
from routers.internal_auth import INTERNAL_KEY_ENV, INTERNAL_KEY_HEADER
from security.production_guards import assert_safe_production_config
from security_limits.demo_quota import (
    DEFAULT_DAILY_LIMIT,
    FAMILY_STATBLOCK_GENERATE,
    FAMILY_CARD_GENERATE_ITEM,
    client_ip,
    demo_quota_store,
)
from security_limits.download_limits import download_url_allowed
from security_limits.image_bounds import open_image_bounded, MAX_IMAGE_PIXELS
from security_limits.image_validation import sniff_image_mime, validate_image_bytes
from security_limits.input_limits import clamp_num_images, MAX_IMAGES_PER_REQUEST
from security_limits.paid_budget import paid_budget_store
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
    assert any(m.cls is SessionMiddleware for m in app.user_middleware)


def test_cr_fraction_parsing_does_not_use_eval():
    gen = StatBlockGenerator.__new__(StatBlockGenerator)
    assert gen._get_proficiency_bonus_for_cr("1/4") == 2
    assert isinstance(gen._get_proficiency_bonus_for_cr("__import__('os').system('true')"), int)


def test_download_url_allowlist():
    assert download_url_allowed("https://imagedelivery.net/acct/img/public")
    assert not download_url_allowed("https://evil.example/ssrf")


def test_image_magic_rejects_non_image_at_boundary():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    assert sniff_image_mime(png) == "image/png"
    with pytest.raises(Exception) as exc:
        validate_image_bytes(b"not-an-image")
    assert exc.value.status_code == 400


def test_client_ip_ignores_spoofed_x_forwarded_for(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY", "true")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": "/",
        "raw_path": b"/",
        "root_path": "",
        "scheme": "http",
        "query_string": b"",
        "headers": [
            (b"x-forwarded-for", b"1.2.3.4, 10.0.0.1"),
            (b"x-real-ip", b"203.0.113.50"),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
    }
    req = Request(scope)
    assert client_ip(req) == "203.0.113.50"

    monkeypatch.setenv("TRUST_PROXY", "false")
    assert client_ip(req) == "127.0.0.1"


def test_demo_quota_is_global_across_families_and_xff_does_not_reset():
    demo_quota_store.reset()
    demo_quota_store.daily_limit = 3
    identity = "ip:203.0.113.9"
    demo_quota_store.admit(identity, FAMILY_STATBLOCK_GENERATE)
    demo_quota_store.release(identity)
    demo_quota_store.admit(identity, FAMILY_CARD_GENERATE_ITEM)
    demo_quota_store.release(identity)
    demo_quota_store.admit(identity, FAMILY_STATBLOCK_GENERATE)
    demo_quota_store.release(identity)
    with pytest.raises(Exception) as exc:
        demo_quota_store.admit(identity, FAMILY_CARD_GENERATE_ITEM)
    assert exc.value.status_code == 429
    demo_quota_store.reset()
    demo_quota_store.daily_limit = DEFAULT_DAILY_LIMIT


def test_paid_budget_debits_units():
    paid_budget_store.reset()
    paid_budget_store.daily_limit = 5
    paid_budget_store.consume("u1", units=3)
    paid_budget_store.consume("u1", units=2)
    with pytest.raises(Exception) as exc:
        paid_budget_store.consume("u1", units=1)
    assert exc.value.status_code == 429
    paid_budget_store.reset()
    paid_budget_store.daily_limit = 100


def test_clamp_num_images():
    assert clamp_num_images(4) == 4
    with pytest.raises(Exception) as exc:
        clamp_num_images(MAX_IMAGES_PER_REQUEST + 1)
    assert exc.value.status_code == 422


def test_open_image_bounded_rejects_huge_dimensions(monkeypatch):
    from PIL import Image
    import io

    # Tiny PNG that claims huge size is hard; instead mock Image.open
    class FakeImg:
        size = (20000, 20000)

        def load(self):
            return None

    monkeypatch.setattr("security_limits.image_bounds.Image.open", lambda *_a, **_k: FakeImg())
    with pytest.raises(Exception) as exc:
        open_image_bounded(b"fakepng")
    assert exc.value.status_code == 413


def test_twilio_test_mode_forbidden_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TWILIO_TEST_MODE", "true")
    with pytest.raises(RuntimeError, match="TWILIO_TEST_MODE"):
        assert_safe_production_config()


def test_delete_requires_registry_asset_not_project_url(test_client):
    """URL presence in a project must not authorize delete; only asset_id + owner."""
    from routers.auth_router import get_current_user
    from auth_service import User
    from routers import image_management_router as imr
    from services import image_asset_registry as registry

    async def _user_a():
        return User(sub="user-a", email="a@example.com", name="A")

    app = test_client.app
    app.dependency_overrides[get_current_user] = _user_a

    # Legacy URL-only delete must fail (asset_id required)
    resp = test_client.delete(
        "/api/images/delete",
        params={
            "image_url": "https://imagedelivery.net/acct/victim/Full",
            "service": "map",
        },
    )
    assert resp.status_code in (422, 400)

    # Forged: attacker has no registry row
    with patch.object(registry, "get_asset_for_owner", return_value=None):
        resp2 = test_client.delete(
            "/api/images/delete",
            params={"asset_id": "not-owned-asset", "service": "map"},
        )
        assert resp2.status_code == 403

    app.dependency_overrides.clear()


def test_upload_rejects_non_image_at_validation_boundary(test_client):
    from routers.auth_router import get_current_user
    from auth_service import User
    from security_limits.image_validation import validate_image_bytes

    # Prove boundary without requiring Cloudflare
    with pytest.raises(Exception) as exc:
        validate_image_bytes(b"not-an-image-payload")
    assert exc.value.status_code == 400

    async def _user():
        return User(sub="user-a", email="a@example.com", name="A")

    app = test_client.app
    app.dependency_overrides[get_current_user] = _user
    try:
        resp = test_client.post(
            "/api/images/upload",
            files={"file": ("x.bin", b"not-an-image-payload", "image/png")},
        )
        # Must fail at validation (400) before CF — never 200
        assert resp.status_code == 400
        assert "image" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_production_surface_and_auth_gates(test_client, monkeypatch):
    monkeypatch.setenv(INTERNAL_KEY_ENV, "prod-smoke-internal-key")
    from app import create_app

    production_app = create_app()
    paths = {route.path for route in production_app.routes if isinstance(route, APIRoute)}
    assert not any(p.startswith("/api/demo") for p in paths)

    client = test_client
    assert client.get("/api/demo/health").status_code == 404

    unauth_upload = client.post(
        "/api/images/upload",
        files={"file": ("x.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, "image/png")},
    )
    assert unauth_upload.status_code in (401, 403)

    unauth_core = client.post(
        "/api/v1/cardgenerator/generate-core-images",
        data={"sdPrompt": "dragon", "numImages": "1"},
    )
    assert unauth_core.status_code in (401, 403)

    from routers.auth_router import get_current_user
    from auth_service import User

    async def _fake_user():
        return User(sub="user-a", email="a@example.com", name="A")

    app = client.app
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        ssrf = client.get(
            "/api/mapgenerator/download",
            params={"url": "https://evil.example/ssrf"},
        )
        assert ssrf.status_code == 400
    finally:
        app.dependency_overrides.clear()

    sms_retry = client.get("/api/sms/retry-failed")
    assert sms_retry.status_code in (401, 403)
    sms_keyed = client.get(
        "/api/sms/retry-failed",
        headers={INTERNAL_KEY_HEADER: "prod-smoke-internal-key"},
    )
    assert sms_keyed.status_code in (200, 500)
    assert sms_keyed.status_code not in (401, 403)


def test_ruleslawyer_control_endpoints_require_internal_key(test_client, monkeypatch):
    monkeypatch.setenv(INTERNAL_KEY_ENV, "rl-internal-key")
    client = test_client

    refresh = client.post(
        "/api/ruleslawyer/rulebooks/refresh",
        json={"rulebookIds": ["x"], "reason": "test"},
    )
    assert refresh.status_code in (401, 403)

    load = client.post(
        "/api/ruleslawyer/loadembeddings",
        json={
            "embedding": "x",
            "embeddings_file_path": "a.csv",
            "enhanced_json_path": "b.json",
        },
    )
    assert load.status_code in (401, 403)


def test_ruleslawyer_path_traversal_rejected():
    from routers.ruleslawyer_router import _resolve_under_ruleslawyer_data_dir
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _resolve_under_ruleslawyer_data_dir("../../etc/passwd")
    assert exc.value.status_code == 400


def test_decode_data_uri_bounded_rejects_oversized_and_bad_b64():
    from security_limits.image_bounds import decode_data_uri_bounded, MAX_DATA_URI_CHARS

    with pytest.raises(Exception) as exc:
        decode_data_uri_bounded("not-a-data-uri", field="maskBase64")
    assert exc.value.status_code == 400

    huge = "data:image/png;base64," + ("A" * (MAX_DATA_URI_CHARS + 1))
    with pytest.raises(Exception) as exc2:
        decode_data_uri_bounded(huge, field="maskBase64")
    assert exc2.value.status_code == 413


def test_open_image_bounded_checks_size_before_load(monkeypatch):
    """Regression: dimension reject must happen before img.load()."""
    load_called = {"n": 0}

    class FakeImg:
        size = (20000, 20000)

        def load(self):
            load_called["n"] += 1
            return None

    monkeypatch.setattr(
        "security_limits.image_bounds.Image.open", lambda *_a, **_k: FakeImg()
    )
    with pytest.raises(Exception) as exc:
        open_image_bounded(b"fakepng")
    assert exc.value.status_code == 413
    assert load_called["n"] == 0


def test_create_map_project_unowned_url_returns_403_not_500(test_client):
    from routers.auth_router import get_current_user
    from auth_service import User
    from services import image_asset_registry as registry

    async def _user():
        return User(sub="user-a", email="a@example.com", name="A")

    app = test_client.app
    app.dependency_overrides[get_current_user] = _user
    try:
        with patch.object(registry, "get_owned_asset_by_url", return_value=None):
            resp = test_client.post(
                "/api/mapgenerator/projects",
                json={
                    "name": "Forged",
                    "baseImageUrl": "https://imagedelivery.net/acct/victim/public",
                },
            )
        assert resp.status_code == 403
        assert "owned" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_cloudflare_image_id_from_url():
    from services.image_asset_registry import cloudflare_image_id_from_url

    assert (
        cloudflare_image_id_from_url(
            "https://imagedelivery.net/acctHash/img-uuid-123/public"
        )
        == "img-uuid-123"
    )
