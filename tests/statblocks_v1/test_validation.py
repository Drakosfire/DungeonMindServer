from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from statblocks_v1.domain import (
    StatblockDefinitionV1,
    ValidationMode,
    ValidationSeverity,
    validate_definition,
)
from statblocks_v1.domain.primitives import (
    Distance,
    DistanceUnit,
    RangeProfile,
    TargetKind,
    TargetProfile,
)
from statblocks_v1.domain.rule_elements import AttackMechanic, AttackType


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
    assert receipt.mode is ValidationMode.persistence


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
    assert receipt.is_persistence_ready is False


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
    assert candidate.is_persistence_ready is False
    assert persistence.is_persistence_ready is False


def test_candidate_receipt_never_claims_persistence_readiness(load_fixture) -> None:
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))

    candidate = validate_definition(definition, ValidationMode.generation_candidate)
    preview = validate_definition(definition, ValidationMode.editor_preview)

    assert candidate.status.value == "valid"
    assert candidate.is_persistence_ready is False
    assert preview.is_persistence_ready is False


def test_repeated_validation_matches_except_supplied_time(load_fixture) -> None:
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    first_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    second_time = datetime(2026, 1, 2, tzinfo=timezone.utc)

    first = validate_definition(
        definition, ValidationMode.persistence, validated_at=first_time
    )
    second = validate_definition(
        definition, ValidationMode.persistence, validated_at=second_time
    )

    assert first.model_dump(exclude={"validated_at"}) == second.model_dump(
        exclude={"validated_at"}
    )
    assert first.validated_at == first_time
    assert second.validated_at == second_time


def test_passive_perception_checks_perception_skill_value(load_fixture) -> None:
    payload = load_fixture("simple_bruiser")
    # Wisdom 10 (mod 0) + PB 2 => standard Perception 2; passive must be 12.
    payload["proficiencies"]["skills"] = [
        {
            "skill": "Perception",
            "ability": "wisdom",
            "value": 2,
            "derivation": "standard",
            "note": None,
        }
    ]
    payload["senses"]["passive_perception"] = 10

    receipt = validate_definition(
        StatblockDefinitionV1.model_validate(payload), ValidationMode.persistence
    )

    issue = next(item for item in receipt.issues if item.code == "PASSIVE_PERCEPTION_MISMATCH")
    assert issue.field_path == "senses.passive_perception"
    assert issue.severity is ValidationSeverity.error
    assert "SKILL_DERIVATION_MISMATCH" not in {item.code for item in receipt.issues}


def test_standard_saving_throw_derivation_must_match_ability_and_pb(load_fixture) -> None:
    payload = load_fixture("simple_bruiser")
    # Strength 18 (mod +4) + PB 2 => expected standard save +6.
    payload["proficiencies"]["saving_throws"] = [
        {
            "ability": "strength",
            "value": 2,
            "derivation": "standard",
            "note": None,
        }
    ]

    receipt = validate_definition(
        StatblockDefinitionV1.model_validate(payload), ValidationMode.persistence
    )

    issue = next(
        item for item in receipt.issues if item.code == "SAVING_THROW_DERIVATION_MISMATCH"
    )
    assert issue.field_path == "proficiencies.saving_throws[0].value"
    assert receipt.is_persistence_ready is False


