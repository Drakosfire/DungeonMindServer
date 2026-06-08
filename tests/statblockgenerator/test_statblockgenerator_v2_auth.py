import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from routers import statblockgenerator_router
from routers.internal_auth import (
    INTERNAL_KEY_ENV,
    INTERNAL_KEY_HEADER,
    require_dungeonbuddy_internal_key,
)
from statblockgenerator.models.statblock_models import StatBlockDetails

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "Docs/Design/fixtures/statblockgenerator-command-board-contract"
TEST_INTERNAL_KEY = "test-internal-key"


def client():
    app = FastAPI()
    app.include_router(statblockgenerator_router.router)
    return TestClient(app)


def auth_headers(key: str = TEST_INTERNAL_KEY):
    return {INTERNAL_KEY_HEADER: key}


def generate_payload():
    return json.loads((FIXTURE_DIR / "generate_from_prompt.basic.json").read_text())


def sample_statblock():
    return StatBlockDetails.model_validate({
        "name": "Bog Knife Outrider",
        "size": "Small",
        "type": "humanoid",
        "alignment": "neutral evil",
        "armorClass": 14,
        "hitPoints": 27,
        "hitDice": "6d6+6",
        "speed": {"walk": 30, "swim": 20},
        "abilities": {"str": 8, "dex": 16, "con": 12, "int": 10, "wis": 12, "cha": 8},
        "senses": {"darkvision": 60, "passive_perception": 13},
        "languages": "Common, Goblin",
        "challengeRating": "1",
        "xp": 200,
        "proficiencyBonus": 2,
        "actions": [
            {
                "name": "Bog Knife",
                "desc": "Melee Weapon Attack: +5 to hit, reach 5 ft., one target. Hit: 6 piercing damage.",
                "attack_bonus": 5,
                "damage": "1d6+3",
                "damage_type": "piercing",
            }
        ],
        "description": "A reed-cloaked ambusher that fights from shallow water and sucking mud.",
        "sdPrompt": "A reed cloaked goblin in a swamp",
    })


def render_payload():
    return {
        "request_id": "db-cmd-render-auth-001",
        "statblock": sample_statblock().model_dump(by_alias=True),
        "source_refs": [
            {
                "id": "combatant:bog-knife-outrider",
                "kind": "combatant",
                "label": "Bog Knife Outrider",
            }
        ],
        "output_options": {
            "include_markdown": True,
            "include_combat_defaults": True,
            "include_review_warnings": True,
            "persist": False,
        },
    }


def test_v2_health_missing_header_denied(monkeypatch):
    monkeypatch.setenv(INTERNAL_KEY_ENV, TEST_INTERNAL_KEY)

    response = client().get("/api/statblockgenerator/v2/health")

    assert response.status_code == 401
    assert response.json() == {"detail": "Missing internal API key"}


def test_v2_health_wrong_header_denied(monkeypatch):
    monkeypatch.setenv(INTERNAL_KEY_ENV, TEST_INTERNAL_KEY)

    response = client().get(
        "/api/statblockgenerator/v2/health",
        headers=auth_headers("wrong-key"),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid internal API key"}


def test_v2_health_correct_header_accepted(monkeypatch):
    monkeypatch.setenv(INTERNAL_KEY_ENV, TEST_INTERNAL_KEY)

    response = client().get("/api/statblockgenerator/v2/health", headers=auth_headers())

    assert response.status_code == 200
    assert response.json()["contract"] == "command_board_draft_v2"


def test_v2_health_missing_server_env_fails_closed(monkeypatch):
    monkeypatch.delenv(INTERNAL_KEY_ENV, raising=False)

    response = client().get("/api/statblockgenerator/v2/health", headers=auth_headers())

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal API key is not configured"}


def test_generate_draft_missing_header_does_not_call_generation(monkeypatch):
    monkeypatch.setenv(INTERNAL_KEY_ENV, TEST_INTERNAL_KEY)
    mock_generate = AsyncMock()
    monkeypatch.setattr(statblockgenerator_router.statblock_generator, "generate_creature", mock_generate)

    response = client().post("/api/statblockgenerator/v2/generate-draft", json=generate_payload())

    assert response.status_code == 401
    mock_generate.assert_not_awaited()


def test_generate_draft_wrong_header_does_not_call_generation(monkeypatch):
    monkeypatch.setenv(INTERNAL_KEY_ENV, TEST_INTERNAL_KEY)
    mock_generate = AsyncMock()
    monkeypatch.setattr(statblockgenerator_router.statblock_generator, "generate_creature", mock_generate)

    response = client().post(
        "/api/statblockgenerator/v2/generate-draft",
        json=generate_payload(),
        headers=auth_headers("wrong-key"),
    )

    assert response.status_code == 403
    mock_generate.assert_not_awaited()


def test_generate_draft_correct_header_reaches_generation(monkeypatch):
    monkeypatch.setenv(INTERNAL_KEY_ENV, TEST_INTERNAL_KEY)
    mock_generate = AsyncMock(
        return_value=(
            True,
            {
                "statblock": sample_statblock().model_dump(by_alias=True),
                "generation_info": {"model_used": "mock-model"},
            },
        )
    )
    monkeypatch.setattr(statblockgenerator_router.statblock_generator, "generate_creature", mock_generate)

    response = client().post(
        "/api/statblockgenerator/v2/generate-draft",
        json=generate_payload(),
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    mock_generate.assert_awaited_once()


def test_render_draft_missing_header_does_not_render(monkeypatch):
    monkeypatch.setenv(INTERNAL_KEY_ENV, TEST_INTERNAL_KEY)
    mock_build_draft = Mock()
    monkeypatch.setattr(statblockgenerator_router, "build_draft", mock_build_draft)

    response = client().post("/api/statblockgenerator/v2/render-draft", json=render_payload())

    assert response.status_code == 401
    assert "draft" not in response.json()
    mock_build_draft.assert_not_called()


def test_render_draft_wrong_header_does_not_render(monkeypatch):
    monkeypatch.setenv(INTERNAL_KEY_ENV, TEST_INTERNAL_KEY)
    mock_build_draft = Mock()
    monkeypatch.setattr(statblockgenerator_router, "build_draft", mock_build_draft)

    response = client().post(
        "/api/statblockgenerator/v2/render-draft",
        json=render_payload(),
        headers=auth_headers("wrong-key"),
    )

    assert response.status_code == 403
    assert "draft" not in response.json()
    mock_build_draft.assert_not_called()


def test_render_draft_correct_header_reaches_rendering(monkeypatch):
    monkeypatch.setenv(INTERNAL_KEY_ENV, TEST_INTERNAL_KEY)

    response = client().post(
        "/api/statblockgenerator/v2/render-draft",
        json=render_payload(),
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["draft"]["draft_id"] == "draft-db-cmd-render-auth-001"


def test_legacy_generate_statblock_route_does_not_require_internal_key():
    route = next(
        route
        for route in statblockgenerator_router.router.routes
        if isinstance(route, APIRoute)
        and route.path == "/api/statblockgenerator/generate-statblock"
        and "POST" in route.methods
    )

    dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
    assert require_dungeonbuddy_internal_key not in dependency_calls
