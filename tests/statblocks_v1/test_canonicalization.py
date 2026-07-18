from __future__ import annotations

from statblocks_v1.domain import (
    StatblockDefinitionV1,
    canonical_definition_bytes,
    canonicalize_definition,
)


def test_canonicalization_is_byte_identical(load_fixture) -> None:
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))

    assert canonical_definition_bytes(definition) == canonical_definition_bytes(definition)
    assert canonicalize_definition(definition).startswith('{"abilities":')


def test_set_like_tags_normalize_but_rule_order_is_preserved(load_fixture) -> None:
    payload = load_fixture("simple_bruiser")
    payload["rule_elements"][0]["tags"] = ["brute", "attack", "brute"]
    duplicate = payload["rule_elements"][0].copy()
    duplicate["key"] = "second_attack"
    duplicate["name"] = "Second Attack"
    payload["rule_elements"].append(duplicate)

    first = StatblockDefinitionV1.model_validate(payload)
    payload["rule_elements"][0]["tags"] = ["attack", "brute"]
    payload["rule_elements"].reverse()
    second = StatblockDefinitionV1.model_validate(payload)

    assert '"tags":["attack","brute"]' in canonicalize_definition(first)
    assert canonicalize_definition(first) != canonicalize_definition(second)


def test_rules_text_whitespace_is_preserved(load_fixture) -> None:
    payload = load_fixture("simple_bruiser")
    payload["rule_elements"][0]["rules_text"] = "Hit:\n  13 damage.  "

    canonical = canonicalize_definition(StatblockDefinitionV1.model_validate(payload))

    assert "Hit:\\n  13 damage.  " in canonical
