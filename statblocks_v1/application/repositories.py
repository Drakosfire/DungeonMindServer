"""Transport-neutral synchronous repository protocols and persistence commands.

Firestore's Python client is blocking.  These protocols intentionally expose
synchronous methods; async API code must call them with ``asyncio.to_thread``.
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Protocol

from statblocks_v1.domain.canonicalization import canonicalize_definition
from statblocks_v1.domain.resources import (
    GeneratedStatblockCandidateV1,
    IdempotencyRecordV1,
    StatblockResourceV1,
    StatblockRevisionResourceV1,
)
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1


def compute_request_digest(operation: str, payload: dict[str, Any]) -> str:
    """Hash operation intent with NFC-normalized, order-stable JSON.

    The definition component must already be PR14 canonical JSON text so Unicode
    and set-like field ordering cannot create false idempotency conflicts.
    """

    canonical = json.dumps(
        {
            "operation": operation,
            "payload": _normalize_request_payload(payload),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _normalize_request_payload(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        return {
            unicodedata.normalize("NFC", str(key)): _normalize_request_payload(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, list):
        return [_normalize_request_payload(item) for item in value]
    return value


class CandidateRepository(Protocol):
    def create(self, candidate: GeneratedStatblockCandidateV1) -> GeneratedStatblockCandidateV1: ...
    def get(self, candidate_id: str, *, now: datetime | None = None) -> GeneratedStatblockCandidateV1: ...


class StatblockRepository(Protocol):
    def get(self, statblock_id: str) -> StatblockResourceV1: ...


class RevisionRepository(Protocol):
    def get_revision(self, statblock_id: str, revision_id: str) -> StatblockRevisionResourceV1: ...
    def list_for_statblock(self, statblock_id: str) -> list[StatblockRevisionResourceV1]: ...


class IdempotencyRepository(Protocol):
    def get_idempotency(
        self, caller_scope: str, operation: str, idempotency_key: str
    ) -> IdempotencyRecordV1 | None: ...


class StatblockPersistenceRepository(
    StatblockRepository, RevisionRepository, IdempotencyRepository, Protocol
):
    """Atomic create/append boundary implemented by each durable adapter."""

    def create_statblock(
        self, command: "CreateStatblockCommand"
    ) -> tuple[StatblockResourceV1, StatblockRevisionResourceV1]: ...

    def append_revision(
        self, command: "AppendRevisionCommand"
    ) -> StatblockRevisionResourceV1: ...


class CreateStatblockCommand:
    def __init__(
        self,
        *,
        caller_scope: str,
        idempotency_key: str,
        definition: StatblockDefinitionV1,
        created_by: str,
        provenance: dict[str, Any] | None = None,
        asset_bindings: list[dict[str, Any]] | None = None,
        candidate_id: str | None = None,
    ) -> None:
        self.caller_scope = caller_scope
        self.idempotency_key = idempotency_key
        self.definition = definition
        self.created_by = created_by
        self.provenance = provenance or {}
        self.asset_bindings = asset_bindings or []
        self.candidate_id = candidate_id

    @property
    def request_digest(self) -> str:
        return compute_request_digest(
            "create_statblock",
            {
                "definition_canonical": str(canonicalize_definition(self.definition)),
                "created_by": self.created_by,
                "provenance": self.provenance,
                "asset_bindings": self.asset_bindings,
                "candidate_id": self.candidate_id,
            },
        )


class AppendRevisionCommand:
    def __init__(
        self,
        *,
        caller_scope: str,
        idempotency_key: str,
        statblock_id: str,
        parent_revision_id: str,
        definition: StatblockDefinitionV1,
        provenance: dict[str, Any] | None = None,
        asset_bindings: list[dict[str, Any]] | None = None,
        candidate_id: str | None = None,
    ) -> None:
        self.caller_scope = caller_scope
        self.idempotency_key = idempotency_key
        self.statblock_id = statblock_id
        self.parent_revision_id = parent_revision_id
        self.definition = definition
        self.provenance = provenance or {}
        self.asset_bindings = asset_bindings or []
        self.candidate_id = candidate_id

    @property
    def request_digest(self) -> str:
        return compute_request_digest(
            "append_revision",
            {
                "statblock_id": self.statblock_id,
                "parent_revision_id": self.parent_revision_id,
                "definition_canonical": str(canonicalize_definition(self.definition)),
                "provenance": self.provenance,
                "asset_bindings": self.asset_bindings,
                "candidate_id": self.candidate_id,
            },
        )


Clock = Callable[[], datetime]
