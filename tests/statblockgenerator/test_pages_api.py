"""Integration tests for the statblock pages API."""

from typing import Dict

import pytest
from fastapi.testclient import TestClient

from app import app
from session_management import get_authenticated_session
from models.dungeonmind_objects import (
    PageDocument,
    Visibility
)
from database.dungeonmind_objects_db import PermissionError

from tests.support.statblock_test_utils import (
    FakeStatblockDB,
    apply_statblock_env,
    ensure_service_account_file,
    patch_dungeonmind_db,
    reset_statblock_env,
)


def override_auth_dependency():
    class DummySession:
        user_id = "test-user"
        active_world_id = "world-001"
        active_project_id = "project-001"

        def add_to_recently_viewed(self, _object_id: str) -> None:
            return None

    return DummySession(), "session-id"


@pytest.fixture(autouse=True)
def configure_test_environment(monkeypatch):
    ensure_service_account_file()
    apply_statblock_env(monkeypatch)
    fake_db = FakeStatblockDB()
    patch_dungeonmind_db(monkeypatch, fake_db)
    app.dependency_overrides[get_authenticated_session] = override_auth_dependency
    yield fake_db
    fake_db.reset_behaviour()
    app.dependency_overrides.clear()
    reset_statblock_env(monkeypatch)


@pytest.fixture
def client(configure_test_environment):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def fake_statblock_db(configure_test_environment):
    return configure_test_environment


def _base_page_document() -> Dict[str, object]:
    return {
        "id": "page-123",
        "templateId": "template-xyz",
        "pageVariables": {"mode": "locked"},
        "componentInstances": [
            {
                "id": "component-1",
                "type": "identity-header",
                "dataRef": {"type": "statblock", "path": "name"},
                "layout": {"isVisible": True}
            }
        ],
        "dataSources": [
            {
                "id": "source-1",
                "type": "statblock",
                "payload": {"name": "Dustwalker"},
                "updatedAt": "2025-09-27T00:00:00Z"
            }
        ]
    }


def test_statblock_page_crud_flow(client):
    create_payload = {
        "name": "Dustwalker Demo",
        "description": "Initial statblock page",
        "tags": ["demo", "statblock"],
        "visibility": Visibility.PRIVATE.value,
        "page": _base_page_document(),
        "statblockDetails": {"creatureType": "humanoid", "armorClass": 15},
        "metadata": {"projectId": "project-777", "worldId": "world-555"}
    }

    create_response = client.post("/api/statblock-pages/", json=create_payload)
    assert create_response.status_code == 200
    created = create_response.json()
    page_id = created["objectId"]
    assert isinstance(page_id, str) and page_id
    assert created["projectId"] == "project-777"
    assert created["worldId"] == "world-555"

    fetch_response = client.get(f"/api/statblock-pages/{page_id}")
    assert fetch_response.status_code == 200
    fetched = fetch_response.json()
    assert fetched["objectId"] == page_id
    assert fetched["page"]["templateId"] == "template-xyz"

    updated_page = _base_page_document()
    updated_page["templateId"] = "template-updated"
    updated_page["metadata"] = {"note": "updated"}

    update_payload = {
        "name": "Dustwalker Updated",
        "page": updated_page,
        "statblockDetails": {"creatureType": "fey", "armorClass": 16}
    }

    update_response = client.put(f"/api/statblock-pages/{page_id}", json=update_payload)
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "Dustwalker Updated"
    assert updated["page"]["templateId"] == "template-updated"
    assert updated["statblockDetails"]["creatureType"] == "fey"

    # Ensure subsequent GET returns updated content
    refetch_response = client.get(f"/api/statblock-pages/{page_id}")
    assert refetch_response.status_code == 200
    refetched = refetch_response.json()
    assert refetched["name"] == "Dustwalker Updated"
    assert refetched["page"]["templateId"] == "template-updated"


def test_update_allows_clearing_optional_fields(client):
    create_payload = {
        "name": "Dustwalker Demo",
        "description": "Initial statblock page",
        "tags": ["demo", "statblock"],
        "visibility": Visibility.PRIVATE.value,
        "page": _base_page_document(),
        "statblockDetails": {"creatureType": "humanoid", "armorClass": 15},
        "metadata": {"projectId": "project-777", "worldId": "world-555"}
    }

    create_response = client.post("/api/statblock-pages/", json=create_payload)
    create_body = create_response.json()
    page_id = create_body["objectId"]
    original_page = create_body["page"]

    update_payload = {
        "tags": [],
        "statblockDetails": {},
        "page": None
    }

    update_response = client.put(f"/api/statblock-pages/{page_id}", json=update_payload)
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["tags"] == []
    assert updated["statblockDetails"] == {}
    assert updated["page"]["templateId"] == original_page["templateId"]
    assert updated["page"]["dataSources"] == original_page["dataSources"]


def test_visibility_update_and_public_fetch(client):
    create_payload = {
        "name": "Dustwalker Demo",
        "description": "Initial statblock page",
        "tags": ["demo", "statblock"],
        "visibility": Visibility.PRIVATE.value,
        "page": _base_page_document(),
        "statblockDetails": {"creatureType": "humanoid", "armorClass": 15},
        "metadata": {"projectId": "project-777", "worldId": "world-555"}
    }

    create_response = client.post("/api/statblock-pages/", json=create_payload)
    page_id = create_response.json()["objectId"]

    update_payload = {
        "visibility": Visibility.PUBLIC.value
    }

    update_response = client.put(f"/api/statblock-pages/{page_id}", json=update_payload)
    assert update_response.status_code == 200
    assert update_response.json()["visibility"] == Visibility.PUBLIC.value

    fetch_response = client.get(f"/api/statblock-pages/{page_id}")
    assert fetch_response.status_code == 200


def test_permission_denied_on_fetch(client, fake_statblock_db):
    create_payload = {
        "name": "Dustwalker Demo",
        "description": "Initial statblock page",
        "tags": ["demo", "statblock"],
        "visibility": Visibility.PRIVATE.value,
        "page": _base_page_document(),
        "statblockDetails": {"creatureType": "humanoid", "armorClass": 15},
        "metadata": {"projectId": "project-777", "worldId": "world-555"}
    }

    create_response = client.post("/api/statblock-pages/", json=create_payload)
    page_id = create_response.json()["objectId"]

    async def deny_get(page_id: str, user_id: str):  # pylint: disable=unused-argument
        raise PermissionError("Access denied")

    fake_statblock_db.with_behaviour(get=deny_get)

    fetch_response = client.get(f"/api/statblock-pages/{page_id}")
    assert fetch_response.status_code == 403
