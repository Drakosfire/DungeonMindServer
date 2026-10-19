from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from models.session_models import RulesLawyerSessionState
from session_management import EnhancedGlobalSessionManager


@pytest.fixture
def session_api(monkeypatch):
    from unittest.mock import MagicMock

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DUNGEONMIND_API_URL", "http://localhost:7860")
    monkeypatch.setenv("REACT_LANDING_URL", "http://localhost:3000")

    import auth_service as auth_service_module
    import firestore.firebase_config as firebase_config
    import session_config as session_config_module
    import session_management

    monkeypatch.setattr(
        firebase_config,
        "db",
        MagicMock(name="session_contract_firestore_stub"),
    )
    import routers.global_session_router as global_session_router
    import routers.global_objects_router as global_objects_router
    import routers.session_router as session_router

    manager = EnhancedGlobalSessionManager(session_timeout_hours=1)
    monkeypatch.setattr(global_session_router, "session_manager", manager)
    monkeypatch.setattr(session_management, "session_manager", manager)

    async def anonymous_auth(_request):
        from auth_service import AuthResult

        return AuthResult(authenticated=False, error="No test principal")

    monkeypatch.setattr(
        auth_service_module.auth_service,
        "get_current_user_from_request",
        anonymous_auth,
    )
    monkeypatch.setattr(
        session_config_module.session_config,
        "get_cookie_kwargs",
        lambda: {"httponly": True, "secure": False, "samesite": "lax"},
    )
    api = FastAPI()
    api.include_router(global_session_router.router)
    api.include_router(global_objects_router.router)
    api.include_router(session_router)
    return api, manager


@pytest.fixture
async def async_client(session_api):
    api, manager = session_api
    async with AsyncClient(
        transport=ASGITransport(app=api),
        base_url="http://testserver",
    ) as client:
        yield client, manager


def assert_public_snapshot(snapshot, session_id):
    assert snapshot["schema_version"] == 1
    assert snapshot["session_id"] == session_id
    assert "ip_address" not in snapshot
    assert "user_agent" not in snapshot


@pytest.mark.asyncio
async def test_create_returns_versioned_snapshot_after_preferences_and_cookie(async_client):
    client, manager = async_client

    response = await client.post(
        "/api/session/create",
        json={
            "user_id": "user-1",
            "platform": "web",
            "preferences": {"theme": "dark", "language": "fr"},
        },
        headers={"user-agent": "private-agent-marker"},
    )

    assert response.status_code == 200
    payload = response.json()
    session_id = payload["session_id"]
    assert payload["schema_version"] == 1
    assert payload["outcome"] == "created"
    assert payload["success"] is True
    assert_public_snapshot(payload["session"], session_id)
    assert payload["session"]["user_id"] is None
    assert payload["session"]["preferences"]["theme"] == "dark"
    assert payload["session"]["preferences"]["language"] == "fr"
    assert response.cookies["dungeonmind_session_id"] == session_id
    assert manager.sessions[session_id]._authenticated_principal_id is None
    assert manager.sessions[session_id].user_agent == "private-agent-marker"
    assert manager.sessions[session_id].ip_address is not None
    assert len(manager.sessions) == 1

    # The caller-supplied identity did not grant access to protected objects.
    objects_response = await client.get("/api/objects/")
    assert objects_response.status_code == 401


