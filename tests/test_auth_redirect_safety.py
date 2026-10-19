from importlib import import_module
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from starlette.middleware.sessions import SessionMiddleware


@pytest.fixture
def stubbed_oauth_redirects(monkeypatch):
    auth_router = import_module('routers.auth_router')

    monkeypatch.setattr(auth_router, '_oauth_configured', True)

    async def authorize_redirect(_request, _redirect_uri, **_kwargs):
        return JSONResponse({'ok': True})

    async def authorize_access_token(_request):
        return {'id_token': 'test-only'}

    async def parse_id_token(_token, **_kwargs):
        return {'sub': 'return-path-test-user', 'email': 'test@example.test'}

    fake_google = SimpleNamespace(
        authorize_redirect=authorize_redirect,
        authorize_access_token=authorize_access_token,
        parse_id_token=parse_id_token,
    )
    monkeypatch.setattr(auth_router, 'oauth', SimpleNamespace(google=fake_google))
    return auth_router


@pytest.fixture
def auth_app(stubbed_oauth_redirects):
    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key='test-only-auth-redirect-secret',
    )
    app.include_router(stubbed_oauth_redirects.router, prefix='/api/auth')
    return app


async def test_login_callback_preserves_same_origin_path_query_and_fragment(
    auth_app, monkeypatch
):
    monkeypatch.setenv('REACT_LANDING_URL', 'https://app.example.test')
    return_path = '/world/elderwyld?view=play&search=moon%20bridge#scene-4'

    async with AsyncClient(
        transport=ASGITransport(app=auth_app),
        base_url='http://testserver',
        follow_redirects=False,
    ) as client:
        login = await client.get('/api/auth/login', params={'redirect': return_path})
        assert login.status_code == 200

        callback = await client.get('/api/auth/callback')
        assert callback.status_code == 307
        assert callback.headers['location'] == 'https://app.example.test' + return_path


@pytest.mark.parametrize(
    'return_target',
    [
        'https://attacker.example',
        '//attacker.example/path',
        '///attacker.example/path',
        '@attacker.example',
        '/\\\\attacker.example/path',
        '/%252f%252fattacker.example/path',
        '/%255c%255cattacker.example/path',
        '/path\r\nLocation: https://attacker.example',
    ],
)
async def test_login_replaces_external_or_ambiguous_return_targets_with_root(
    auth_app, monkeypatch, return_target
):
    monkeypatch.setenv('REACT_LANDING_URL', 'https://app.example.test')

    async with AsyncClient(
        transport=ASGITransport(app=auth_app),
        base_url='http://testserver',
        follow_redirects=False,
    ) as client:
        login = await client.get('/api/auth/login', params={'redirect': return_target})
        assert login.status_code == 200

        callback = await client.get('/api/auth/callback')
        assert callback.status_code == 307
        assert callback.headers['location'] == 'https://app.example.test/'


@pytest.mark.asyncio
async def test_callback_revalidates_an_existing_session_return_target(
    monkeypatch, stubbed_oauth_redirects
):
    from routers.auth_router import auth_callback

    monkeypatch.setenv('REACT_LANDING_URL', 'https://app.example.test')
    request = SimpleNamespace(session={'return_to': '//attacker.example/path', 'nonce': None})

    response = await auth_callback(request)

    assert response.status_code == 307
    assert response.headers['location'] == 'https://app.example.test/'
