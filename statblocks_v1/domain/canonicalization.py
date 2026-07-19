"""Versioned canonical JSON for statblock mechanics definitions.

Policy v1 serializes a Pydantic definition with every contract field present
(including explicit ``null`` and empty lists), normalizes strings to Unicode
NFC, and emits compact UTF-8 JSON with lexicographically ordered object keys.
``rules_text`` is never trimmed, collapsed, or regenerated; NFC is the only
string transformation.  Presentation and execution lists retain their order.
Known set-like fields (tags, qualifiers, damage types, languages, and similar
metadata) are sorted and deduplicated.  Dice and CR are already structured /
string fields in the contract and are therefore emitted without reformatting.

The implementation is RFC 8785-compatible for contract v1's JSON subset:
integers, strings, booleans, nulls, arrays, and objects.  The schema excludes
floating-point values, avoiding platform-specific number serialization.
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Mapping
from typing import Any, final

from statblocks_v1.domain.rule_elements import StatblockDefinitionV1

CANONICALIZER_VERSION = "statblock-canonicalizer-v1"

_SET_LIKE_FIELD_NAMES = frozenset(
    {
        "adjudication_tags",
        "bypasses",
        "condition_immunities",
        "damage_types",
        "languages",
        "qualifiers",
        "special_modes",
        "subtypes",
        "tags",
    }
)


@final
class CanonicalDefinitionJSON(str):
    """Canonical JSON text returned by :func:`canonicalize_definition`.

    This is a convenience brand for persistence/transport callers. Digests must
    still be computed from :class:`StatblockDefinitionV1` so forged wrappers
    around noncanonical text cannot bypass canonicalization.
    """

    __slots__ = ()


def canonicalize_definition(definition: StatblockDefinitionV1) -> CanonicalDefinitionJSON:
    """Return the version-1 canonical JSON representation of ``definition``."""

    payload = definition.model_dump(mode="json", exclude_none=False)
    normalized = _normalize_value(payload)
    text = json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return CanonicalDefinitionJSON(text)


def canonical_definition_bytes(definition: StatblockDefinitionV1) -> bytes:
    """Return canonical JSON encoded as UTF-8 for hashing or persistence."""

    return canonicalize_definition(definition).encode("utf-8")


def _normalize_value(value: Any, field_name: str | None = None) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        return {
            unicodedata.normalize("NFC", str(key)): _normalize_value(item, str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        normalized = [_normalize_value(item) for item in value]
        if field_name in _SET_LIKE_FIELD_NAMES:
            return sorted(set(normalized))
        return normalized
    return value
