import json
from pathlib import Path

from statblockgenerator.models.command_board_contract_models import StatBlockDraftRequest
from statblockgenerator.models.statblock_models import StatBlockDetails
from statblockgenerator.services.statblock_draft_adapter import (
    build_draft,
    build_generation_request,
    build_warnings,
    derive_combat_defaults,
    render_markdown,
)

FIXTURE_DIR = Path("Docs/Design/fixtures/statblockgenerator-command-board-contract")


def sample_statblock(**overrides):
    data = {
        "name": "Bog Knife Outrider",
        "size": "Small",
        "type": "humanoid",
        "alignment": "neutral evil",
        "armorClass": 14,
        "hitPoints": 27,
        "hitDice": "6d6+6",
        "speed": {"walk": 30, "swim": 20},
        "abilities": {"str": 8, "dex": 16, "con": 12, "int": 10, "wis": 12, "cha": 8},
        "skills": {"Stealth": 5, "Perception": 3},
        "conditionImmunity": "",
        "senses": {"darkvision": 60, "passive_perception": 13},
        "languages": "Common, Goblin",
        "challengeRating": "1",
        "xp": 200,
        "proficiencyBonus": 2,
        "specialAbilities": [
            {"name": "Reed Camouflage", "desc": "The outrider has advantage on Dexterity (Stealth) checks in reeds."}
        ],
        "actions": [
            {
                "name": "Bog Knife",
                "desc": "Melee Weapon Attack: +5 to hit, reach 5 ft., one target. Hit: 6 piercing damage.",
                "attack_bonus": 5,
                "damage": "1d6+3",
                "damage_type": "piercing",
            },
            {
                "name": "Mud Snare",
                "desc": "One creature in mud must succeed on a DC 13 Strength saving throw or be restrained until the end of its next turn.",
            },
        ],
        "description": "A reed-cloaked ambusher that fights from shallow water and sucking mud.",
        "sdPrompt": "A reed cloaked goblin in a swamp",
    }
    data.update(overrides)
    return StatBlockDetails.model_validate(data)


def sample_request():
    payload = json.loads((FIXTURE_DIR / "generate_from_prompt.basic.json").read_text())
    return StatBlockDraftRequest.model_validate(payload)


def test_generation_request_composes_transparent_description():
    request = sample_request()

    generation_request = build_generation_request(request)

    assert generation_request.challenge_rating_target == "1"
    assert "Intent: Create a low-complexity swamp ambusher" in generation_request.description
    assert "Target CR: 1" in generation_request.description
    assert "Terrain features: shallow water, reeds, difficult terrain" in generation_request.description


def test_markdown_contains_core_statblock_sections():
    markdown = render_markdown(sample_statblock())

    assert "# Bog Knife Outrider" in markdown
    assert "**Armor Class** 14" in markdown
    assert "**Hit Points** 27" in markdown
    assert "**Speed** 30 ft., swim 20 ft." in markdown
    assert "**Challenge** 1" in markdown
    assert "## Actions" in markdown
    assert "**Bog Knife.**" in markdown


def test_combat_defaults_are_deterministic_from_statblock():
    defaults = derive_combat_defaults(sample_statblock())

    assert defaults.name == "Bog Knife Outrider"
    assert defaults.armor_class == 14
    assert defaults.hit_points == 27
    assert defaults.initiative_bonus == 3
    assert defaults.passive_perception == 13
    assert defaults.speed_summary == "30 ft., swim 20 ft."
    assert defaults.primary_actions == ["Bog Knife", "Mud Snare"]
    assert defaults.save_dcs == [13]
    assert defaults.senses_summary == "darkvision 60 ft., passive Perception 13"


def test_warnings_include_cr_mismatch():
    statblock = sample_statblock(challengeRating="2")

    warnings = build_warnings(sample_request(), statblock, render_markdown(statblock))

    assert any(warning.code == "cr_mismatch" for warning in warnings)


def test_warnings_include_terrain_assumption_when_terrain_is_ignored():
    statblock = sample_statblock(
        actions=[{"name": "Knife", "desc": "Melee Weapon Attack: +5 to hit. Hit: 6 piercing damage."}],
        specialAbilities=[],
        description="A plain ambusher with no environmental text.",
    )

    warnings = build_warnings(sample_request(), statblock, render_markdown(statblock))

    assert any(warning.code == "terrain_assumption" for warning in warnings)


def test_build_draft_includes_lifecycle_provenance_and_review_status():
    request = sample_request()

    draft = build_draft(request, sample_statblock().model_dump(by_alias=True), {"model_used": "mock"})

    assert draft.draft_id == "draft-db-cmd-basic-001"
    assert draft.lifecycle_state == "live_draft"
    assert draft.markdown
    assert draft.combat_defaults.name == "Bog Knife Outrider"
    assert draft.provenance.request_id == request.request_id
    assert draft.provenance.persist_requested is False
    assert draft.provenance.generation_info["model_used"] == "mock"
