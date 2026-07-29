"""Deterministic schema publication helpers for the v1 definition."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from statblocks_v1.domain.rule_elements import StatblockDefinitionV1

SCHEMA_ARTIFACT_DIRECTORY = Path(__file__).with_name("schema_artifacts")


class OpenAIStrictSchemaCompilationError(ValueError):
    """Raised when a canonical schema cannot be compiled losslessly for OpenAI."""


# Schema-node metadata keys stripped for OpenAI Structured Outputs strict mode.
# ``description`` is retained (empirically accepted; verified 2026-07-29).
# ``title`` is stripped: Pydantic auto-generates it from class names, duplicating
# the ``$defs`` key at pure token cost.
# These must NOT be stripped when they appear as *property names* under
# ``properties`` (e.g. ArmorClassProfile.default, StatblockFlavorText.description).
_STRIPPED_OPENAI_METADATA = frozenset(
    {
        "$schema",
        "default",
        "examples",
        "title",
        "discriminator",
    }
)

# Composition / constraint keywords with no lossless OpenAI rewrite.
# Encountering these in a canonical schema fails compilation (fail closed).
_UNSUPPORTED_OPENAI_KEYWORDS = frozenset(
    {
        "prefixItems",
        "patternProperties",
        "unevaluatedProperties",
        "unevaluatedItems",
        "if",
        "then",
        "else",
        "not",
        "dependentSchemas",
        "dependentRequired",
    }
)


def canonical_json_schema() -> dict[str, Any]:
    """Return Pydantic's canonical JSON Schema for the contract."""
    return StatblockDefinitionV1.model_json_schema()


def openai_strict_json_schema() -> dict[str, Any]:
    """Compile canonical schema into OpenAI Structured Outputs strict form.

    - Strips documentation-only metadata at schema-node level only.
    - Preserves property names that collide with metadata words.
    - Lossless rewrites: ``oneOf`` → ``anyOf``; single-branch ``allOf`` unwrap.
    - Fails closed on unsupported constructs without a lossless rewrite.
    - Closes every object (``additionalProperties: false`` + all properties required).
    """
    return _transform_schema_node(copy.deepcopy(canonical_json_schema()))


def write_schema_artifacts(directory: Path = SCHEMA_ARTIFACT_DIRECTORY) -> tuple[Path, Path]:
    """Write stable, reviewable schema artifacts and return their paths."""
    directory.mkdir(parents=True, exist_ok=True)
    canonical_path = directory / "statblock_definition_v1.canonical.schema.json"
    strict_path = directory / "statblock_definition_v1.openai-strict.schema.json"
    _write_json(canonical_path, canonical_json_schema())
    _write_json(strict_path, openai_strict_json_schema())
    return canonical_path, strict_path


def collect_property_paths(schema: dict[str, Any]) -> set[str]:
    """Collect dotted property paths from a JSON Schema (resolving local ``$defs``)."""
    defs = schema.get("$defs") or schema.get("definitions") or {}
    paths: set[str] = set()
    _walk_property_paths(schema, defs=defs, prefix="", out=paths, seen_refs=set())
    return paths


def _transform_schema_node(node: Any) -> Any:
    if isinstance(node, list):
        return [_transform_schema_node(item) for item in node]
    if not isinstance(node, dict):
        return node

    unsupported = _UNSUPPORTED_OPENAI_KEYWORDS & set(node.keys())
    if unsupported:
        names = ", ".join(sorted(repr(k) for k in unsupported))
        raise OpenAIStrictSchemaCompilationError(
            f"Unsupported OpenAI Structured Outputs construct(s) {names}; "
            "no lossless rewrite is defined (fail closed)"
        )

    if "allOf" in node:
        return _transform_schema_node(_unwrap_single_all_of(node))

    transformed: dict[str, Any] = {}
    for key, value in node.items():
        if key in _STRIPPED_OPENAI_METADATA:
            continue
        if key == "oneOf":
            # Lossless rewrite: OpenAI supports anyOf, not oneOf.
            transformed["anyOf"] = _transform_schema_node(value)
            continue
        if key == "properties" and isinstance(value, dict):
            # Property names are never treated as metadata keywords.
            transformed[key] = {
                prop_name: _transform_schema_node(prop_schema)
                for prop_name, prop_schema in value.items()
            }
            continue
        if key in {"$defs", "definitions"} and isinstance(value, dict):
            transformed[key] = {
                def_name: _transform_schema_node(def_schema)
                for def_name, def_schema in value.items()
            }
            continue
        transformed[key] = _transform_schema_node(value)

    if transformed.get("type") == "object" or "properties" in transformed:
        transformed["additionalProperties"] = False
        if "properties" in transformed:
            transformed["required"] = list(transformed["properties"])
    return transformed


def _unwrap_single_all_of(node: dict[str, Any]) -> dict[str, Any]:
    """Losslessly unwrap Pydantic's single-branch ``allOf`` + sibling metadata pattern.

    Multi-branch ``allOf`` has no lossless OpenAI rewrite and fails closed.
    """
    branches = node["allOf"]
    if not isinstance(branches, list) or len(branches) != 1:
        count = len(branches) if isinstance(branches, list) else "non-list"
        raise OpenAIStrictSchemaCompilationError(
            f"Unsupported allOf with {count} branches; "
            "only a single-branch allOf unwrap is defined (fail closed)"
        )
    sole = branches[0]
    if not isinstance(sole, dict):
        raise OpenAIStrictSchemaCompilationError(
            "Unsupported allOf branch: expected a schema object (fail closed)"
        )
    merged = dict(sole)
    for key, value in node.items():
        if key == "allOf":
            continue
        if key in merged and key not in _STRIPPED_OPENAI_METADATA:
            raise OpenAIStrictSchemaCompilationError(
                f"Cannot unwrap allOf: conflicting sibling key {key!r} (fail closed)"
            )
        merged[key] = value
    return merged


def _walk_property_paths(
    node: Any,
    *,
    defs: dict[str, Any],
    prefix: str,
    out: set[str],
    seen_refs: set[str],
) -> None:
    if isinstance(node, list):
        for item in node:
            _walk_property_paths(item, defs=defs, prefix=prefix, out=out, seen_refs=seen_refs)
        return
    if not isinstance(node, dict):
        return

    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        def_name = ref.rsplit("/", 1)[-1]
        if def_name not in seen_refs:
            seen_refs.add(def_name)
            target = defs.get(def_name)
            if target is not None:
                _walk_property_paths(
                    target, defs=defs, prefix=prefix, out=out, seen_refs=seen_refs
                )
            seen_refs.discard(def_name)
        return

    properties = node.get("properties")
    if isinstance(properties, dict):
        for prop_name, prop_schema in properties.items():
            path = f"{prefix}.{prop_name}" if prefix else prop_name
            out.add(path)
            _walk_property_paths(
                prop_schema, defs=defs, prefix=path, out=out, seen_refs=seen_refs
            )

    for key in ("anyOf", "oneOf", "allOf"):
        branch = node.get(key)
        if isinstance(branch, list):
            for item in branch:
                _walk_property_paths(
                    item, defs=defs, prefix=prefix, out=out, seen_refs=seen_refs
                )

    items = node.get("items")
    if isinstance(items, dict):
        _walk_property_paths(
            items,
            defs=defs,
            prefix=f"{prefix}[]" if prefix else "[]",
            out=out,
            seen_refs=seen_refs,
        )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