def test_expertise_skill_derivation_and_explicit_override(load_fixture) -> None:
    payload = load_fixture("simple_bruiser")
    # Dexterity 10 (mod 0) + 2×PB => expertise Stealth 4.
    payload["proficiencies"]["skills"] = [
        {
            "skill": "Stealth",
            "ability": "dexterity",
            "value": 3,
            "derivation": "expertise",
            "note": None,
        },
        {
            "skill": "Athletics",
            "ability": "strength",
            "value": 9,
            "derivation": "explicit_override",
            "note": "magical boots",
        },
    ]

    receipt = validate_definition(
        StatblockDefinitionV1.model_validate(payload), ValidationMode.persistence
    )

    codes = {item.code for item in receipt.issues}
    assert "SKILL_DERIVATION_MISMATCH" in codes
    expertise = next(
        item for item in receipt.issues if item.code == "SKILL_DERIVATION_MISMATCH"
    )
    assert expertise.field_path == "proficiencies.skills[0].value"
    assert "SAVING_THROW_DERIVATION_MISMATCH" not in codes
    assert receipt.is_persistence_ready is False

    payload["proficiencies"]["skills"][0]["value"] = 4
    fixed = validate_definition(
        StatblockDefinitionV1.model_validate(payload), ValidationMode.persistence
    )
    assert "SKILL_DERIVATION_MISMATCH" not in {item.code for item in fixed.issues}
    assert fixed.is_persistence_ready


def test_duplicate_saving_throw_and_normalized_skill_rejected(load_fixture) -> None:
    payload = load_fixture("simple_bruiser")
    payload["proficiencies"]["saving_throws"] = [
        {
            "ability": "constitution",
            "value": 5,
            "derivation": "standard",
            "note": None,
        },
        {
            "ability": "constitution",
            "value": 5,
            "derivation": "standard",
            "note": None,
        },
    ]
    payload["proficiencies"]["skills"] = [
        {
            "skill": "Perception",
            "ability": "wisdom",
            "value": 2,
            "derivation": "standard",
            "note": None,
        },
        {
            "skill": "perception",
            "ability": "wisdom",
            "value": 2,
            "derivation": "standard",
            "note": None,
        },
    ]
    payload["senses"]["passive_perception"] = 12

    receipt = validate_definition(
        StatblockDefinitionV1.model_validate(payload), ValidationMode.persistence
    )

    by_code = {item.code: item for item in receipt.issues}
    assert by_code["DUPLICATE_SAVING_THROW_ABILITY"].field_path == (
        "proficiencies.saving_throws[1].ability"
    )
    assert by_code["DUPLICATE_SKILL_NAME"].field_path == "proficiencies.skills[1].skill"
    assert receipt.is_persistence_ready is False
    assert "PASSIVE_PERCEPTION_MISMATCH" not in by_code


def test_recharge_usage_requires_typed_range_object(load_fixture) -> None:
    payload = load_fixture("simple_bruiser")
    payload["rule_elements"][0]["usage"] = {
        "kind": "recharge",
        "recharge_range": None,
        "uses": None,
        "resource_key": None,
        "refresh_text": None,
    }

    receipt = validate_definition(
        StatblockDefinitionV1.model_validate(payload), ValidationMode.persistence
    )

    assert "USAGE_FIELDS_INCOHERENT" in {issue.code for issue in receipt.issues}


def test_innate_spell_group_rejects_slots(load_fixture) -> None:
    payload = load_fixture("innate_spellcaster")
    payload["rule_elements"][0]["mechanic"]["groups"][1]["slots"] = 3
    payload["rule_elements"][0]["mechanic"]["groups"][1]["usage"]["uses"] = 3

    receipt = validate_definition(
        StatblockDefinitionV1.model_validate(payload), ValidationMode.persistence
    )

    assert "SPELL_GROUP_SLOTS_INCOHERENT" in {issue.code for issue in receipt.issues}


def test_nested_effect_reference_uses_real_collection_path(load_fixture) -> None:
    payload = load_fixture("simple_bruiser")
    existing_hits = len(payload["rule_elements"][0]["mechanic"]["hit_effects"])
    payload["rule_elements"][0]["mechanic"]["hit_effects"].append(
        {
            "kind": "enable_elements",
            "element_keys": ["missing_element"],
        }
    )

    receipt = validate_definition(
        StatblockDefinitionV1.model_validate(payload), ValidationMode.persistence
    )

    paths = {
        issue.field_path
        for issue in receipt.issues
        if issue.code == "UNKNOWN_ELEMENT_REFERENCE"
    }
    expected = f"rule_elements[0].mechanic.hit_effects[{existing_hits}].element_keys[0]"
    assert expected in paths
    assert not any(".mechanic.effects[" in path for path in paths)


