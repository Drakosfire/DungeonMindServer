from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from models.session_models import RulesLawyerSessionState
from session_management import EnhancedGlobalSessionManager


@pytest.fixture
def session_api(monkeypatch):
    from unittest.mock import MagicMock

    import firestore.firebase_config as firebase_config

    monkeypatch.setattr(
        firebase_config,
        "db",
        MagicMock(name="session_contract_firestore_stub"),
    )
    import routers.global_session_router as global_session_router

    manager = EnhancedGlobalSessionManager(session_timeout_hours=1)
    monkeypatch.setattr(global_session_router, "session_manager", manager)
    api = FastAPI()
    api.include_router(global_session_router.router)
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
    assert payload["session"]["preferences"]["theme"] == "dark"
    assert payload["session"]["preferences"]["language"] == "fr"
    assert response.cookies["dungeonmind_session_id"] == session_id
    assert manager.sessions[session_id].user_agent == "private-agent-marker"
    assert manager.sessions[session_id].ip_address is not None
    assert len(manager.sessions) == 1


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
