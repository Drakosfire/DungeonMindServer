from statblocks_v1.application.schema_compiler import compile_openai_definition_schema


def test_compiler_is_deterministic_and_closes_every_object() -> None:
    first = compile_openai_definition_schema()
    second = compile_openai_definition_schema()

    assert first.fingerprint == second.fingerprint
    assert first.schema == second.schema
    assert first.schema["additionalProperties"] is False
    assert "$defs" in first.schema


def test_prepared_provider_schema_omits_retired_element_metadata() -> None:
    prepared = compile_openai_definition_schema().schema
    definitions = prepared["$defs"]
    element = definitions["RuleElement"]
    assert "explains" not in element["properties"]
    assert "explains" not in element["required"]
    assert "ExplainsEdge" not in definitions
    assert set(element["required"]) == set(element["properties"])
    assert element["additionalProperties"] is False