def test_attack_target_count_and_area_coherence(load_fixture) -> None:
    payload = load_fixture("simple_bruiser")
    payload["rule_elements"][0]["mechanic"]["target"] = {
        "kind": "creatures",
        "count": None,
        "range": None,
        "area": "10-foot radius",
        "qualifiers": [],
    }

    receipt = validate_definition(
        StatblockDefinitionV1.model_validate(payload), ValidationMode.persistence
    )
    codes = {issue.code for issue in receipt.issues}
    assert "ATTACK_TARGET_COUNT_REQUIRED" in codes
    assert "ATTACK_TARGET_AREA_UNEXPECTED" in codes


def test_prepared_spell_group_requires_slots_and_spell_slots_usage(load_fixture) -> None:
    payload = deepcopy(load_fixture("spellcaster"))
    payload["rule_elements"][0]["mechanic"]["groups"][1]["slots"] = None
    payload["rule_elements"][0]["mechanic"]["groups"][1]["usage"]["kind"] = "at_will"
    payload["rule_elements"][0]["mechanic"]["groups"][1]["usage"]["uses"] = None
    payload["rule_elements"][0]["mechanic"]["groups"][1]["usage"]["refresh_text"] = None

    receipt = validate_definition(
        StatblockDefinitionV1.model_validate(payload), ValidationMode.persistence
    )
    codes = {issue.code for issue in receipt.issues}
    assert "SPELL_GROUP_SLOTS_INCOHERENT" in codes
    assert "SPELL_GROUP_USAGE_INCOHERENT" in codes


def test_spell_group_resource_key_must_resolve(load_fixture) -> None:
    payload = load_fixture("innate_spellcaster")
    payload["rule_elements"][0]["mechanic"]["casting_mode"] = "charges"
    payload["rule_elements"][0]["mechanic"]["caster_level"] = None
    payload["rule_elements"][0]["mechanic"]["groups"] = [
        {
            "usage": {
                "kind": "resource",
                "recharge_range": None,
                "uses": None,
                "resource_key": "missing_charge_pool",
                "refresh_text": None,
            },
            "level": 1,
            "slots": None,
            "spells": [
                {
                    "name": "magic missile",
                    "school": None,
                    "source_id": None,
                    "rules_text": None,
                }
            ],
        }
    ]

    receipt = validate_definition(
        StatblockDefinitionV1.model_validate(payload), ValidationMode.persistence
    )
    issue = next(
        item for item in receipt.issues if item.code == "UNKNOWN_RESOURCE_REFERENCE"
    )
    assert issue.field_path == (
        "rule_elements[0].mechanic.groups[0].usage.resource_key"
    )


def test_attack_target_range_is_rejected(load_fixture) -> None:
    payload = load_fixture("simple_bruiser")
    payload["rule_elements"][0]["mechanic"]["target"]["range"] = {
        "normal": {"value": 5, "unit": "feet"},
        "long": None,
    }

    receipt = validate_definition(
        StatblockDefinitionV1.model_validate(payload), ValidationMode.persistence
    )
    assert "ATTACK_TARGET_RANGE_UNEXPECTED" in {issue.code for issue in receipt.issues}


def test_spell_slots_usage_forbidden_outside_leveled_prepared_known(load_fixture) -> None:
    payload = load_fixture("simple_bruiser")
    payload["rule_elements"][0]["usage"]["kind"] = "spell_slots"

    element_receipt = validate_definition(
        StatblockDefinitionV1.model_validate(payload), ValidationMode.persistence
    )
    assert "USAGE_FIELDS_INCOHERENT" in {issue.code for issue in element_receipt.issues}

    innate = load_fixture("innate_spellcaster")
    innate["rule_elements"][0]["mechanic"]["groups"][1]["usage"]["kind"] = "spell_slots"
    innate["rule_elements"][0]["mechanic"]["groups"][1]["usage"]["uses"] = None
    innate["rule_elements"][0]["mechanic"]["groups"][1]["slots"] = 3

    innate_receipt = validate_definition(
        StatblockDefinitionV1.model_validate(innate), ValidationMode.persistence
    )
    assert "USAGE_FIELDS_INCOHERENT" in {issue.code for issue in innate_receipt.issues}
    assert "SPELL_GROUP_SLOTS_INCOHERENT" in {issue.code for issue in innate_receipt.issues}


