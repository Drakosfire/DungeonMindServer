"""Transport-neutral synchronous repository protocols and persistence commands.

Firestore's Python client is blocking.  These protocols intentionally expose
synchronous methods; async API code must call them with ``asyncio.to_thread``.
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from statblocks_v1.application.commands import GenerateStatblockCommandV1
from statblocks_v1.domain.assets import AssetBindingV1
from statblocks_v1.domain.candidate_operations import (
    GENERATE_CANDIDATE_OPERATION,
    CandidateGenerationFailureSnapshotV1,
    CandidateGenerationOperationV1,
    CandidateGenerationStatusV1,
)
from statblocks_v1.domain.canonicalization import canonicalize_definition
from statblocks_v1.domain.errors import (
    AmbiguousRequestPayloadError,
    GenerateOperationIntegrityError,
)
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
    Distinct map keys that collide after NFC normalization fail closed.
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
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            nfc_key = unicodedata.normalize("NFC", str(key))
            if nfc_key in normalized:
                raise AmbiguousRequestPayloadError(nfc_key)
            normalized[nfc_key] = _normalize_request_payload(item)
        return {key: normalized[key] for key in sorted(normalized)}
    if isinstance(value, list):
        return [_normalize_request_payload(item) for item in value]
    return value


def _idempotency_provenance(provenance: Mapping[str, Any]) -> dict[str, Any]:
    """Exclude server-owned candidate audit evidence from the request digest.

    ``candidate_id`` is hashed separately. Replay must not require the live
    candidate document after Firestore TTL deletion.
    """

    return {key: value for key, value in provenance.items() if key != "candidate"}


def _dump_asset_bindings(bindings: list[AssetBindingV1]) -> list[dict[str, Any]]:
    return [binding.model_dump(mode="json") for binding in bindings]


class CandidateRepository(Protocol):
    def create(self, candidate: GeneratedStatblockCandidateV1) -> GeneratedStatblockCandidateV1: ...
    def get(self, candidate_id: str, *, now: datetime | None = None) -> GeneratedStatblockCandidateV1: ...

    def get_for_acceptance(self, candidate_id: str) -> GeneratedStatblockCandidateV1:
        """Load retained candidate audit data without applying workflow expiry."""
        ...


def compute_generate_candidate_digest(command: GenerateStatblockCommandV1) -> str:
    """Digest caller-controlled generate intent. ``request_id`` is the durable key, not digested."""

    return compute_request_digest(
        GENERATE_CANDIDATE_OPERATION,
        {
            "ruleset": command.ruleset.model_dump(mode="json"),
            "source": command.source.model_dump(mode="json"),
            "intent": command.intent.model_dump(mode="json"),
            "context": command.context.model_dump(mode="json"),
            "asset_options": command.asset_options.model_dump(mode="json"),
            "actor": command.caller.actor,
        },
    )


def candidate_belongs_to_generate_operation(
    candidate: GeneratedStatblockCandidateV1,
    operation: CandidateGenerationOperationV1,
) -> bool:
    """True only when the stored candidate was produced for this generate operation.

    Same-operation stale-worker convergence is valid. An unrelated or recreated
    document that happens to share ``candidate_id`` must fail closed. Binding
    includes ``request_digest`` so a replaced document under the same ID cannot
    be treated as canonical for a different generate intent.
    """

    if candidate.candidate_id != operation.candidate_id:
        return False
    receipt = candidate.generation_receipt
    if receipt is None or receipt.request_digest is None:
        return False
    return (
        receipt.request_id == operation.request_id
        and receipt.caller_scope == operation.caller_scope
        and receipt.request_digest == operation.request_digest
    )


def verify_generate_operation_lookup_identity(
    record: CandidateGenerationOperationV1,
    *,
    caller_scope: str,
    request_id: str,
) -> CandidateGenerationOperationV1:
    """Fail closed when stored identity/state does not match the hashed lookup key."""

    if (
        record.caller_scope != caller_scope
        or record.request_id != request_id
        or record.operation != GENERATE_CANDIDATE_OPERATION
    ):
        raise GenerateOperationIntegrityError(
            request_id,
            candidate_id=record.candidate_id,
            reason="Stored generate operation identity does not match lookup key",
        )
    if record.status is CandidateGenerationStatusV1.pending:
        if (
            record.failure is not None
            or record.candidate_expires_at is not None
            or record.completed_at is not None
        ):
            raise GenerateOperationIntegrityError(
                request_id,
                candidate_id=record.candidate_id,
                reason="Pending generate operation carries terminal fields",
            )
    elif record.status is CandidateGenerationStatusV1.completed:
        if record.candidate_expires_at is None:
            raise GenerateOperationIntegrityError(
                request_id,
                candidate_id=record.candidate_id,
                reason="Completed generate operation is missing candidate_expires_at",
            )
        if record.failure is not None:
            raise GenerateOperationIntegrityError(
                request_id,
                candidate_id=record.candidate_id,
                reason="Completed generate operation must not carry failure",
            )
        if record.completed_at is None:
            raise GenerateOperationIntegrityError(
                request_id,
                candidate_id=record.candidate_id,
                reason="Completed generate operation is missing completed_at",
            )
    elif record.status is CandidateGenerationStatusV1.failed:
        if record.failure is None:
            raise GenerateOperationIntegrityError(
                request_id,
                candidate_id=record.candidate_id,
                reason="Failed generate operation is missing failure",
            )
        if record.candidate_expires_at is not None:
            raise GenerateOperationIntegrityError(
                request_id,
                candidate_id=record.candidate_id,
                reason="Failed generate operation must not carry candidate_expires_at",
            )
        if record.completed_at is None:
            raise GenerateOperationIntegrityError(
                request_id,
                candidate_id=record.candidate_id,
                reason="Failed generate operation is missing completed_at",
            )
    return record


@dataclass(frozen=True)
class GenerateBeginClaimed:
    """Caller owns a pending lease and must run generation against ``candidate_id``."""

    operation: CandidateGenerationOperationV1


@dataclass(frozen=True)
class GenerateBeginCompleted:
    """Durable completed operation; replay must verify candidate ownership."""

    operation: CandidateGenerationOperationV1

    @property
    def candidate_id(self) -> str:
        return self.operation.candidate_id

    @property
    def candidate_expires_at(self) -> datetime | None:
        return self.operation.candidate_expires_at


@dataclass(frozen=True)
class GenerateBeginFailed:
    failure: CandidateGenerationFailureSnapshotV1


@dataclass(frozen=True)
class GenerateBeginInProgress:
    candidate_id: str
    lease_expires_at: datetime


@dataclass(frozen=True)
class GenerateCompleteResult:
    """Outcome of complete_generate with fresh-vs-convergence observability."""

    candidate: GeneratedStatblockCandidateV1
    already_completed: bool


GenerateBeginResult = (
    GenerateBeginClaimed
    | GenerateBeginCompleted
    | GenerateBeginFailed
    | GenerateBeginInProgress
)


class CandidateGenerationOperationRepository(Protocol):
    """Durable generate-request reservation, completion, and terminal-failure store."""

    def get_generate_operation(
        self, caller_scope: str, request_id: str
    ) -> CandidateGenerationOperationV1 | None: ...

    def begin_generate(
        self,
        *,
        caller_scope: str,
        request_id: str,
        request_digest: str,
        candidate_id_factory: Callable[[], str],
        lease_owner: str,
        lease_duration_seconds: int,
    ) -> GenerateBeginResult: ...

    def complete_generate(
        self,
        *,
        caller_scope: str,
        request_id: str,
        request_digest: str,
        lease_owner: str,
        candidate: GeneratedStatblockCandidateV1,
    ) -> GenerateCompleteResult: ...

    def fail_generate(
        self,
        *,
        caller_scope: str,
        request_id: str,
        request_digest: str,
        lease_owner: str,
        failure: CandidateGenerationFailureSnapshotV1,
    ) -> CandidateGenerationFailureSnapshotV1: ...


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
    """Immutable create intent: inputs are snapshotted and the digest is fixed."""

    __slots__ = (
        "caller_scope",
        "idempotency_key",
        "created_by",
        "candidate_id",
        "_definition",
        "_provenance",
        "_asset_bindings",
        "_request_digest",
    )

    def __init__(
        self,
        *,
        caller_scope: str,
        idempotency_key: str,
        definition: StatblockDefinitionV1,
        created_by: str,
        provenance: dict[str, Any] | None = None,
        asset_bindings: list[AssetBindingV1] | None = None,
        candidate_id: str | None = None,
    ) -> None:
        object.__setattr__(self, "caller_scope", caller_scope)
        object.__setattr__(self, "idempotency_key", idempotency_key)
        object.__setattr__(self, "created_by", created_by)
        object.__setattr__(self, "candidate_id", candidate_id)
        object.__setattr__(self, "_definition", definition.model_copy(deep=True))
        object.__setattr__(self, "_provenance", deepcopy(provenance or {}))
        object.__setattr__(self, "_asset_bindings", deepcopy(asset_bindings or []))
        object.__setattr__(
            self,
            "_request_digest",
            compute_request_digest(
                "create_statblock",
                {
                    "definition_canonical": str(
                        canonicalize_definition(self._definition)
                    ),
                    "created_by": created_by,
                    "provenance": _idempotency_provenance(self._provenance),
                    "asset_bindings": _dump_asset_bindings(self._asset_bindings),
                    "candidate_id": candidate_id,
                },
            ),
        )

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("CreateStatblockCommand is immutable after construction")

    @property
    def definition(self) -> StatblockDefinitionV1:
        return self._definition.model_copy(deep=True)

    @property
    def provenance(self) -> dict[str, Any]:
        return deepcopy(self._provenance)

    @property
    def asset_bindings(self) -> list[AssetBindingV1]:
        return deepcopy(self._asset_bindings)

    @property
    def request_digest(self) -> str:
        return self._request_digest


class AppendRevisionCommand:
    """Immutable append intent: inputs are snapshotted and the digest is fixed."""

    __slots__ = (
        "caller_scope",
        "idempotency_key",
        "statblock_id",
        "parent_revision_id",
        "candidate_id",
        "_definition",
        "_provenance",
        "_asset_bindings",
        "_request_digest",
    )

    def __init__(
        self,
        *,
        caller_scope: str,
        idempotency_key: str,
        statblock_id: str,
        parent_revision_id: str,
        definition: StatblockDefinitionV1,
        provenance: dict[str, Any] | None = None,
        asset_bindings: list[AssetBindingV1] | None = None,
        candidate_id: str | None = None,
    ) -> None:
        object.__setattr__(self, "caller_scope", caller_scope)
        object.__setattr__(self, "idempotency_key", idempotency_key)
        object.__setattr__(self, "statblock_id", statblock_id)
        object.__setattr__(self, "parent_revision_id", parent_revision_id)
        object.__setattr__(self, "candidate_id", candidate_id)
        object.__setattr__(self, "_definition", definition.model_copy(deep=True))
        object.__setattr__(self, "_provenance", deepcopy(provenance or {}))
        object.__setattr__(self, "_asset_bindings", deepcopy(asset_bindings or []))
        object.__setattr__(
            self,
            "_request_digest",
            compute_request_digest(
                "append_revision",
                {
                    "statblock_id": statblock_id,
                    "parent_revision_id": parent_revision_id,
                    "definition_canonical": str(
                        canonicalize_definition(self._definition)
                    ),
                    "provenance": _idempotency_provenance(self._provenance),
                    "asset_bindings": _dump_asset_bindings(self._asset_bindings),
                    "candidate_id": candidate_id,
                },
            ),
        )

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("AppendRevisionCommand is immutable after construction")

    @property
    def definition(self) -> StatblockDefinitionV1:
        return self._definition.model_copy(deep=True)

    @property
    def provenance(self) -> dict[str, Any]:
        return deepcopy(self._provenance)

    @property
    def asset_bindings(self) -> list[AssetBindingV1]:
        return deepcopy(self._asset_bindings)

    @property
    def request_digest(self) -> str:
        return self._request_digest


Clock = Callable[[], datetime]
