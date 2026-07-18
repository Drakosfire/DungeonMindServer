from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from statblocks_v1.domain import StatblockDefinitionV1

FIXTURE_DIRECTORY = (
    Path(__file__).parents[2]
    / "Docs"
    / "Design"
    / "fixtures"
    / "dungeonbuddy-statblock-v1"
)
VALID_FIXTURES = (
    "simple_bruiser",
    "spellcaster",
    "innate_spellcaster",
    "legendary_creature",
    "lair_creature",
    "unusual_movement",
    "mythic_phase",
    "human_adjudicated",
)
STRUCTURALLY_INVALID_FIXTURES = ("formula_hp_missing_formula", "unknown_ruleset")
CROSS_REFERENCE_FIXTURES = (
    "duplicate_rule_element_key",
    "dangling_multiattack_ref",
    "phase_unknown_element",
    "unknown_resource_pool",
    "section_activation_contradiction",
    "multiple_default_armor_class",
)


def _payload(name: str) -> dict:
    return json.loads((FIXTURE_DIRECTORY / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", VALID_FIXTURES)
def test_valid_fixture_parses_and_round_trips(name: str) -> None:
    definition = StatblockDefinitionV1.model_validate(_payload(name))

    assert (
        StatblockDefinitionV1.model_validate(definition.model_dump(mode="json"))
        == definition
    )


@pytest.mark.parametrize("name", STRUCTURALLY_INVALID_FIXTURES)
def test_structural_invalid_fixtures_fail_immediately(name: str) -> None:
    with pytest.raises(ValidationError):
        StatblockDefinitionV1.model_validate(_payload(name))


@pytest.mark.parametrize("name", CROSS_REFERENCE_FIXTURES)
def test_cross_reference_fixtures_are_reserved_for_pr14(name: str) -> None:
    """PR13 stores examples; semantic validation intentionally arrives in PR14."""
    assert StatblockDefinitionV1.model_validate(_payload(name))
