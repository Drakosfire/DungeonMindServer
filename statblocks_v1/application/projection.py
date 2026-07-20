"""Minimal combat projection helpers for smoke and consumer proofs."""
from __future__ import annotations

from typing import Any

from statblocks_v1.domain.rule_elements import StatblockDefinitionV1


def combat_minimums(definition: StatblockDefinitionV1) -> dict[str, Any]:
    """Derive stable combat summary fields without logging private narrative text."""
    armor = next(
        (profile for profile in definition.defenses.armor_classes if profile.default),
        definition.defenses.armor_classes[0],
    )
    hp = definition.vitality.hit_points
    return {
        "name": definition.identity.name,
        "armor_class": armor.value,
        "hit_points": hp.displayed_average,
        "hit_point_formula": (
            hp.formula.model_dump(mode="json") if hp.formula is not None else None
        ),
        "challenge_rating": definition.challenge.rating,
        "proficiency_bonus": definition.challenge.proficiency_bonus,
        "speed": [
            {
                "mode": mode.mode.value if hasattr(mode.mode, "value") else mode.mode,
                "distance": mode.distance.model_dump(mode="json"),
            }
            for mode in definition.movement.modes
        ],
        "human_adjudicated_elements": [
            element.key
            for element in definition.rule_elements
            if getattr(element.mechanic, "kind", None) == "human_adjudicated"
        ],
    }
