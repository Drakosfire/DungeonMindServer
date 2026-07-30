"""Server-owned derived values: provider-emitted numbers are advisory."""

from statblocks_v1.domain.derived import compute_derived_values
from statblocks_v1.domain.profiles import (
    ProficiencyDerivation,
    SavingThrowBonus,
    SkillBonus,
)
from statblocks_v1.domain.primitives import AbilityName
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1


def _definition(load_fixture) -> StatblockDefinitionV1:
    return StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))


def _with_proficiencies(
    definition: StatblockDefinitionV1,
    *,
    skills: list[SkillBonus] | None = None,
    saving_throws: list[SavingThrowBonus] | None = None,
) -> StatblockDefinitionV1:
    return definition.model_copy(
        update={
            "proficiencies": definition.proficiencies.model_copy(
                update={
                    "skills": skills if skills is not None else definition.proficiencies.skills,
                    "saving_throws": (
                        saving_throws
                        if saving_throws is not None
                        else definition.proficiencies.saving_throws
                    ),
                }
            )
        }
    )


def test_standard_skill_value_is_recomputed(load_fixture) -> None:
    definition = _with_proficiencies(
        _definition(load_fixture),
        skills=[
            SkillBonus(
                skill="Athletics",
                ability=AbilityName.strength,
                value=7,
                derivation=ProficiencyDerivation.standard,
            )
        ],
    )

    derived, adjustments = compute_derived_values(definition)

    # STR 18 (+4) with CR 3 proficiency bonus (+2) is +6, not the emitted 7.
    assert derived.proficiencies.skills[0].value == 6
    assert [
        (a.field_path, a.provider_value, a.computed_value) for a in adjustments
    ] == [("proficiencies.skills[0].value", 7, 6)]


def test_expertise_save_value_is_recomputed(load_fixture) -> None:
    definition = _with_proficiencies(
        _definition(load_fixture),
        saving_throws=[
            SavingThrowBonus(
                ability=AbilityName.strength,
                value=99,
                derivation=ProficiencyDerivation.expertise,
            )
        ],
    )

    derived, adjustments = compute_derived_values(definition)

    # Expertise: +4 modifier plus double proficiency (+4) = +8.
    assert derived.proficiencies.saving_throws[0].value == 8
    assert [
        (a.field_path, a.provider_value, a.computed_value) for a in adjustments
    ] == [("proficiencies.saving_throws[0].value", 99, 8)]


def test_explicit_override_keeps_authored_authority(load_fixture) -> None:
    definition = _with_proficiencies(
        _definition(load_fixture),
        skills=[
            SkillBonus(
                skill="Intimidation",
                ability=AbilityName.charisma,
                value=9,
                derivation=ProficiencyDerivation.explicit_override,
            )
        ],
    )

    derived, adjustments = compute_derived_values(definition)

    assert derived.proficiencies.skills[0].value == 9
    assert adjustments == []


def test_proficiency_bonus_is_recomputed_from_rating_and_derivations_follow(
    load_fixture,
) -> None:
    definition = _definition(load_fixture).model_copy(
        update={"challenge": _definition(load_fixture).challenge.model_copy(
            update={"proficiency_bonus": 9}
        )}
    )
    definition = _with_proficiencies(
        definition,
        skills=[
            SkillBonus(
                skill="Athletics",
                ability=AbilityName.strength,
                value=13,
                derivation=ProficiencyDerivation.standard,
            )
        ],
    )

    derived, adjustments = compute_derived_values(definition)

    # Rating "3" owns proficiency bonus +2; the standard skill derives against
    # the corrected bonus (+4 modifier + 2), not the emitted +9.
    assert derived.challenge.proficiency_bonus == 2
    assert derived.proficiencies.skills[0].value == 6
    paths = [a.field_path for a in adjustments]
    assert paths == ["challenge.proficiency_bonus", "proficiencies.skills[0].value"]


def test_unknown_rating_preserves_authored_bonus(load_fixture) -> None:
    base = _definition(load_fixture)
    definition = base.model_copy(
        update={
            "challenge": base.challenge.model_copy(
                update={"rating": "mythic", "proficiency_bonus": 7}
            )
        }
    )

    derived, adjustments = compute_derived_values(definition)

    assert derived.challenge.proficiency_bonus == 7
    assert adjustments == []


def test_displayed_average_is_recomputed_from_formula(load_fixture) -> None:
    base = _definition(load_fixture)
    for emitted in (999, None):
        definition = base.model_copy(
            update={
                "vitality": base.vitality.model_copy(
                    update={
                        "hit_points": base.vitality.hit_points.model_copy(
                            update={"displayed_average": emitted}
                        )
                    }
                )
            }
        )

        derived, adjustments = compute_derived_values(definition)

        # 8d10+24 averages 68 regardless of the emitted value (or its absence).
        assert derived.vitality.hit_points.displayed_average == 68
        assert [
            (a.field_path, a.provider_value, a.computed_value) for a in adjustments
        ] == [("vitality.hit_points.displayed_average", emitted, 68)]


def test_fixed_hit_point_method_leaves_displayed_average_alone(load_fixture) -> None:
    base = _definition(load_fixture)
    definition = base.model_copy(
        update={
            "vitality": base.vitality.model_copy(
                update={
                    "hit_points": base.vitality.hit_points.model_copy(
                        update={
                            "method": "fixed",
                            "formula": None,
                            "fixed_value": 68,
                            "displayed_average": None,
                        }
                    )
                }
            )
        }
    )

    derived, adjustments = compute_derived_values(definition)

    assert derived.vitality.hit_points.displayed_average is None
    assert adjustments == []


def test_consistent_definition_is_returned_unchanged(load_fixture) -> None:
    definition = _definition(load_fixture)

    derived, adjustments = compute_derived_values(definition)

    assert derived is definition
    assert adjustments == []
