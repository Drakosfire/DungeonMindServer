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
        ("simple_bruiser", "sha256:935dc0dff1ac7cc8405836764469761a1d26e9e38dd74cd856b8a8a31f0fae51"),
        ("spellcaster", "sha256:a4dcbf3ad017f5fbc893603718b8728541bc554a0b3aed7815dc6be2658b7b0a"),
        ("human_adjudicated", "sha256:1e98449313c00ee129f7a4d207b51dcb9df368f151147cb2dacbe99462e09982"),
    ),
)
def test_definition_digest_snapshots(load_fixture, fixture: str, expected_digest: str) -> None:
    definition = StatblockDefinitionV1.model_validate(load_fixture(fixture))
    digest = compute_definition_digest(definition)
    if expected_digest.endswith("PLACEHOLDER"):
        pytest.fail(f"refresh snapshot for {fixture}: {digest}")
    assert digest == expected_digest


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


def test_digest_api_accepts_only_definition_model(load_fixture) -> None:
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    canonical = canonicalize_definition(definition)
    forged = CanonicalDefinitionJSON('{"z":1,"a":2}')
    noncanonical = '{"z":1,"a":2}'

    assert isinstance(canonical, CanonicalDefinitionJSON)
    with pytest.raises(TypeError, match="StatblockDefinitionV1"):
        compute_definition_digest(noncanonical)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="StatblockDefinitionV1"):
        compute_definition_digest(noncanonical.encode("utf-8"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="StatblockDefinitionV1"):
        compute_definition_digest(forged)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="StatblockDefinitionV1"):
        compute_definition_digest(canonical)  # type: ignore[arg-type]
    assert compute_definition_digest(definition).startswith("sha256:")
