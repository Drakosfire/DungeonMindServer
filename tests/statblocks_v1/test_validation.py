from __future__ import annotations

import pytest

from statblocks_v1.domain import (
    StatblockDefinitionV1,
    ValidationMode,
    ValidationSeverity,
    validate_definition,
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


@pytest.mark.parametrize("name", VALID_FIXTURES)
def test_valid_fixtures_are_persistence_ready(load_fixture, name: str) -> None:
    definition = StatblockDefinitionV1.model_validate(load_fixture(name))

    receipt = validate_definition(definition, ValidationMode.persistence)

    assert receipt.is_persistence_ready


@pytest.mark.parametrize(
    ("fixture", "expected_code"),
    (
        ("duplicate_rule_element_key", "DUPLICATE_LOCAL_KEY"),
        ("dangling_multiattack_ref", "UNKNOWN_MULTIATTACK_ELEMENT"),
        ("phase_unknown_element", "UNKNOWN_PHASE_ELEMENT"),
        ("unknown_resource_pool", "UNKNOWN_RESOURCE_REFERENCE"),
        ("section_activation_contradiction", "SECTION_ACTIVATION_INCOHERENT"),
        ("multiple_default_armor_class", "DEFAULT_ARMOR_CLASS_CARDINALITY"),
    ),
)
def test_cross_reference_fixtures_emit_stable_codes(
    load_fixture, fixture: str, expected_code: str
) -> None:
    receipt = validate_definition(
        StatblockDefinitionV1.model_validate(load_fixture(fixture)),
        ValidationMode.persistence,
    )

    assert expected_code in {issue.code for issue in receipt.issues}
    assert receipt.status.value == "invalid"


def test_human_adjudicated_requires_manual_automation(load_fixture) -> None:
    payload = load_fixture("human_adjudicated")
    payload["rule_elements"][0]["automation_support"] = "full"

    receipt = validate_definition(
        StatblockDefinitionV1.model_validate(payload), ValidationMode.persistence
    )

    assert "HUMAN_ADJUDICATED_AUTOMATION_MISMATCH" in {
        issue.code for issue in receipt.issues
    }


def test_high_confidence_rules_text_conflict_blocks_only_persistence(load_fixture) -> None:
    payload = load_fixture("simple_bruiser")
    payload["rule_elements"][0]["rules_text"] = (
        "Melee Weapon Attack: +4 to hit. Hit: 2d8 + 4 bludgeoning damage."
    )
    definition = StatblockDefinitionV1.model_validate(payload)

    candidate = validate_definition(definition, ValidationMode.generation_candidate)
    persistence = validate_definition(definition, ValidationMode.persistence)

    candidate_issue = next(
        issue for issue in candidate.issues if issue.code == "RULES_TEXT_ATTACK_BONUS_MISMATCH"
    )
    persistence_issue = next(
        issue for issue in persistence.issues if issue.code == "RULES_TEXT_ATTACK_BONUS_MISMATCH"
    )
    assert candidate_issue.severity is ValidationSeverity.warning
    assert persistence_issue.severity is ValidationSeverity.error
