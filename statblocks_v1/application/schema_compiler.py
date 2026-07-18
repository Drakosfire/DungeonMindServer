"""Provider-schema compilation over the published OpenAI strict artifact."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from statblocks_v1.domain.schema import SCHEMA_ARTIFACT_DIRECTORY, openai_strict_json_schema

SCHEMA_COMPILER_VERSION = "statblock-openai-strict-compiler-v1"


@dataclass(frozen=True)
class CompiledSchemaV1:
    name: str
    schema: dict[str, Any]
    compiler_version: str
    fingerprint: str


def compile_openai_definition_schema() -> CompiledSchemaV1:
    """Load the reviewed strict artifact and reject a stale contract publication."""
    artifact = SCHEMA_ARTIFACT_DIRECTORY / "statblock_definition_v1.openai-strict.schema.json"
    schema = json.loads(artifact.read_text(encoding="utf-8"))
    if schema != openai_strict_json_schema():
        raise ValueError(
            "OpenAI strict schema artifact is stale; regenerate schema artifacts before deployment"
        )
    _assert_closed_objects(schema)
    encoded = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return CompiledSchemaV1(
        name="statblock_definition_v1",
        schema=schema,
        compiler_version=SCHEMA_COMPILER_VERSION,
        fingerprint=f"sha256:{hashlib.sha256(encoded).hexdigest()}",
    )


def _assert_closed_objects(node: Any) -> None:
    if isinstance(node, list):
        for item in node:
            _assert_closed_objects(item)
    elif isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            if node.get("additionalProperties") is not False:
                raise ValueError("OpenAI strict compilation left an object open")
            if set(node.get("required", ())) != set(node.get("properties", ())):
                raise ValueError("OpenAI strict compilation omitted required properties")
        for value in node.values():
            _assert_closed_objects(value)
