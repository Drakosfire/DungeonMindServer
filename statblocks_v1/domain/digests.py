"""Cryptographic content digests for canonical statblock definitions."""

from __future__ import annotations

import hashlib

from statblocks_v1.domain.canonicalization import canonicalize_definition
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1

DIGEST_ALGORITHM = "sha256"


def compute_definition_digest(definition: StatblockDefinitionV1) -> str:
    """Return ``sha256:<hex>`` over canonical UTF-8 definition JSON.

    Accepts only a parsed :class:`StatblockDefinitionV1`. Callers must not pass
    raw or branded JSON strings — canonicalize inside this function so digests
    cannot be forged around noncanonical text.
    """

    if not isinstance(definition, StatblockDefinitionV1):
        raise TypeError(
            "compute_definition_digest accepts only StatblockDefinitionV1; "
            f"got {type(definition).__name__}"
        )
    payload = canonicalize_definition(definition).encode("utf-8")
    return f"{DIGEST_ALGORITHM}:{hashlib.sha256(payload).hexdigest()}"
