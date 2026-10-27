from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.datastructures import QueryParams
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse

from auth_router_test_support import load_auth_router


OAUTH_STATE = "synthetic-oauth-state"


@pytest.fixture
def stubbed_oauth_redirects(monkeypatch):
    auth_router = load_auth_router()
    monkeypatch.setattr(auth_router, "_oauth_configured", True)
    calls = {"access_token": 0, "authorize_redirect": 0}

    async def authorize_redirect(_request, _redirect_uri, **_kwargs):
        calls["authorize_redirect"] += 1
        state = (
            OAUTH_STATE
            if calls["authorize_redirect"] == 1
            else f"{OAUTH_STATE}-{calls['authorize_redirect']}"
        )
        return RedirectResponse(
            url=f"https://accounts.example.test/authorize?state={state}"
        )

    async def authorize_access_token(request):
        calls["access_token"] += 1
        if request.query_params.get("code") == "provider-failure":
            raise RuntimeError("synthetic OAuth failure")
        return {"id_token": "test-only"}

    async def parse_id_token(_token, **_kwargs):
        return {"sub": "return-path-test-user", "email": "test@example.test"}

    fake_google = SimpleNamespace(
        authorize_redirect=authorize_redirect,
        authorize_access_token=authorize_access_token,
        parse_id_token=parse_id_token,
    )
    monkeypatch.setattr(auth_router, "oauth", SimpleNamespace(google=fake_google))
    auth_router._test_calls = calls
    return auth_router


@pytest.fixture
def auth_app(stubbed_oauth_redirects):
    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key="test-only-auth-redirect-secret",
    )
    app.include_router(stubbed_oauth_redirects.router, prefix="/api/auth")
    return app


async def _login_and_callback(client, *, login_params=None, callback_params=None):
    login = await client.get("/api/auth/login", params=login_params or {})
    callback = await client.get(
        "/api/auth/callback",
        params={"state": OAUTH_STATE, **(callback_params or {})},
    )
    return login, callback


