from __future__ import annotations

import json

from statblocks_v1.domain.schema import (
    SCHEMA_ARTIFACT_DIRECTORY,
    canonical_json_schema,
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


def test_openai_strict_schema_closes_all_objects_and_strips_metadata() -> None:
    schema = openai_strict_json_schema()
    forbidden = {"$schema", "default", "description", "examples", "title", "discriminator"}

    def visit(node: object) -> None:
        if isinstance(node, dict):
            assert not (forbidden & set(node))
            if node.get("type") == "object" or "properties" in node:
                assert node["additionalProperties"] is False
                if "properties" in node:
                    assert node["required"] == list(node["properties"])
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
