from __future__ import annotations

import pytest
from pydantic import ValidationError

from statblocks_v1.domain import StatblockDefinitionV1
from statblocks_v1.domain.rule_elements import (
    AttackMechanic,
    HumanAdjudicatedMechanic,
    PhaseTransitionMechanic,
)


def test_mechanic_discriminators_select_concrete_models(load_fixture) -> None:
    bruiser = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    mythic = StatblockDefinitionV1.model_validate(load_fixture("mythic_phase"))
    adjudicated = StatblockDefinitionV1.model_validate(load_fixture("human_adjudicated"))

    assert isinstance(bruiser.rule_elements[0].mechanic, AttackMechanic)
    assert isinstance(mythic.rule_elements[0].mechanic, PhaseTransitionMechanic)
    assert isinstance(adjudicated.rule_elements[0].mechanic, HumanAdjudicatedMechanic)


def test_canonical_models_forbid_unknown_fields(load_fixture) -> None:
    payload = load_fixture("simple_bruiser")
    payload["identity"]["unexpected"] = "not accepted"

    with pytest.raises(ValidationError, match="extra_forbidden"):
        StatblockDefinitionV1.model_validate(payload)


def test_formula_hp_requires_dice_expression(load_fixture) -> None:
    with pytest.raises(ValidationError) as error:
        StatblockDefinitionV1.model_validate(load_fixture("formula_hp_missing_formula"))

    assert error.value.errors()[0]["loc"] == ("vitality", "hit_points")