async def test_login_without_selector_preserves_website_return_and_query_fragment(
    auth_app, monkeypatch
):
    monkeypatch.setenv("REACT_LANDING_URL", "https://app.example.test/")
    return_path = "/world/elderwyld?view=play&search=moon%2Fbridge#scene-4"

    async with AsyncClient(
        transport=ASGITransport(app=auth_app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        login, callback = await _login_and_callback(
            client, login_params={"redirect": return_path}
        )

    assert login.status_code == 307
    assert "state=" + OAUTH_STATE in login.headers["location"]
    assert callback.status_code == 307
    assert callback.headers["location"] == "https://app.example.test" + return_path


async def test_buddy_selector_returns_to_server_owned_buddy_origin_and_original_route(
    auth_app, monkeypatch
):
    monkeypatch.setenv("REACT_LANDING_URL", "https://app.example.test")
    monkeypatch.setenv("BUDDY_FRONTEND_URL", "https://buddy.example.test")
    return_path = "/play/run-7?panel=history#turn-3"

    async with AsyncClient(
        transport=ASGITransport(app=auth_app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        login, callback = await _login_and_callback(
            client,
            login_params={"frontend": "buddy", "redirect": return_path},
        )

    assert login.status_code == 307
    assert callback.status_code == 307
    assert callback.headers["location"] == "https://buddy.example.test" + return_path


async def test_overlapping_login_flows_keep_independent_routes_and_consume_on_replay(
    auth_app, monkeypatch, stubbed_oauth_redirects
):
    monkeypatch.setenv("REACT_LANDING_URL", "https://app.example.test")
    monkeypatch.setenv("BUDDY_FRONTEND_URL", "https://buddy.example.test")

    async with AsyncClient(
        transport=ASGITransport(app=auth_app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        first_login = await client.get(
            "/api/auth/login",
            params={"frontend": "buddy", "redirect": "/play/first?turn=3"},
        )
        second_login = await client.get(
            "/api/auth/login",
            params={"frontend": "buddy", "redirect": "/play/second?turn=8"},
        )
        first_state = QueryParams(urlsplit(first_login.headers["location"]).query).get("state")
        second_state = QueryParams(urlsplit(second_login.headers["location"]).query).get("state")
        invalid_callback = await client.get(
            "/api/auth/callback", params={"state": "unrecognized-state", "code": "invalid"}
        )
        first_callback = await client.get(
            "/api/auth/callback", params={"state": first_state, "code": "first"}
        )
        second_callback = await client.get(
            "/api/auth/callback", params={"state": second_state, "code": "second"}
        )
        replay = await client.get(
            "/api/auth/callback", params={"state": first_state, "code": "replay"}
        )

    assert first_state != second_state
    assert invalid_callback.headers["location"] == "https://app.example.test/?auth_error=true"
    assert first_callback.headers["location"] == "https://buddy.example.test/play/first?turn=3"
    assert second_callback.headers["location"] == "https://buddy.example.test/play/second?turn=8"
    assert replay.headers["location"] == "https://app.example.test/?auth_error=true"
    assert stubbed_oauth_redirects._test_calls["access_token"] == 2


async def test_unknown_frontend_selector_uses_website_default(auth_app, monkeypatch):
    monkeypatch.setenv("REACT_LANDING_URL", "https://app.example.test")
    monkeypatch.setenv("BUDDY_FRONTEND_URL", "https://buddy.example.test")

    async with AsyncClient(
        transport=ASGITransport(app=auth_app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        _, callback = await _login_and_callback(
            client,
            login_params={"frontend": "attacker", "redirect": "/plan"},
        )

    assert callback.headers["location"] == "https://app.example.test/plan"


@pytest.mark.parametrize(
    "return_target",
    [
        "https://attacker.example",
        "//attacker.example/path",
        "///attacker.example/path",
        "@attacker.example",
        "/\\\\attacker.example/path",
        "/%252f%252fattacker.example/path",
        "/%255c%255cattacker.example/path",
        "/%252%66host",
        "/%25%32%66%25%32%66host",
        "/%255%63host",
        "/%250%64x",
        "/" + ("a" * 512),
        "/path\r\nLocation: https://attacker.example",
    ],
)
async def test_login_replaces_external_or_ambiguous_return_targets_with_root(
    auth_app, monkeypatch, return_target
):
    monkeypatch.setenv("REACT_LANDING_URL", "https://app.example.test")
    monkeypatch.setenv("BUDDY_FRONTEND_URL", "https://buddy.example.test")

    async with AsyncClient(
        transport=ASGITransport(app=auth_app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        _, callback = await _login_and_callback(
            client,
            login_params={"frontend": "buddy", "redirect": return_target},
        )

    assert callback.headers["location"] == "https://buddy.example.test/"


@pytest.mark.parametrize(
    ("provider_error", "expected_error"),
    [("access_denied", "cancelled"), ("server_error", "failed")],
)
async def test_buddy_cancellation_and_error_return_to_safe_intended_route(
    auth_app, monkeypatch, provider_error, expected_error
):
    monkeypatch.setenv("REACT_LANDING_URL", "https://app.example.test")
    monkeypatch.setenv("BUDDY_FRONTEND_URL", "https://buddy.example.test")
    return_path = "/plan?view=timeline&auth_error=stale#session-8"

    async with AsyncClient(
        transport=ASGITransport(app=auth_app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        login = await client.get(
            "/api/auth/login",
            params={"frontend": "buddy", "redirect": return_path},
        )
        callback = await client.get(
            "/api/auth/callback",
            params={"state": OAUTH_STATE, "error": provider_error},
        )

    assert login.status_code == 307
    assert callback.headers["location"] == (
        "https://buddy.example.test/plan?view=timeline&auth_error="
        f"{expected_error}#session-8"
    )


async def test_website_callback_error_keeps_existing_root_error_behavior(
    auth_app, monkeypatch
):
    monkeypatch.setenv("REACT_LANDING_URL", "https://app.example.test")

    async with AsyncClient(
        transport=ASGITransport(app=auth_app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        await client.get(
            "/api/auth/login",
            params={"redirect": "/plan?view=timeline#session-8"},
        )
        callback = await client.get(
            "/api/auth/callback",
            params={"state": OAUTH_STATE, "error": "access_denied"},
        )

    assert callback.headers["location"] == "https://app.example.test/?auth_error=true"


@pytest.mark.parametrize("buddy_origin", [None, "https://buddy.example.test/path", "//attacker.test"])
async def test_invalid_buddy_origin_falls_back_to_validated_website(
    auth_app, monkeypatch, buddy_origin
):
    monkeypatch.setenv("REACT_LANDING_URL", "https://app.example.test")
    monkeypatch.delenv("BUDDY_FRONTEND_URL", raising=False)
    if buddy_origin is not None:
        monkeypatch.setenv("BUDDY_FRONTEND_URL", buddy_origin)

    async with AsyncClient(
        transport=ASGITransport(app=auth_app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        login = await client.get(
            "/api/auth/login", params={"frontend": "buddy", "redirect": "/play"}
        )

    assert login.status_code == 307
    assert login.headers["location"] == "https://app.example.test/?auth_error=true"


async def test_missing_or_duplicate_state_falls_back_and_does_not_call_provider(
    auth_app, monkeypatch, stubbed_oauth_redirects
):
    monkeypatch.setenv("REACT_LANDING_URL", "https://app.example.test")

    async with AsyncClient(
        transport=ASGITransport(app=auth_app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        await client.get("/api/auth/login", params={"frontend": "buddy"})
        missing = await client.get("/api/auth/callback")
        await client.get("/api/auth/login", params={"frontend": "buddy"})
        duplicate = await client.get(
            "/api/auth/callback?state=synthetic-oauth-state&state=other"
        )

    assert missing.headers["location"] == "https://app.example.test/?auth_error=true"
    assert duplicate.headers["location"] == "https://app.example.test/?auth_error=true"
    assert stubbed_oauth_redirects._test_calls["access_token"] == 0


@pytest.mark.parametrize(
    "intent",
    [
        {"state": "different-state", "frontend": "buddy", "return_to": "/play"},
        {"state": OAUTH_STATE, "frontend": "attacker", "return_to": "/play"},
    ],
)
async def test_tampered_session_intent_never_supplies_redirect_authority(
    monkeypatch, stubbed_oauth_redirects, intent
):
    monkeypatch.setenv("REACT_LANDING_URL", "https://app.example.test")
    monkeypatch.setenv("BUDDY_FRONTEND_URL", "https://buddy.example.test")
    request = SimpleNamespace(
        session={"auth_returns": {OAUTH_STATE: intent}, "user": {"sub": "existing-test-user"}},
        query_params=QueryParams({"state": OAUTH_STATE}),
    )

    response = await stubbed_oauth_redirects.auth_callback(request)

    assert response.headers["location"] == "https://app.example.test/?auth_error=true"
    assert "auth_returns" not in request.session
    assert request.session["user"]["sub"] == "existing-test-user"
    assert stubbed_oauth_redirects._test_calls["access_token"] == 0


async def test_tampered_external_return_path_is_reduced_to_buddy_root(
    monkeypatch, stubbed_oauth_redirects
):
    monkeypatch.setenv("REACT_LANDING_URL", "https://app.example.test")
    monkeypatch.setenv("BUDDY_FRONTEND_URL", "https://buddy.example.test")
    request = SimpleNamespace(
        session={
            "auth_returns": {
                OAUTH_STATE: {
                    "state": OAUTH_STATE,
                    "frontend": "buddy",
                    "return_to": "//attacker.test/path",
                }
            },
        },
        query_params=QueryParams({"state": OAUTH_STATE}),
    )

    response = await stubbed_oauth_redirects.auth_callback(request)

    assert response.headers["location"] == "https://buddy.example.test/"
    assert "auth_returns" not in request.session


async def test_successful_callback_consumes_return_intent_and_keeps_identity(
    monkeypatch, stubbed_oauth_redirects
):
    monkeypatch.setenv("REACT_LANDING_URL", "https://app.example.test")
    request = SimpleNamespace(
        session={
            "auth_returns": {
                OAUTH_STATE: {
                    "state": OAUTH_STATE,
                    "frontend": "website",
                    "return_to": "/plan?view=timeline",
                }
            },
            "nonce": None,
        },
        query_params=QueryParams({"state": OAUTH_STATE, "code": "synthetic"}),
    )

    response = await stubbed_oauth_redirects.auth_callback(request)

    assert response.headers["location"] == "https://app.example.test/plan?view=timeline"
    assert "auth_returns" not in request.session
    assert request.session["user"]["sub"] == "return-path-test-user"


async def test_oauth_exception_returns_to_buddy_route_and_cleans_intent(
    monkeypatch, stubbed_oauth_redirects
):
    monkeypatch.setenv("REACT_LANDING_URL", "https://app.example.test")
    monkeypatch.setenv("BUDDY_FRONTEND_URL", "https://buddy.example.test")
    request = SimpleNamespace(
        session={
            "auth_returns": {
                OAUTH_STATE: {
                    "state": OAUTH_STATE,
                    "frontend": "buddy",
                    "return_to": "/play?session=failed#turn-2",
                }
            },
            "nonce": None,
        },
        query_params=QueryParams(
            {"state": OAUTH_STATE, "code": "provider-failure"}
        ),
    )

    response = await stubbed_oauth_redirects.auth_callback(request)

    assert response.headers["location"] == (
        "https://buddy.example.test/play?session=failed&auth_error=failed#turn-2"
    )
    assert "auth_returns" not in request.session


async def test_invalid_buddy_configuration_at_callback_falls_back_safely(
    auth_app, monkeypatch
):
    monkeypatch.setenv("REACT_LANDING_URL", "https://app.example.test")
    monkeypatch.setenv("BUDDY_FRONTEND_URL", "https://buddy.example.test")

    async with AsyncClient(
        transport=ASGITransport(app=auth_app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        await client.get(
            "/api/auth/login",
            params={"frontend": "buddy", "redirect": "/play/run-2?turn=8"},
        )
        monkeypatch.setenv("BUDDY_FRONTEND_URL", "https://attacker.test/path")
        callback = await client.get(
            "/api/auth/callback", params={"state": OAUTH_STATE, "code": "synthetic"}
        )

    assert callback.headers["location"] == "https://app.example.test/?auth_error=true"
