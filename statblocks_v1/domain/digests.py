"""Cryptographic content digests for canonical statblock definitions."""

from __future__ import annotations

import hashlib

from statblocks_v1.domain.canonicalization import canonical_definition_bytes
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1

DIGEST_ALGORITHM = "sha256"


def compute_definition_digest(
    definition: StatblockDefinitionV1 | str | bytes,
) -> str:
    """Return ``sha256:<hex>`` over canonical UTF-8 definition JSON.

    A ``str`` or ``bytes`` input is accepted for persistence code that already
    holds canonical JSON. Callers remain responsible for only passing output
    from :func:`canonicalize_definition` in that case.
    """

    if isinstance(definition, StatblockDefinitionV1):
        payload = canonical_definition_bytes(definition)
    elif isinstance(definition, str):
        payload = definition.encode("utf-8")
    else:
        payload = definition
    return f"{DIGEST_ALGORITHM}:{hashlib.sha256(payload).hexdigest()}"
