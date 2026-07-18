from __future__ import annotations

import pytest

from statblocks_v1.domain import (
    StatblockDefinitionV1,
    compute_definition_digest,
    validate_definition,
)


@pytest.mark.parametrize(
    ("fixture", "expected_digest"),
    (
        ("simple_bruiser", "sha256:1896114a584759920d625e8c54bb2c34f48d5539f533364177235b4360c514a7"),
        ("spellcaster", "sha256:4be89f79011efbd1a7122e8ac741a07a32b99fe910a29ad232a93c8945e2d299"),
        ("human_adjudicated", "sha256:66947815c3622adc643ba141618f4611bccd95f0fcb9a17622c295a7814894ab"),
    ),
)
def test_definition_digest_snapshots(load_fixture, fixture: str, expected_digest: str) -> None:
    definition = StatblockDefinitionV1.model_validate(load_fixture(fixture))

    assert compute_definition_digest(definition) == expected_digest


def test_mechanic_and_rules_text_changes_change_digest(load_fixture) -> None:
    payload = load_fixture("simple_bruiser")
    original = StatblockDefinitionV1.model_validate(payload)
    payload["rule_elements"][0]["mechanic"]["attack_bonus"] = 7
    changed_mechanic = StatblockDefinitionV1.model_validate(payload)
    payload["rule_elements"][0]["rules_text"] = "A changed table-facing expression."
    changed_text = StatblockDefinitionV1.model_validate(payload)

    assert compute_definition_digest(original) != compute_definition_digest(changed_mechanic)
    assert compute_definition_digest(changed_mechanic) != compute_definition_digest(changed_text)


def test_validation_envelope_facts_do_not_change_digest(load_fixture) -> None:
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))

    receipt = validate_definition(definition, "persistence")

    assert receipt.definition_digest == compute_definition_digest(definition)