@pytest.mark.asyncio
async def test_restore_returns_existing_state_and_restored_outcome(async_client):
    client, manager = async_client
    session_id = manager.create_session(user_id="user-2")
    stored = manager.sessions[session_id]
    stored.clipboard = ["object-a", "object-b"]
    stored.recently_viewed = ["object-c"]
    stored.preferences.theme = "dark"
    stored.ruleslawyer = RulesLawyerSessionState(
        active_query_history=[{"role": "user", "content": "saved question"}]
    )
    stored.ip_address = "private-ip-marker"
    stored.user_agent = "private-agent-marker"

    response = await client.post(
        "/api/session/restore",
        json={"session_id": session_id, "fallback_to_new": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["outcome"] == "restored"
    assert payload["session_id"] == session_id
    assert_public_snapshot(payload["session"], session_id)
    assert payload["session"]["clipboard"] == ["object-a", "object-b"]
    assert payload["session"]["recently_viewed"] == ["object-c"]
    assert payload["session"]["preferences"]["theme"] == "dark"
    assert payload["session"]["user_id"] is None
    assert payload["session"]["ruleslawyer"]["active_query_history"] == [
        {"role": "user", "content": "saved question"}
    ]
    assert len(manager.sessions) == 1


@pytest.mark.asyncio
async def test_restore_fallback_creates_one_session_and_returns_created_fallback(async_client):
    client, manager = async_client
    expired_id = manager.create_session(user_id="user-3")
    manager.sessions[expired_id].expires_at = datetime.now() - timedelta(seconds=1)

    response = await client.post(
        "/api/session/restore",
        json={"session_id": expired_id, "fallback_to_new": True},
    )

    assert response.status_code == 200
    payload = response.json()
    new_session_id = payload["session_id"]
    assert payload["outcome"] == "created_fallback"
    assert new_session_id != expired_id
    assert_public_snapshot(payload["session"], new_session_id)
    assert response.cookies["dungeonmind_session_id"] == new_session_id
    assert expired_id not in manager.sessions
    assert list(manager.sessions) == [new_session_id]


@pytest.mark.asyncio
async def test_restore_without_fallback_returns_typed_not_found_without_creating(async_client):
    client, manager = async_client

    response = await client.post(
        "/api/session/restore",
        json={"session_id": "missing-session", "fallback_to_new": False},
    )

    assert response.status_code == 404
    assert response.json() == {
        "schema_version": 1,
        "outcome": "not_found",
        "success": False,
        "session_id": None,
        "session": None,
        "status": None,
        "message": "Session not found and fallback creation is disabled",
    }
    assert len(manager.sessions) == 0
    assert "dungeonmind_session_id" not in response.cookies


def test_openapi_declares_versioned_success_and_restore_not_found_contract(session_api):
    api, _ = session_api
    schema = api.openapi()
    create_responses = schema["paths"]["/api/session/create"]["post"]["responses"]
    restore_responses = schema["paths"]["/api/session/restore"]["post"]["responses"]
    schemas = schema["components"]["schemas"]

    assert "SessionAvailableResponseV1" in schemas
    assert "SessionSnapshotV1" in schemas
    assert "SessionNotFoundResponseV1" in schemas
    assert "SessionAvailableResponseV1" in str(create_responses["200"])
    assert "SessionNotFoundResponseV1" in str(restore_responses["404"])
    assert schemas["SessionSnapshotV1"]["properties"]["schema_version"]["default"] == 1
    assert set(schemas["SessionSnapshotV1"]["properties"]).isdisjoint(
        {"ip_address", "user_agent"}
    )


def install_test_principal(monkeypatch, user):
    import auth_service as auth_service_module
    from auth_service import AuthResult

    async def get_current_user_from_request(_request):
        return AuthResult(
            authenticated=user is not None,
            user=user,
            error=None if user is not None else "No test principal",
        )

    monkeypatch.setattr(
        auth_service_module.auth_service,
        "get_current_user_from_request",
        get_current_user_from_request,
    )


@pytest.mark.asyncio
async def test_authenticated_create_ignores_forged_user_id_and_existing_client_uses_cookie(
    async_client, monkeypatch
):
    from auth_service import User
    import routers.global_objects_router as global_objects_router

    client, manager = async_client
    install_test_principal(
        monkeypatch,
        User(sub="verified-user", email="verified@example.test", name="Verified"),
    )

    database_calls = []

    async def list_user_objects(**kwargs):
        database_calls.append(kwargs)
        return []

    monkeypatch.setattr(
        global_objects_router.dungeonmind_db,
        "get_user_objects",
        list_user_objects,
    )

    # Mirrors GlobalSessionAPI.createSession: it still sends user_id for
    # compatibility, but the backend must derive identity from the DMS session.
    create_response = await client.post(
        "/api/session/create",
        json={"platform": "web", "user_id": "forged-user"},
    )

    assert create_response.status_code == 200
    session_id = create_response.json()["session_id"]
    assert create_response.json()["session"]["user_id"] == "verified-user"
    assert manager.sessions[session_id].user_id == "verified-user"
    assert manager.sessions[session_id]._authenticated_principal_id == "verified-user"

    # Mirrors GlobalObjectsAPI: credentials/cookie only, with no session_id query.
    objects_response = await client.get("/api/objects/")

    assert objects_response.status_code == 200
    assert database_calls and database_calls[0]["user_id"] == "verified-user"


@pytest.mark.asyncio
async def test_object_access_rejects_another_authenticated_users_session(
    async_client, monkeypatch
):
    from auth_service import User
    import routers.global_objects_router as global_objects_router
    import auth_service as auth_service_module

    client, _manager = async_client
    current_user = {"value": User(sub="user-a", email="a@example.test", name="A")}

    async def get_current_user_from_request(_request):
        from auth_service import AuthResult

        user = current_user["value"]
        return AuthResult(authenticated=True, user=user)

    monkeypatch.setattr(
        auth_service_module.auth_service,
        "get_current_user_from_request",
        get_current_user_from_request,
    )

    database_calls = []

    async def list_user_objects(**kwargs):
        database_calls.append(kwargs)
        return []

    monkeypatch.setattr(
        global_objects_router.dungeonmind_db,
        "get_user_objects",
        list_user_objects,
    )

    create_response = await client.post(
        "/api/session/create",
        json={"user_id": "user-b"},
    )
    assert create_response.status_code == 200

    current_user["value"] = User(sub="user-b", email="b@example.test", name="B")
    response = await client.get("/api/objects/")

    assert response.status_code == 403
    assert database_calls == []


@pytest.mark.asyncio
async def test_legacy_caller_asserted_session_is_not_migrated_to_authenticated(
    async_client, monkeypatch
):
    from auth_service import User

    client, manager = async_client
    install_test_principal(
        monkeypatch,
        User(sub="user-a", email="a@example.test", name="A"),
    )

    legacy_id = manager.create_session(user_id="user-a")
    client.cookies.set("dungeonmind_session_id", legacy_id)
    response = await client.get("/api/objects/")

    assert response.status_code == 403
    assert manager.sessions[legacy_id]._authenticated_principal_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("locator", ["query", "cookie"])
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/api/session/status", None),
        ("put", "/api/session/tools/cardgenerator", {"active_item_id": "stolen"}),
        ("post", "/api/session/cardgenerator/update", {"active_item_id": "stolen"}),
        ("put", "/api/session/world/world-a", None),
        ("put", "/api/session/project/project-a", None),
        ("put", "/api/session/preferences", {"theme": "dark"}),
        ("delete", "/api/session/clipboard/object-a", None),
        ("delete", "/api/session/{session_id}", None),
    ],
)
async def test_foreign_verified_session_is_not_accessible_by_id_or_cookie(
    async_client, monkeypatch, locator, method, path, body
):
    from auth_service import User

    client, manager = async_client
    owner_session_id = manager.create_session(
        user_id="user-b", authenticated_principal_id="user-b"
    )
    stored = manager.sessions[owner_session_id]
    stored.clipboard = ["object-a"]
    stored.active_world_id = "world-b"
    stored.active_project_id = "project-b"
    stored.preferences.theme = "light"
    before = stored.model_dump()
    install_test_principal(
        monkeypatch,
        User(sub="user-a", email="a@example.test", name="A"),
    )
    if locator == "cookie":
        client.cookies.set("dungeonmind_session_id", owner_session_id)
        query = ""
    else:
        query = f"?session_id={owner_session_id}"
    resolved_path = path.format(session_id=owner_session_id) + query

    if body is None:
        response = await getattr(client, method)(resolved_path)
    else:
        response = await getattr(client, method)(resolved_path, json=body)

    assert response.status_code == 403
    assert manager.sessions[owner_session_id].model_dump() == before


