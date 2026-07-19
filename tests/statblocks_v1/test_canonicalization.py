from __future__ import annotations

import unicodedata

from statblocks_v1.domain import (
    CanonicalDefinitionJSON,
    StatblockDefinitionV1,
    canonical_definition_bytes,
    canonicalize_definition,
    compute_definition_digest,
)


def test_set_like_field_order_normalizes_to_identical_bytes(load_fixture) -> None:
    payload = load_fixture("simple_bruiser")
    payload["identity"]["subtypes"] = ["orc", "brute"]
    payload["communication"]["languages"] = ["Orc", "Common"]
    payload["rule_elements"][0]["tags"] = ["brute", "attack", "brute"]
    first = StatblockDefinitionV1.model_validate(payload)

    payload["identity"]["subtypes"] = ["brute", "orc"]
    payload["communication"]["languages"] = ["Common", "Orc"]
    payload["rule_elements"][0]["tags"] = ["attack", "brute"]
    second = StatblockDefinitionV1.model_validate(payload)

    assert canonicalize_definition(first) == canonicalize_definition(second)
    assert canonical_definition_bytes(first) == canonical_definition_bytes(second)
    assert compute_definition_digest(first) == compute_definition_digest(second)


def test_nfc_and_decomposed_unicode_normalize_identically(load_fixture) -> None:
    payload = load_fixture("simple_bruiser")
    payload["identity"]["name"] = unicodedata.normalize("NFC", "Cafe\u0301 Brute")
    composed = StatblockDefinitionV1.model_validate(payload)
    payload["identity"]["name"] = unicodedata.normalize("NFD", "Café Brute")
    decomposed = StatblockDefinitionV1.model_validate(payload)

    assert canonicalize_definition(composed) == canonicalize_definition(decomposed)
    assert compute_definition_digest(composed) == compute_definition_digest(decomposed)


def test_presentation_order_of_rule_elements_is_preserved(load_fixture) -> None:
    payload = load_fixture("simple_bruiser")
    duplicate = payload["rule_elements"][0].copy()
    duplicate["key"] = "second_attack"
    duplicate["name"] = "Second Attack"
    payload["rule_elements"].append(duplicate)
    first = StatblockDefinitionV1.model_validate(payload)

    payload["rule_elements"].reverse()
    second = StatblockDefinitionV1.model_validate(payload)

    assert canonicalize_definition(first) != canonicalize_definition(second)


def test_rules_text_whitespace_is_preserved(load_fixture) -> None:
    payload = load_fixture("simple_bruiser")
    payload["rule_elements"][0]["rules_text"] = "Hit:\n  13 damage.  "

    canonical = canonicalize_definition(StatblockDefinitionV1.model_validate(payload))

    assert isinstance(canonical, CanonicalDefinitionJSON)
    assert "Hit:\\n  13 damage.  " in canonical
    assert canonicalize_definition(
        StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    ).startswith('{"abilities":')
