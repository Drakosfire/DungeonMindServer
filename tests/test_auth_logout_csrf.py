from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from starlette.middleware.sessions import SessionMiddleware

from auth_router_test_support import load_auth_router


@pytest.fixture
def logout_app(monkeypatch):
    auth_router = load_auth_router()
    monkeypatch.setattr(auth_router, '_oauth_configured', True)

    async def authorize_redirect(_request, _redirect_uri, **_kwargs):
        from fastapi.responses import JSONResponse

        return JSONResponse({'ok': True})

    async def authorize_access_token(_request):
        return {'id_token': 'test-only'}

    async def parse_id_token(_token, **_kwargs):
        return {'sub': 'logout-test-user', 'email': 'test@example.test'}

    fake_google = SimpleNamespace(
        authorize_redirect=authorize_redirect,
        authorize_access_token=authorize_access_token,
        parse_id_token=parse_id_token,
    )
    monkeypatch.setattr(auth_router, 'oauth', SimpleNamespace(google=fake_google))

    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key='test-only-auth-logout-secret',
        session_cookie='dungeonmind_session',
    )

    @app.get('/test/seed-session')
    async def seed_session(request: Request):
        request.session['user'] = {
            'sub': 'logout-test-user',
            'email': 'test@example.test',
        }
        return {'ok': True}

    app.include_router(auth_router.router, prefix='/api/auth')
    return app


@pytest.fixture
def auth_origin_allowlist(monkeypatch):
    monkeypatch.setenv(
        'AUTH_TRUSTED_FRONTEND_ORIGINS',
        'https://app.example.test,http://localhost:3000',
    )


async def test_trusted_post_clears_session_returns_204_and_is_idempotent(
    logout_app, auth_origin_allowlist
):
    async with AsyncClient(
        transport=ASGITransport(app=logout_app),
        base_url='http://testserver',
        follow_redirects=False,
    ) as client:
        seeded = await client.get('/test/seed-session')
        assert seeded.status_code == 200
        assert (await client.get('/api/auth/profile')).status_code == 200

        response = await client.post(
            '/api/auth/logout',
            headers={'Origin': 'https://app.example.test'},
        )

        assert response.status_code == 204
        assert response.content == b''
        assert 'dungeonmind_session=' in response.headers['set-cookie']
        assert 'dungeonmind_session=null' in response.headers['set-cookie']
        assert 'expires=thu, 01 jan 1970' in response.headers['set-cookie'].lower()
        assert (await client.get('/api/auth/profile')).status_code == 401

        repeated = await client.post(
            '/api/auth/logout',
            headers={'Origin': 'https://app.example.test'},
        )
        assert repeated.status_code == 204


@pytest.mark.parametrize(
    'origin',
    [
        None,
        'null',
        'https://app.example.test/path',
        'https://app.example.test?query=1',
        'https://user@app.example.test',
        'https://attacker.example',
        'https://app.example.test, https://attacker.example',
    ],
)
async def test_rejected_origin_does_not_clear_existing_session(
    logout_app, auth_origin_allowlist, origin
):
    async with AsyncClient(
        transport=ASGITransport(app=logout_app),
        base_url='http://testserver',
        follow_redirects=False,
    ) as client:
        await client.get('/test/seed-session')
        before_cookie = client.cookies.get('dungeonmind_session')
        headers = {} if origin is None else {'Origin': origin}

        response = await client.post('/api/auth/logout', headers=headers)

        assert response.status_code == 403
        assert client.cookies.get('dungeonmind_session') == before_cookie
        assert 'Max-Age=0' not in response.headers.get('set-cookie', '')
        assert (await client.get('/api/auth/profile')).status_code == 200


async def test_malformed_allowlist_fails_closed_without_session_mutation(
    logout_app, monkeypatch
):
    monkeypatch.setenv(
        'AUTH_TRUSTED_FRONTEND_ORIGINS',
        'https://app.example.test,https://other.example/path',
    )
    async with AsyncClient(
        transport=ASGITransport(app=logout_app),
        base_url='http://testserver',
        follow_redirects=False,
    ) as client:
        await client.get('/test/seed-session')
        before_cookie = client.cookies.get('dungeonmind_session')

        response = await client.post(
            '/api/auth/logout',
            headers={'Origin': 'https://app.example.test'},
        )

        assert response.status_code == 403
        assert client.cookies.get('dungeonmind_session') == before_cookie
        assert (await client.get('/api/auth/profile')).status_code == 200


async def test_duplicate_origin_headers_are_rejected_without_session_mutation(
    logout_app, auth_origin_allowlist
):
    async with AsyncClient(
        transport=ASGITransport(app=logout_app),
        base_url='http://testserver',
        follow_redirects=False,
    ) as client:
        await client.get('/test/seed-session')
        before_cookie = client.cookies.get('dungeonmind_session')

        response = await client.post(
            '/api/auth/logout',
            headers=[
                ('Origin', 'https://app.example.test'),
                ('Origin', 'https://attacker.example'),
            ],
        )

        assert response.status_code == 403
        assert client.cookies.get('dungeonmind_session') == before_cookie
        assert (await client.get('/api/auth/profile')).status_code == 200


async def test_unset_allowlist_fails_closed_without_session_mutation(
    logout_app, monkeypatch
):
    monkeypatch.delenv('AUTH_TRUSTED_FRONTEND_ORIGINS', raising=False)
    async with AsyncClient(
        transport=ASGITransport(app=logout_app),
        base_url='http://testserver',
        follow_redirects=False,
    ) as client:
        await client.get('/test/seed-session')
        before_cookie = client.cookies.get('dungeonmind_session')

        response = await client.post(
            '/api/auth/logout',
            headers={'Origin': 'https://app.example.test'},
        )

        assert response.status_code == 403
        assert client.cookies.get('dungeonmind_session') == before_cookie
        assert (await client.get('/api/auth/profile')).status_code == 200


async def test_get_logout_is_nonmutating_405(logout_app, auth_origin_allowlist):
    async with AsyncClient(
        transport=ASGITransport(app=logout_app),
        base_url='http://testserver',
        follow_redirects=False,
    ) as client:
        await client.get('/test/seed-session')
        before_cookie = client.cookies.get('dungeonmind_session')

        response = await client.get(
            '/api/auth/logout',
            headers={'Origin': 'https://app.example.test'},
        )

        assert response.status_code == 405
        assert 'location' not in response.headers
        assert client.cookies.get('dungeonmind_session') == before_cookie
        assert (await client.get('/api/auth/profile')).status_code == 200