def test_resource_cost_amount_cannot_exceed_pool_maximum(load_fixture) -> None:
    payload = load_fixture("legendary_creature")
    payload["rule_elements"][0]["costs"] = [
        {"resource_key": "legendary_actions", "amount": 4}
    ]

    receipt = validate_definition(
        StatblockDefinitionV1.model_validate(payload), ValidationMode.persistence
    )
    issue = next(
        item for item in receipt.issues if item.code == "RESOURCE_COST_EXCEEDS_POOL"
    )
    assert issue.field_path == "rule_elements[0].costs[0].amount"
    assert receipt.is_persistence_ready is False


def test_duplicate_same_pool_costs_rejected_and_aggregate_checked(load_fixture) -> None:
    payload = load_fixture("legendary_creature")
    payload["rule_elements"][0]["costs"] = [
        {"resource_key": "legendary_actions", "amount": 2},
        {"resource_key": "legendary_actions", "amount": 2},
    ]

    receipt = validate_definition(
        StatblockDefinitionV1.model_validate(payload), ValidationMode.persistence
    )
    codes = {issue.code: issue.field_path for issue in receipt.issues}
    assert codes.get("RESOURCE_COST_DUPLICATE_POOL") == (
        "rule_elements[0].costs[1].resource_key"
    )
    assert codes.get("RESOURCE_COST_EXCEEDS_POOL") == (
        "rule_elements[0].costs[1].amount"
    )


def test_legendary_usage_and_costs_must_name_same_pool(load_fixture) -> None:
    payload = load_fixture("legendary_creature")
    payload["resources"].append(
        {
            "key": "mythic_actions",
            "name": "Mythic Actions",
            "maximum": 3,
            "refresh": "at the start of its turn",
            "rules_text": None,
        }
    )
    payload["rule_elements"][0]["usage"]["resource_key"] = "legendary_actions"
    payload["rule_elements"][0]["costs"] = [
        {"resource_key": "mythic_actions", "amount": 1}
    ]

    receipt = validate_definition(
        StatblockDefinitionV1.model_validate(payload), ValidationMode.persistence
    )
    assert "LEGENDARY_RESOURCE_MISMATCH" in {issue.code for issue in receipt.issues}


def test_range_profile_rejects_long_shorter_than_normal() -> None:
    with pytest.raises(ValidationError, match="long range"):
        RangeProfile(
            normal=Distance(value=80, unit=DistanceUnit.feet),
            long=Distance(value=30, unit=DistanceUnit.feet),
        )


def test_attack_validation_detects_inverted_range_window(load_fixture) -> None:
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    inverted = RangeProfile.model_construct(
        normal=Distance(value=80, unit=DistanceUnit.feet),
        long=Distance(value=30, unit=DistanceUnit.feet),
    )
    element = definition.rule_elements[0]
    attack = AttackMechanic.model_construct(
        kind="attack",
        attack_type=AttackType.ranged_weapon,
        attack_bonus=5,
        reach=None,
        range=inverted,
        target=TargetProfile(kind=TargetKind.creature, count=1),
        hit_effects=[],
        miss_effects=[],
    )
    mutated = definition.model_copy(
        update={
            "rule_elements": [
                element.model_copy(update={"mechanic": attack}),
                *definition.rule_elements[1:],
            ]
        }
    )

    receipt = validate_definition(mutated, ValidationMode.persistence)
    assert "ATTACK_RANGE_ORDER_INCOHERENT" in {issue.code for issue in receipt.issues}
