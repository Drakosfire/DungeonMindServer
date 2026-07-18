from __future__ import annotations

import pytest

from statblocks_v1.domain import (
    CanonicalDefinitionJSON,
    StatblockDefinitionV1,
    canonicalize_definition,
    compute_definition_digest,
    validate_definition,
)


@pytest.mark.parametrize(
    ("fixture", "expected_digest"),
    (
        ("simple_bruiser", "sha256:265da39c72a5275bfb81315034b972ddae4aca261a683fa9ecc70a4839e91c44"),
        ("spellcaster", "sha256:bcd596e77e2458682425d36558fa2f8cd4a2951d99d8202d319e086e39cd5bbd"),
        ("human_adjudicated", "sha256:974de07596c008ebc3a480c50c81ad693346a1ce1dad896da69b0a7da4783229"),
    ),
)
def test_definition_digest_snapshots(load_fixture, fixture: str, expected_digest: str) -> None:
    definition = StatblockDefinitionV1.model_validate(load_fixture(fixture))
    digest = compute_definition_digest(definition)
    if expected_digest.endswith("PLACEHOLDER"):
        pytest.fail(f"refresh snapshot for {fixture}: {digest}")
    assert digest == expected_digest
    assert compute_definition_digest(canonicalize_definition(definition)) == digest


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


def test_raw_string_and_bytes_cannot_bypass_canonicalizer(load_fixture) -> None:
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    canonical = canonicalize_definition(definition)
    noncanonical = '{"z":1,"a":2}'

    assert isinstance(canonical, CanonicalDefinitionJSON)
    with pytest.raises(TypeError, match="CanonicalDefinitionJSON"):
        compute_definition_digest(noncanonical)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="CanonicalDefinitionJSON"):
        compute_definition_digest(noncanonical.encode("utf-8"))  # type: ignore[arg-type]
    assert compute_definition_digest(canonical) == compute_definition_digest(definition)