@pytest.mark.asyncio
async def test_verified_session_restore_denies_foreign_and_anonymous_without_fallback(
    async_client, monkeypatch
):
    from auth_service import User

    client, manager = async_client
    owner_session_id = manager.create_session(
        user_id="user-b", authenticated_principal_id="user-b"
    )
    install_test_principal(
        monkeypatch,
        User(sub="user-a", email="a@example.test", name="A"),
    )

    foreign = await client.post(
        "/api/session/restore",
        json={"session_id": owner_session_id, "fallback_to_new": True},
    )
    assert foreign.status_code == 403
    assert set(manager.sessions) == {owner_session_id}

    install_test_principal(monkeypatch, None)
    anonymous = await client.post(
        "/api/session/restore",
        json={"session_id": owner_session_id, "fallback_to_new": True},
    )
    assert anonymous.status_code == 401
    assert set(manager.sessions) == {owner_session_id}


@pytest.mark.asyncio
async def test_restore_cookie_cannot_expose_foreign_verified_session(
    async_client, monkeypatch
):
    from auth_service import User

    client, manager = async_client
    owner_session_id = manager.create_session(
        user_id="user-b", authenticated_principal_id="user-b"
    )
    client.cookies.set("dungeonmind_session_id", owner_session_id)
    install_test_principal(
        monkeypatch,
        User(sub="user-a", email="a@example.test", name="A"),
    )

    response = await client.post(
        "/api/session/restore", json={"fallback_to_new": True}
    )

    assert response.status_code == 403
    assert set(manager.sessions) == {owner_session_id}


