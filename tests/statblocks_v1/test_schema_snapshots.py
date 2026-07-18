from __future__ import annotations

import json

import pytest

from statblocks_v1.domain.schema import (
    SCHEMA_ARTIFACT_DIRECTORY,
    OpenAIStrictSchemaCompilationError,
    _UNSUPPORTED_OPENAI_KEYWORDS,
    _UNSUPPORTED_OPENAI_METADATA,
    _transform_schema_node,
    canonical_json_schema,
    collect_property_paths,
    openai_strict_json_schema,
)


def test_schema_artifacts_match_model_output() -> None:
    canonical = json.loads(
        (SCHEMA_ARTIFACT_DIRECTORY / "statblock_definition_v1.canonical.schema.json").read_text()
    )
    strict = json.loads(
        (SCHEMA_ARTIFACT_DIRECTORY / "statblock_definition_v1.openai-strict.schema.json").read_text()
    )

    assert canonical == canonical_json_schema()
    assert strict == openai_strict_json_schema()


def test_openai_strict_schema_preserves_property_names_matching_metadata() -> None:
    schema = openai_strict_json_schema()
    paths = collect_property_paths(schema)
    assert "defenses.armor_classes[].default" in paths or any(
        p.endswith(".default") for p in paths
    )
    assert any(p.endswith(".description") for p in paths)


def test_openai_strict_schema_closes_objects_and_strips_node_metadata() -> None:
    schema = openai_strict_json_schema()

    def visit(node: object, *, under_properties: bool = False) -> None:
        if isinstance(node, dict):
            if not under_properties:
                assert not (_UNSUPPORTED_OPENAI_METADATA & set(node.keys()))
            assert not (_UNSUPPORTED_OPENAI_KEYWORDS & set(node.keys()))
            if node.get("type") == "object" or "properties" in node:
                assert node["additionalProperties"] is False
                if "properties" in node:
                    assert node["required"] == list(node["properties"])
            for key, value in node.items():
                if key == "properties" and isinstance(value, dict):
                    for prop_schema in value.values():
                        visit(prop_schema, under_properties=False)
                else:
                    visit(value, under_properties=False)
        elif isinstance(node, list):
            for value in node:
                visit(value, under_properties=under_properties)

    visit(schema)


def test_openai_strict_schema_uses_anyof_not_oneof_or_prefix_items() -> None:
    schema = openai_strict_json_schema()
    encoded = json.dumps(schema)
    assert '"oneOf"' not in encoded
    assert '"allOf"' not in encoded
    assert '"prefixItems"' not in encoded
    assert "anyOf" in encoded


def test_openai_strict_compiler_fails_closed_on_unsupported_constructs() -> None:
    """Unsupported composition keywords must raise, not silently disappear."""
    with pytest.raises(OpenAIStrictSchemaCompilationError, match="not"):
        _transform_schema_node(
            {
                "type": "object",
                "properties": {"x": {"not": {"type": "null"}}},
                "additionalProperties": False,
                "required": ["x"],
            }
        )

    with pytest.raises(OpenAIStrictSchemaCompilationError, match="allOf"):
        _transform_schema_node(
            {
                "allOf": [
                    {"type": "object", "properties": {"a": {"type": "string"}}},
                    {"type": "object", "properties": {"b": {"type": "integer"}}},
                ]
            }
        )

    with pytest.raises(OpenAIStrictSchemaCompilationError, match="if"):
        _transform_schema_node(
            {
                "type": "object",
                "properties": {"n": {"type": "integer"}},
                "if": {"properties": {"n": {"const": 0}}},
                "then": {"required": ["n"]},
            }
        )

    # Lossless rewrites still succeed.
    rewritten = _transform_schema_node(
        {
            "oneOf": [
                {
                    "type": "object",
                    "properties": {"kind": {"const": "a"}},
                    "required": ["kind"],
                },
                {
                    "type": "object",
                    "properties": {"kind": {"const": "b"}},
                    "required": ["kind"],
                },
            ]
        }
    )
    assert "anyOf" in rewritten
    assert "oneOf" not in rewritten

    unwrapped = _transform_schema_node(
        {"allOf": [{"$ref": "#/$defs/DistanceUnit"}], "default": "feet"}
    )
    assert unwrapped == {"$ref": "#/$defs/DistanceUnit"}


def test_canonical_and_provider_property_paths_match() -> None:
    canonical_paths = collect_property_paths(canonical_json_schema())
    provider_paths = collect_property_paths(openai_strict_json_schema())
    assert canonical_paths == provider_paths
    assert "defenses.armor_classes[].default" in provider_paths or any(
        "armor_classes" in p and p.endswith(".default") for p in provider_paths
    )
    assert any("flavor_text" in p and p.endswith(".description") for p in provider_paths)
