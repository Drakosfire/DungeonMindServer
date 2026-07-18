"""Cryptographic content digests for canonical statblock definitions."""

from __future__ import annotations

import hashlib

from statblocks_v1.domain.canonicalization import (
    CanonicalDefinitionJSON,
    canonicalize_definition,
)
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1

DIGEST_ALGORITHM = "sha256"


def compute_definition_digest(
    definition: StatblockDefinitionV1 | CanonicalDefinitionJSON,
) -> str:
    """Return ``sha256:<hex>`` over canonical UTF-8 definition JSON.

    Accepts only a parsed definition model or a branded
    :class:`CanonicalDefinitionJSON` from :func:`canonicalize_definition`.
    Raw ``str`` / ``bytes`` are rejected so noncanonical JSON cannot receive a
    normal-looking digest.
    """

    if isinstance(definition, StatblockDefinitionV1):
        payload = canonicalize_definition(definition).encode("utf-8")
    elif isinstance(definition, CanonicalDefinitionJSON):
        payload = definition.encode("utf-8")
    else:
        raise TypeError(
            "compute_definition_digest accepts StatblockDefinitionV1 or "
            "CanonicalDefinitionJSON from canonicalize_definition; "
            f"got {type(definition).__name__}"
        )
    return f"{DIGEST_ALGORITHM}:{hashlib.sha256(payload).hexdigest()}"
