import json
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import statblockgenerator_router
from statblockgenerator.models.statblock_models import StatBlockDetails

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "Docs/Design/fixtures/statblockgenerator-command-board-contract"
FIXTURE_PATHS = sorted(FIXTURE_DIR.glob("*.json"))
assert FIXTURE_PATHS, f"No command-board contract fixtures found in {FIXTURE_DIR}"


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


def client():
    app = FastAPI()
    app.include_router(statblockgenerator_router.router)
    return TestClient(app)


def test_v2_health_returns_contract_payload():
    response = client().get("/api/statblockgenerator/v2/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "statblockgenerator"
    assert data["contract"] == "command_board_draft_v2"
    assert data["version"] == "0.1.0"
    assert data["supports"] == ["generate-draft", "render-draft"]


def test_generate_draft_accepts_basic_fixture(monkeypatch):
    payload = json.loads((FIXTURE_DIR / "generate_from_prompt.basic.json").read_text())
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

    response = client().post("/api/statblockgenerator/v2/generate-draft", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["draft"]["lifecycle_state"] == "live_draft"
    assert data["draft"]["markdown"]
    assert data["draft"]["combat_defaults"]["name"] == "Bog Knife Outrider"
    assert "warnings" in data["draft"]
    assert data["draft"]["provenance"]["request_id"] == "db-cmd-basic-001"
    assert data["draft"]["provenance"]["persist_requested"] is False
    mock_generate.assert_awaited_once()


def test_render_draft_wraps_existing_statblock_without_generation(monkeypatch):
    mock_generate = AsyncMock()
    monkeypatch.setattr(statblockgenerator_router.statblock_generator, "generate_creature", mock_generate)
    payload = {
        "request_id": "db-cmd-render-001",
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

    response = client().post("/api/statblockgenerator/v2/render-draft", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["draft"]["draft_id"] == "draft-db-cmd-render-001"
    assert data["draft"]["markdown"].startswith("# Bog Knife Outrider")
    assert data["draft"]["combat_defaults"]["armor_class"] == 14
    assert data["draft"]["combat_defaults"]["hit_points"] == 27
    assert data["draft"]["provenance"]["mode"] == "render_existing"
    assert data["draft"]["provenance"]["generator"] == "statblock_draft_adapter.render_existing"
    assert data["draft"]["provenance"]["generator"] != "StatBlockGenerator.generate_creature"
    assert data["draft"]["provenance"]["generation_info"] == {
        "source": "render-draft",
        "generated": False,
    }
    assert data["draft"]["provenance"]["source_refs"][0]["id"] == "combatant:bog-knife-outrider"
    mock_generate.assert_not_awaited()


def test_generate_draft_failure_returns_stable_error_envelope(monkeypatch):
    payload = json.loads((FIXTURE_DIR / "generate_from_prompt.basic.json").read_text())
    mock_generate = AsyncMock(return_value=(False, {"error": "OpenAI client not initialized"}))
    monkeypatch.setattr(statblockgenerator_router.statblock_generator, "generate_creature", mock_generate)

    response = client().post("/api/statblockgenerator/v2/generate-draft", json=payload)

    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert data["draft"] is None
    assert data["error"]["code"] == "generation_failed"
    assert data["error"]["message"] == "OpenAI client not initialized"


def test_generate_draft_returns_501_for_accepted_unimplemented_modes():
    payload = json.loads((FIXTURE_DIR / "generate_from_source_statblock.tripod_variant.json").read_text())

    response = client().post("/api/statblockgenerator/v2/generate-draft", json=payload)

    assert response.status_code == 501
    data = response.json()
    assert data["success"] is False
    assert data["draft"] is None
    assert data["error"]["code"] == "not_implemented"
    assert data["error"]["details"]["mode"] == "generate_from_source_statblock"
