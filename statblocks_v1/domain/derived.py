"""Server-owned derived values for the v1 statblock contract.

The LLM authors intent (ability scores, challenge rating, derivation kinds,
dice formulas). Every value that is a deterministic function of that intent
is computed by the server: provider-emitted numbers for these fields are
advisory and are overwritten before validation and storage. This module is
the single source of truth for the derivation math; ``validation.py`` imports
it to check (rather than re-implement) the same rules.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from statblocks_v1.domain.primitives import AbilityName, DiceExpression
from statblocks_v1.domain.profiles import AbilityScores, ProficiencyDerivation
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1

CR_PROFICIENCY_BONUS = {
    "0": 2,
    "1/8": 2,
    "1/4": 2,
    "1/2": 2,
    **{str(cr): 2 for cr in range(1, 5)},
    **{str(cr): 3 for cr in range(5, 9)},
    **{str(cr): 4 for cr in range(9, 13)},
    **{str(cr): 5 for cr in range(13, 17)},
    **{str(cr): 6 for cr in range(17, 21)},
    **{str(cr): 7 for cr in range(21, 25)},
    **{str(cr): 8 for cr in range(25, 29)},
    **{str(cr): 9 for cr in range(29, 31)},
}


def ability_modifier(abilities: AbilityScores, ability: AbilityName) -> int:
    return (getattr(abilities, ability.value) - 10) // 2


def expected_proficiency_bonus(
    abilities: AbilityScores,
    ability: AbilityName,
    derivation: ProficiencyDerivation,
    proficiency_bonus: int,
) -> int | None:
    """Expected save/skill value, or None when derivation keeps authored authority."""
    modifier = ability_modifier(abilities, ability)
    if derivation is ProficiencyDerivation.standard:
        return modifier + proficiency_bonus
    if derivation is ProficiencyDerivation.expertise:
        return modifier + (2 * proficiency_bonus)
    return None


def hit_point_average(formula: DiceExpression) -> int:
    return formula.count * (formula.die + 1) // 2 + formula.modifier


@dataclass(frozen=True)
class DerivedValueAdjustmentV1:
    """One provider-emitted value overwritten by server computation."""

    field_path: str
    provider_value: int | None
    computed_value: int


def compute_derived_values(
    definition: StatblockDefinitionV1,
) -> tuple[StatblockDefinitionV1, list[DerivedValueAdjustmentV1]]:
    """Return the definition with every server-owned value computed, plus adjustments.

    Server-owned: challenge.proficiency_bonus (from rating); saving throw and
    skill values for standard/expertise derivations (explicit_override keeps
    authored authority); vitality.hit_points.displayed_average (from the dice
    formula, when present). senses.passive_perception is deliberately excluded:
    traits can legitimately raise it, so it stays authored-and-validated.
    """
    adjustments: list[DerivedValueAdjustmentV1] = []

    challenge = definition.challenge
    table_bonus = CR_PROFICIENCY_BONUS.get(challenge.rating)
    if table_bonus is not None and challenge.proficiency_bonus != table_bonus:
        adjustments.append(
            DerivedValueAdjustmentV1(
                "challenge.proficiency_bonus", challenge.proficiency_bonus, table_bonus
            )
        )
        challenge = challenge.model_copy(update={"proficiency_bonus": table_bonus})
    proficiency_bonus = challenge.proficiency_bonus

    def _derive_items(items, path_prefix):
        derived_items = []
        for index, item in enumerate(items):
            expected = expected_proficiency_bonus(
                definition.abilities, item.ability, item.derivation, proficiency_bonus
            )
            if expected is not None and item.value != expected:
                adjustments.append(
                    DerivedValueAdjustmentV1(
                        f"{path_prefix}[{index}].value", item.value, expected
                    )
                )
                item = item.model_copy(update={"value": expected})
            derived_items.append(item)
        return derived_items

    proficiencies = definition.proficiencies
    saving_throws = _derive_items(proficiencies.saving_throws, "proficiencies.saving_throws")
    skills = _derive_items(proficiencies.skills, "proficiencies.skills")

    hit_points = definition.vitality.hit_points
    if hit_points.formula is not None:
        average = hit_point_average(hit_points.formula)
        # displayed_average is bounded (>= 1) while DiceExpression.modifier is
        # not: a pathological formula (1d2-2) can average below the field's
        # floor. Skip the write; the authored value stays and the validator's
        # mismatch error keeps the weird formula visible instead of storing a
        # contract-violating number.
        if average >= 1 and hit_points.displayed_average != average:
            adjustments.append(
                DerivedValueAdjustmentV1(
                    "vitality.hit_points.displayed_average",
                    hit_points.displayed_average,
                    average,
                )
            )
            hit_points = hit_points.model_copy(update={"displayed_average": average})

    if not adjustments:
        return definition, adjustments

    derived = definition.model_copy(
        update={
            "challenge": challenge,
            "proficiencies": proficiencies.model_copy(
                update={"saving_throws": saving_throws, "skills": skills}
            ),
            "vitality": definition.vitality.model_copy(update={"hit_points": hit_points}),
        }
    )
    try:
        # model_copy skips validation; revalidate so a computed value can never
        # smuggle a contract violation into the stored candidate.
        derived = StatblockDefinitionV1.model_validate(derived.model_dump(mode="json"))
    except ValidationError:
        # Fail safe: keep the provider's original (which already parsed) and let
        # domain validation report the raw state on the receipt instead.
        return definition, []
    return derived, adjustments