@pytest.mark.asyncio
async def test_verified_owner_can_restore_and_use_session(async_client, monkeypatch):
    from auth_service import User

    client, manager = async_client
    owner_session_id = manager.create_session(
        user_id="user-b", authenticated_principal_id="user-b"
    )
    install_test_principal(
        monkeypatch,
        User(sub="user-b", email="b@example.test", name="B"),
    )

    restored = await client.post(
        "/api/session/restore",
        json={"session_id": owner_session_id, "fallback_to_new": False},
    )
    assert restored.status_code == 200
    assert restored.json()["session"]["user_id"] == "user-b"
    client.cookies.set("dungeonmind_session_id", owner_session_id)
    status = await client.get("/api/session/status")
    assert status.status_code == 200
    update = await client.put(
        "/api/session/preferences", json={"theme": "dark"}
    )
    assert update.status_code == 200
    assert manager.sessions[owner_session_id].preferences.theme == "dark"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/api/session/status", None),
        ("put", "/api/session/preferences", {"theme": "dark"}),
        ("delete", "/api/session/clipboard/object-a", None),
    ],
)
async def test_unauthenticated_caller_cannot_use_verified_session_cookie(
    async_client, method, path, body
):
    client, manager = async_client
    session_id = manager.create_session(
        user_id="user-b", authenticated_principal_id="user-b"
    )
    manager.sessions[session_id].clipboard = ["object-a"]
    before = manager.sessions[session_id].model_dump()
    client.cookies.set("dungeonmind_session_id", session_id)

    if body is None:
        response = await getattr(client, method)(path)
    else:
        response = await getattr(client, method)(path, json=body)

    assert response.status_code == 401
    assert manager.sessions[session_id].model_dump() == before


@pytest.mark.asyncio
async def test_markerless_legacy_session_remains_bearer_compatible_but_anonymous(
    async_client
):
    client, manager = async_client
    legacy_id = manager.create_session(user_id="legacy-claimed-user")
    client.cookies.set("dungeonmind_session_id", legacy_id)

    restored = await client.post(
        "/api/session/restore",
        json={"session_id": legacy_id, "fallback_to_new": False},
    )
    assert restored.status_code == 200
    assert restored.json()["session"]["user_id"] is None
    update = await client.put("/api/session/preferences", json={"theme": "dark"})
    assert update.status_code == 200
    assert manager.sessions[legacy_id]._authenticated_principal_id is None
    assert manager.sessions[legacy_id].user_id == "legacy-claimed-user"


@pytest.mark.asyncio
async def test_legacy_session_info_does_not_expose_claimed_user_id(async_client):
    client, manager = async_client
    legacy_id = manager.create_session(user_id="legacy-claimed-user")

    response = await client.get(f"/info/{legacy_id}")

    assert response.status_code == 200
    assert response.json()["user_id"] is None


@pytest.mark.asyncio
async def test_legacy_session_id_validation_does_not_bypass_verified_owner(
    async_client, monkeypatch
):
    from auth_service import User

    client, manager = async_client
    session_id = manager.create_session(
        user_id="user-b", authenticated_principal_id="user-b"
    )
    install_test_principal(
        monkeypatch,
        User(sub="user-a", email="a@example.test", name="A"),
    )

    response = await client.get(f"/validate/{session_id}")

    assert response.status_code == 403
    assert manager.sessions[session_id].user_id == "user-b"
