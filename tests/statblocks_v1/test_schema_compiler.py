from statblocks_v1.application.schema_compiler import compile_openai_definition_schema


def test_compiler_is_deterministic_and_closes_every_object() -> None:
    first = compile_openai_definition_schema()
    second = compile_openai_definition_schema()

    assert first.fingerprint == second.fingerprint
    assert first.schema == second.schema
    assert first.schema["additionalProperties"] is False
    assert "$defs" in first.schema
