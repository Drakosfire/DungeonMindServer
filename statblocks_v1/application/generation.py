"""Application service for generation and revision candidate workflows."""
from __future__ import annotations

import hashlib
import math
import os
import re
import secrets
import time
import unicodedata
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from pydantic import ValidationError

from statblocks_v1.application.assets import AssetGateway
from statblocks_v1.application.commands import (
    CallerProvenanceV1,
    GenerateStatblockCommandV1,
    ReviseStatblockCommandV1,
    SourceSnapshotV1,
)
from statblocks_v1.application.prompts import PROMPT_VERSION, build_generation_prompt, build_revision_prompt
from statblocks_v1.application.provider import (
    DefinitionProvider,
    ProviderOptionsV1,
    ProviderOutcomeKind,
)
from statblocks_v1.application.repositories import (
    CandidateGenerationOperationRepository,
    CandidateRevisionOperationRepository,
    CandidateRepository,
    GenerateBeginClaimed,
    GenerateBeginCompleted,
    GenerateBeginFailed,
    GenerateBeginInProgress,
    ReviseBeginClaimed,
    ReviseBeginCompleted,
    ReviseBeginFailed,
    ReviseBeginInProgress,
    candidate_belongs_to_generate_operation,
    candidate_belongs_to_revise_operation,
    compute_generate_candidate_digest,
    compute_revise_candidate_digest,
)
from statblocks_v1.application.schema_compiler import compile_openai_definition_schema
from statblocks_v1.application.settings import GenerationSettingsV1
from statblocks_v1.domain.assets import AssetBriefV1, AssetRefV1
from statblocks_v1.domain.candidate_operations import (
    CandidateGenerationFailureSnapshotV1,
    CandidateGenerationOperationV1,
    CandidateRevisionOperationV1,
    GenerationValidationDiagnosticIssueV1,
    GenerationValidationDiagnosticPacketV1,
    GenerationValidationPhaseV1,
    MAX_GENERATION_VALIDATION_CODE_LEN,
    MAX_GENERATION_VALIDATION_DIAGNOSTIC_ISSUES,
    MAX_GENERATION_VALIDATION_FIELD_PATH_LEN,
    MAX_GENERATION_VALIDATION_MESSAGE_LEN,
    MAX_GENERATION_VALIDATION_SUGGESTED_RESOLUTION_LEN,
)
from statblocks_v1.domain.digests import compute_definition_digest
from statblocks_v1.domain.errors import (
    CandidateExpiredError,
    CandidateMissingBeforeExpiryError,
    CandidateNotFoundError,
    GenerateOperationIntegrityError,
    ReviseOperationIntegrityError,
    IdempotencyConflictError,
    ImmutableResourceConflictError,
    PersistenceUnavailableError,
    StatblockV1Error,
    TransactionIndeterminateError,
)
from statblocks_v1.domain.profiles import RulesetRef
from statblocks_v1.domain.receipts import (
    ValidationIssueV1,
    ValidationMode,
    ValidationReceiptV1,
    ValidationSeverity,
    ValidationStatus,
)
from statblocks_v1.domain.resources import (
    STATBLOCK_CONTRACT,
    STATBLOCK_CONTRACT_VERSION,
    AssetWarningCode,
    AssetWarningV1,
    ExactRevisionLocatorV1,
    GeneratedStatblockCandidateV1,
    GenerationReceiptV1,
)
from statblocks_v1.domain.rule_elements import RuleElement, StatblockDefinitionV1
from statblocks_v1.domain.validation import validate_definition

Clock = Callable[[], datetime]
CandidateIdFactory = Callable[[], str]
LeaseOwnerFactory = Callable[[], str]

KEY_PRESERVATION_PASS_VERSION = "statblock-key-preservation-v1"


class DefinitionResolver(Protocol):
    def resolve(self, locator: ExactRevisionLocatorV1) -> StatblockDefinitionV1: ...


@dataclass(frozen=True)
class GenerationFailureV1:
    kind: str
    message: str
    diagnostics: GenerationValidationDiagnosticPacketV1 | None = None


@dataclass(frozen=True)
class GenerateOutcomeV1:
    """Successful generate result with fresh-versus-replay observability."""

    candidate: GeneratedStatblockCandidateV1
    replayed: bool

    def __getattr__(self, name: str) -> object:
        return getattr(self.candidate, name)


GenerationResultV1 = GeneratedStatblockCandidateV1 | GenerationFailureV1 | GenerateOutcomeV1


@dataclass(frozen=True)
class _PinnedOperationIntent:
    """Caller-independent operation intent, snapshotted before the provider call.

    Nested models are deep-copied at construction so concurrent mutation of the
    original command cannot change prompt, digests, ruleset, caller, locator,
    key-preservation inputs, or asset intent after the operation starts.
    ``request_id``, ``caller_scope``, and ``request_digest`` are frozen here so
    idempotent generate never re-reads identity from the mutable command.
    """

    request_id: str
    request_digest: str | None
    ruleset: RulesetRef
    caller: CallerProvenanceV1
    prompt: str
    source_description_digest: str | None
    source_definition_digest: str | None
    source_locator: ExactRevisionLocatorV1 | None
    source_definition: StatblockDefinitionV1 | None
    preserve_element_keys: bool
    asset_prompt: str | None
    generate_assets: bool
    include_generation_brief: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "ruleset", self.ruleset.model_copy(deep=True))
        object.__setattr__(self, "caller", self.caller.model_copy(deep=True))
        if self.source_locator is not None:
            object.__setattr__(
                self, "source_locator", self.source_locator.model_copy(deep=True)
            )
        if self.source_definition is not None:
            object.__setattr__(
                self, "source_definition", self.source_definition.model_copy(deep=True)
            )


class GenerationServiceV1:
    """Coordinates provider output without letting provider metadata enter the definition."""

    def __init__(
        self,
        *,
        provider: DefinitionProvider,
        candidates: CandidateRepository,
        settings: GenerationSettingsV1,
        clock: Clock | None = None,
        candidate_id_factory: CandidateIdFactory | None = None,
        definition_resolver: DefinitionResolver | None = None,
        asset_gateway: AssetGateway | None = None,
        generate_operations: CandidateGenerationOperationRepository | None = None,
        revise_operations: CandidateRevisionOperationRepository | None = None,
        lease_owner_factory: LeaseOwnerFactory | None = None,
        generate_lease_seconds: int | None = None,
        revise_lease_seconds: int | None = None,
    ) -> None:
        self._provider = provider
        self._candidates = candidates
        self._settings = settings
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._candidate_id_factory = candidate_id_factory or _new_candidate_id
        self._definition_resolver = definition_resolver
        self._asset_gateway = asset_gateway
        self._generate_operations = generate_operations
        self._revise_operations = revise_operations
        self._lease_owner_factory = lease_owner_factory or (lambda: f"lease_{uuid.uuid4().hex}")
        self._generate_lease_seconds = (
            generate_lease_seconds
            if generate_lease_seconds is not None
            else _default_generate_lease_seconds(settings)
        )
        self._revise_lease_seconds = (
            revise_lease_seconds
            if revise_lease_seconds is not None
            else _default_generate_lease_seconds(settings)
        )

    def generate(self, command: GenerateStatblockCommandV1) -> GenerationResultV1:
        pinned = _pin_generate_intent(command)
        if isinstance(pinned, GenerationFailureV1):
            return pinned
        # Fail closed: never allocate a candidate without durable idempotency.
        if self._generate_operations is None:
            return GenerationFailureV1(
                "persistence_unavailable",
                "Candidate generate-operation repository is not configured",
            )
        return self._generate_idempotent(pinned)

    def revise(self, command: ReviseStatblockCommandV1) -> GenerationResultV1:
        # Authority pin only: digest + XOR/basic shape. Locator resolution and
        # provider work happen only after begin_revise returns ReviseBeginClaimed,
        # so completed/conflict authority wins over transient source unreadability.
        authority = _pin_revise_authority(command)
        if isinstance(authority, GenerationFailureV1):
            return authority
        if self._revise_operations is None:
            return GenerationFailureV1(
                "persistence_unavailable",
                "Candidate revise-operation repository is not configured",
            )
        return self._revise_idempotent(authority)

    def _generate_idempotent(self, pinned: _PinnedOperationIntent) -> GenerationResultV1:
        assert self._generate_operations is not None
        assert pinned.request_digest is not None
        ops = self._generate_operations
        request_id = pinned.request_id
        request_digest = pinned.request_digest
        caller_scope = pinned.caller.caller_scope

        lease_owner = self._lease_owner_factory()
        try:
            began = ops.begin_generate(
                caller_scope=caller_scope,
                request_id=request_id,
                request_digest=request_digest,
                candidate_id_factory=self._candidate_id_factory,
                lease_owner=lease_owner,
                lease_duration_seconds=self._generate_lease_seconds,
            )
        except (IdempotencyConflictError, GenerateOperationIntegrityError):
            raise
        except PersistenceUnavailableError:
            return GenerationFailureV1(
                "persistence_unavailable", "Persistence is unavailable"
            )
        except Exception:
            return GenerationFailureV1(
                "persistence_unavailable", "Persistence is unavailable"
            )

        if isinstance(began, GenerateBeginCompleted):
            loaded = self._load_completed_candidate(began.operation)
            if isinstance(loaded, GenerationFailureV1):
                return loaded
            return GenerateOutcomeV1(candidate=loaded, replayed=True)
        if isinstance(began, GenerateBeginFailed):
            return _generation_failure_from_snapshot(began.failure)
        if isinstance(began, GenerateBeginInProgress):
            return GenerationFailureV1(
                "generation_in_progress",
                "Candidate generation is already in progress for this request",
            )
        if not isinstance(began, GenerateBeginClaimed):
            return GenerationFailureV1(
                "persistence_unavailable", "Persistence returned an unexpected begin state"
            )

        claim = began.operation
        lease_owner = claim.lease_owner
        result = self._run(pinned, reserved_candidate_id=claim.candidate_id, persist=False)
        if isinstance(result, GenerationFailureV1):
            try:
                snapshot = ops.fail_generate(
                    caller_scope=caller_scope,
                    request_id=request_id,
                    request_digest=request_digest,
                    lease_owner=lease_owner,
                    failure=_failure_snapshot_from_generation_failure(result),
                )
            except ImmutableResourceConflictError:
                return self._resolve_after_terminal_race(
                    caller_scope=caller_scope,
                    request_id=request_id,
                    request_digest=request_digest,
                    reserved_candidate_id=claim.candidate_id,
                )
            except TransactionIndeterminateError:
                return self._resolve_after_terminal_race(
                    caller_scope=caller_scope,
                    request_id=request_id,
                    request_digest=request_digest,
                    reserved_candidate_id=claim.candidate_id,
                    indeterminate=True,
                )
            except PersistenceUnavailableError:
                return GenerationFailureV1(
                    "persistence_unavailable", "Persistence is unavailable"
                )
            except IdempotencyConflictError:
                raise
            except GenerateOperationIntegrityError:
                raise
            return _generation_failure_from_snapshot(snapshot)

        try:
            completed = ops.complete_generate(
                caller_scope=caller_scope,
                request_id=request_id,
                request_digest=request_digest,
                lease_owner=lease_owner,
                candidate=result,
            )
        except ImmutableResourceConflictError:
            return self._resolve_after_terminal_race(
                caller_scope=caller_scope,
                request_id=request_id,
                request_digest=request_digest,
                reserved_candidate_id=claim.candidate_id,
            )
        except TransactionIndeterminateError:
            return self._resolve_after_terminal_race(
                caller_scope=caller_scope,
                request_id=request_id,
                request_digest=request_digest,
                reserved_candidate_id=claim.candidate_id,
                indeterminate=True,
            )
        except (PersistenceUnavailableError, CandidateNotFoundError):
            # Prefer durable completed-op expiry/premature-loss authority over a
            # generic unavailable mapping when the operation already committed.
            return self._resolve_after_terminal_race(
                caller_scope=caller_scope,
                request_id=request_id,
                request_digest=request_digest,
                reserved_candidate_id=claim.candidate_id,
                indeterminate=True,
            )
        except GenerateOperationIntegrityError:
            raise
        # Never return the repository candidate verbatim: apply the same
        # operation-expiry + premature-loss semantics as completed replay.
        return self._outcome_from_completed_generate(
            caller_scope=caller_scope,
            request_id=request_id,
            request_digest=request_digest,
            reserved_candidate_id=claim.candidate_id,
            replayed=completed.already_completed,
        )

    def _outcome_from_completed_generate(
        self,
        *,
        caller_scope: str,
        request_id: str,
        request_digest: str,
        reserved_candidate_id: str,
        replayed: bool,
    ) -> GenerationResultV1:
        """Apply authoritative expiry after repository complete/reconcile success.

        Reloaded completed state must still match this attempt's reserved candidate
        and pinned request digest before any candidate is returned (same binding
        checks as terminal-race reconciliation).
        """

        assert self._generate_operations is not None
        existing = self._generate_operations.get_generate_operation(
            caller_scope, request_id
        )
        if existing is None:
            return GenerationFailureV1(
                "persistence_unavailable", "Persistence is unavailable"
            )
        if existing.candidate_id != reserved_candidate_id:
            raise GenerateOperationIntegrityError(
                request_id,
                candidate_id=existing.candidate_id,
                reason=(
                    "Completed generate operation candidate_id does not match "
                    "this attempt's reservation"
                ),
            )
        if existing.request_digest != request_digest:
            raise GenerateOperationIntegrityError(
                request_id,
                candidate_id=existing.candidate_id,
                reason=(
                    "Completed generate operation request_digest does not match "
                    "this attempt's pinned digest"
                ),
            )
        if existing.status.value != "completed":
            raise GenerateOperationIntegrityError(
                request_id,
                candidate_id=existing.candidate_id,
                reason=(
                    "Generate completion reported success without a completed "
                    "operation record"
                ),
            )
        loaded = self._load_completed_candidate(existing)
        if isinstance(loaded, GenerationFailureV1):
            return loaded
        return GenerateOutcomeV1(candidate=loaded, replayed=replayed)

    def _resolve_after_terminal_race(
        self,
        *,
        caller_scope: str,
        request_id: str,
        request_digest: str,
        reserved_candidate_id: str,
        indeterminate: bool = False,
    ) -> GenerationResultV1:
        """Reconcile when this worker lost the lease or lost a terminal race.

        Reloaded terminal state must still match this attempt's reserved candidate
        and pinned request digest before any completed candidate is returned.
        """

        assert self._generate_operations is not None
        existing = self._generate_operations.get_generate_operation(
            caller_scope, request_id
        )
        if existing is None:
            return GenerationFailureV1(
                "persistence_unavailable", "Persistence is unavailable"
            )
        if existing.candidate_id != reserved_candidate_id:
            raise GenerateOperationIntegrityError(
                request_id,
                candidate_id=existing.candidate_id,
                reason=(
                    "Terminal generate operation candidate_id does not match "
                    "this attempt's reservation"
                ),
            )
        if existing.request_digest != request_digest:
            raise GenerateOperationIntegrityError(
                request_id,
                candidate_id=existing.candidate_id,
                reason=(
                    "Terminal generate operation request_digest does not match "
                    "this attempt's pinned digest"
                ),
            )
        if existing.status.value == "completed":
            loaded = self._load_completed_candidate(existing)
            if isinstance(loaded, GenerationFailureV1):
                return loaded
            return GenerateOutcomeV1(candidate=loaded, replayed=True)
        if existing.status.value == "failed" and existing.failure is not None:
            return _generation_failure_from_snapshot(existing.failure)
        if existing.status.value == "pending":
            if indeterminate:
                return GenerationFailureV1(
                    "persistence_unavailable", "Persistence is unavailable"
                )
            return GenerationFailureV1(
                "generation_in_progress",
                "Candidate generation is already in progress for this request",
            )
        return GenerationFailureV1(
            "persistence_unavailable", "Persistence is unavailable"
        )

    def _load_completed_candidate(
        self,
        operation: CandidateGenerationOperationV1,
    ) -> GenerationResultV1:
        """Load a completed generate's candidate, verifying operation binding.

        Load and verify the retained candidate before applying authoritative
        ``operation.candidate_expires_at``. A present candidate whose
        ``expires_at`` disagrees with the operation must fail closed as
        integrity — never as ordinary 410 — even when the operation expiry is
        already past. Document TTL alone must not short-circuit before
        ownership / expiry-agreement checks.
        """

        if operation.candidate_expires_at is None:
            raise GenerateOperationIntegrityError(
                operation.request_id,
                candidate_id=operation.candidate_id,
                reason="Completed generate operation is missing candidate_expires_at",
            )
        candidate_id = operation.candidate_id
        candidate_expires_at = operation.candidate_expires_at
        now = self._clock()

        try:
            # Do not enforce candidate-document TTL here: a foreign/replaced
            # document with an earlier expires_at must not short-circuit to 410
            # before ownership validation.
            candidate = self._candidates.get_for_acceptance(candidate_id)
        except CandidateNotFoundError as error:
            # Truly missing: only then is operation expiry an ordinary 410.
            if now >= candidate_expires_at:
                raise CandidateExpiredError(candidate_id) from error
            raise CandidateMissingBeforeExpiryError(
                error.details.get("candidate_id", candidate_id)
            ) from error
        except PersistenceUnavailableError:
            return GenerationFailureV1(
                "persistence_unavailable", "Persistence is unavailable"
            )
        if not candidate_belongs_to_generate_operation(candidate, operation):
            raise GenerateOperationIntegrityError(
                operation.request_id,
                candidate_id=candidate_id,
                reason=(
                    "Completed generate points to a candidate that does not belong "
                    "to this operation"
                ),
            )
        if _as_utc(candidate.expires_at) != _as_utc(candidate_expires_at):
            raise GenerateOperationIntegrityError(
                operation.request_id,
                candidate_id=candidate_id,
                reason=(
                    "Completed generate candidate.expires_at does not match "
                    "operation.candidate_expires_at"
                ),
            )
        if now >= candidate_expires_at:
            raise CandidateExpiredError(candidate_id)
        return candidate

    def _revise_idempotent(self, authority: "_ReviseAuthorityPin") -> GenerationResultV1:
        assert self._revise_operations is not None
        ops = self._revise_operations
        request_id = authority.snapshot.request_id
        request_digest = authority.request_digest
        caller_scope = authority.snapshot.caller.caller_scope

        lease_owner = self._lease_owner_factory()
        try:
            began = ops.begin_revise(
                caller_scope=caller_scope,
                request_id=request_id,
                request_digest=request_digest,
                candidate_id_factory=self._candidate_id_factory,
                lease_owner=lease_owner,
                lease_duration_seconds=self._revise_lease_seconds,
            )
        except (IdempotencyConflictError, ReviseOperationIntegrityError):
            raise
        except PersistenceUnavailableError:
            return GenerationFailureV1(
                "persistence_unavailable", "Persistence is unavailable"
            )
        except Exception:
            return GenerationFailureV1(
                "persistence_unavailable", "Persistence is unavailable"
            )

        if isinstance(began, ReviseBeginCompleted):
            loaded = self._load_completed_revise_candidate(began.operation)
            if isinstance(loaded, GenerationFailureV1):
                return loaded
            return GenerateOutcomeV1(candidate=loaded, replayed=True)
        if isinstance(began, ReviseBeginFailed):
            return _generation_failure_from_snapshot(began.failure)
        if isinstance(began, ReviseBeginInProgress):
            return GenerationFailureV1(
                "generation_in_progress",
                "Candidate generation is already in progress for this request",
            )
        if not isinstance(began, ReviseBeginClaimed):
            return GenerationFailureV1(
                "persistence_unavailable", "Persistence returned an unexpected begin state"
            )

        claim = began.operation
        lease_owner = claim.lease_owner
        # Locator / definition resolution happens only after a durable claim.
        pinned = _materialize_revise_intent(authority, self._definition_resolver)
        if isinstance(pinned, GenerationFailureV1):
            try:
                snapshot = ops.fail_revise(
                    caller_scope=caller_scope,
                    request_id=request_id,
                    request_digest=request_digest,
                    lease_owner=lease_owner,
                    failure=_failure_snapshot_from_generation_failure(pinned),
                )
            except ImmutableResourceConflictError:
                return self._resolve_after_terminal_race_revise(
                    caller_scope=caller_scope,
                    request_id=request_id,
                    request_digest=request_digest,
                    reserved_candidate_id=claim.candidate_id,
                )
            except TransactionIndeterminateError:
                return self._resolve_after_terminal_race_revise(
                    caller_scope=caller_scope,
                    request_id=request_id,
                    request_digest=request_digest,
                    reserved_candidate_id=claim.candidate_id,
                    indeterminate=True,
                )
            except PersistenceUnavailableError:
                return GenerationFailureV1(
                    "persistence_unavailable", "Persistence is unavailable"
                )
            except IdempotencyConflictError:
                raise
            except ReviseOperationIntegrityError:
                raise
            return _generation_failure_from_snapshot(snapshot)
        result = self._run(pinned, reserved_candidate_id=claim.candidate_id, persist=False)
        if isinstance(result, GenerationFailureV1):
            try:
                snapshot = ops.fail_revise(
                    caller_scope=caller_scope,
                    request_id=request_id,
                    request_digest=request_digest,
                    lease_owner=lease_owner,
                    failure=_failure_snapshot_from_generation_failure(result),
                )
            except ImmutableResourceConflictError:
                return self._resolve_after_terminal_race_revise(
                    caller_scope=caller_scope,
                    request_id=request_id,
                    request_digest=request_digest,
                    reserved_candidate_id=claim.candidate_id,
                )
            except TransactionIndeterminateError:
                return self._resolve_after_terminal_race_revise(
                    caller_scope=caller_scope,
                    request_id=request_id,
                    request_digest=request_digest,
                    reserved_candidate_id=claim.candidate_id,
                    indeterminate=True,
                )
            except PersistenceUnavailableError:
                return GenerationFailureV1(
                    "persistence_unavailable", "Persistence is unavailable"
                )
            except IdempotencyConflictError:
                raise
            except ReviseOperationIntegrityError:
                raise
            return _generation_failure_from_snapshot(snapshot)

        try:
            completed = ops.complete_revise(
                caller_scope=caller_scope,
                request_id=request_id,
                request_digest=request_digest,
                lease_owner=lease_owner,
                candidate=result,
            )
        except ImmutableResourceConflictError:
            return self._resolve_after_terminal_race_revise(
                caller_scope=caller_scope,
                request_id=request_id,
                request_digest=request_digest,
                reserved_candidate_id=claim.candidate_id,
            )
        except TransactionIndeterminateError:
            return self._resolve_after_terminal_race_revise(
                caller_scope=caller_scope,
                request_id=request_id,
                request_digest=request_digest,
                reserved_candidate_id=claim.candidate_id,
                indeterminate=True,
            )
        except (PersistenceUnavailableError, CandidateNotFoundError):
            # Prefer durable completed-op expiry/premature-loss authority over a
            # generic unavailable mapping when the operation already committed.
            return self._resolve_after_terminal_race_revise(
                caller_scope=caller_scope,
                request_id=request_id,
                request_digest=request_digest,
                reserved_candidate_id=claim.candidate_id,
                indeterminate=True,
            )
        except ReviseOperationIntegrityError:
            raise
        # Never return the repository candidate verbatim: apply the same
        # operation-expiry + premature-loss semantics as completed replay.
        return self._outcome_from_completed_revise(
            caller_scope=caller_scope,
            request_id=request_id,
            request_digest=request_digest,
            reserved_candidate_id=claim.candidate_id,
            replayed=completed.already_completed,
        )

    def _outcome_from_completed_revise(
        self,
        *,
        caller_scope: str,
        request_id: str,
        request_digest: str,
        reserved_candidate_id: str,
        replayed: bool,
    ) -> GenerationResultV1:
        """Apply authoritative expiry after repository complete/reconcile success.

        Reloaded completed state must still match this attempt's reserved candidate
        and pinned request digest before any candidate is returned (same binding
        checks as terminal-race reconciliation).
        """

        assert self._revise_operations is not None
        existing = self._revise_operations.get_revise_operation(
            caller_scope, request_id
        )
        if existing is None:
            return GenerationFailureV1(
                "persistence_unavailable", "Persistence is unavailable"
            )
        if existing.candidate_id != reserved_candidate_id:
            raise ReviseOperationIntegrityError(
                request_id,
                candidate_id=existing.candidate_id,
                reason=(
                    "Completed revise operation candidate_id does not match "
                    "this attempt's reservation"
                ),
            )
        if existing.request_digest != request_digest:
            raise ReviseOperationIntegrityError(
                request_id,
                candidate_id=existing.candidate_id,
                reason=(
                    "Completed revise operation request_digest does not match "
                    "this attempt's pinned digest"
                ),
            )
        if existing.status.value != "completed":
            raise ReviseOperationIntegrityError(
                request_id,
                candidate_id=existing.candidate_id,
                reason=(
                    "Revise completion reported success without a completed "
                    "operation record"
                ),
            )
        loaded = self._load_completed_revise_candidate(existing)
        if isinstance(loaded, GenerationFailureV1):
            return loaded
        return GenerateOutcomeV1(candidate=loaded, replayed=replayed)

    def _resolve_after_terminal_race_revise(
        self,
        *,
        caller_scope: str,
        request_id: str,
        request_digest: str,
        reserved_candidate_id: str,
        indeterminate: bool = False,
    ) -> GenerationResultV1:
        """Reconcile when this worker lost the lease or lost a terminal race.

        Reloaded terminal state must still match this attempt's reserved candidate
        and pinned request digest before any completed candidate is returned.
        """

        assert self._revise_operations is not None
        existing = self._revise_operations.get_revise_operation(
            caller_scope, request_id
        )
        if existing is None:
            return GenerationFailureV1(
                "persistence_unavailable", "Persistence is unavailable"
            )
        if existing.candidate_id != reserved_candidate_id:
            raise ReviseOperationIntegrityError(
                request_id,
                candidate_id=existing.candidate_id,
                reason=(
                    "Terminal revise operation candidate_id does not match "
                    "this attempt's reservation"
                ),
            )
        if existing.request_digest != request_digest:
            raise ReviseOperationIntegrityError(
                request_id,
                candidate_id=existing.candidate_id,
                reason=(
                    "Terminal revise operation request_digest does not match "
                    "this attempt's pinned digest"
                ),
            )
        if existing.status.value == "completed":
            loaded = self._load_completed_revise_candidate(existing)
            if isinstance(loaded, GenerationFailureV1):
                return loaded
            return GenerateOutcomeV1(candidate=loaded, replayed=True)
        if existing.status.value == "failed" and existing.failure is not None:
            return _generation_failure_from_snapshot(existing.failure)
        if existing.status.value == "pending":
            if indeterminate:
                return GenerationFailureV1(
                    "persistence_unavailable", "Persistence is unavailable"
                )
            return GenerationFailureV1(
                "generation_in_progress",
                "Candidate generation is already in progress for this request",
            )
        return GenerationFailureV1(
            "persistence_unavailable", "Persistence is unavailable"
        )

    def _load_completed_revise_candidate(
        self,
        operation: CandidateRevisionOperationV1,
    ) -> GenerationResultV1:
        """Load a completed generate's candidate, verifying operation binding.

        Load and verify the retained candidate before applying authoritative
        ``operation.candidate_expires_at``. A present candidate whose
        ``expires_at`` disagrees with the operation must fail closed as
        integrity — never as ordinary 410 — even when the operation expiry is
        already past. Document TTL alone must not short-circuit before
        ownership / expiry-agreement checks.
        """

        if operation.candidate_expires_at is None:
            raise ReviseOperationIntegrityError(
                operation.request_id,
                candidate_id=operation.candidate_id,
                reason="Completed revise operation is missing candidate_expires_at",
            )
        candidate_id = operation.candidate_id
        candidate_expires_at = operation.candidate_expires_at
        now = self._clock()

        try:
            # Do not enforce candidate-document TTL here: a foreign/replaced
            # document with an earlier expires_at must not short-circuit to 410
            # before ownership validation.
            candidate = self._candidates.get_for_acceptance(candidate_id)
        except CandidateNotFoundError as error:
            # Truly missing: only then is operation expiry an ordinary 410.
            if now >= candidate_expires_at:
                raise CandidateExpiredError(candidate_id) from error
            raise CandidateMissingBeforeExpiryError(
                error.details.get("candidate_id", candidate_id)
            ) from error
        except PersistenceUnavailableError:
            return GenerationFailureV1(
                "persistence_unavailable", "Persistence is unavailable"
            )
        if not candidate_belongs_to_revise_operation(candidate, operation):
            raise ReviseOperationIntegrityError(
                operation.request_id,
                candidate_id=candidate_id,
                reason=(
                    "Completed revise points to a candidate that does not belong "
                    "to this operation"
                ),
            )
        if _as_utc(candidate.expires_at) != _as_utc(candidate_expires_at):
            raise ReviseOperationIntegrityError(
                operation.request_id,
                candidate_id=candidate_id,
                reason=(
                    "Completed revise candidate.expires_at does not match "
                    "operation.candidate_expires_at"
                ),
            )
        if now >= candidate_expires_at:
            raise CandidateExpiredError(candidate_id)
        return candidate

    def _run(
        self,
        intent: _PinnedOperationIntent,
        *,
        reserved_candidate_id: str | None = None,
        persist: bool = True,
    ) -> GenerationResultV1:
        compiled = compile_openai_definition_schema()
        started = time.monotonic()
        try:
            outcome = self._provider.generate_definition(
                prompt=intent.prompt,
                schema=compiled,
                options=ProviderOptionsV1(
                    model=self._settings.model,
                    timeout_seconds=self._settings.timeout_seconds,
                    max_retries=self._settings.max_retries,
                ),
            )
        except Exception:
            return GenerationFailureV1(
                "provider_failure", "Provider raised an unexpected error"
            )
        if outcome.kind is not ProviderOutcomeKind.success:
            return GenerationFailureV1(
                f"provider_{outcome.kind.value}",
                outcome.message or "Provider did not return a definition",
            )
        if outcome.payload is None:
            return GenerationFailureV1(
                "provider_incomplete", "Provider returned no definition payload"
            )
        try:
            definition = StatblockDefinitionV1.model_validate(outcome.payload)
        except ValidationError as exc:
            diagnostics = _diagnostics_from_pydantic_validation_error(exc)
            return GenerationFailureV1(
                "definition_invalid",
                "Provider output does not match StatblockDefinitionV1",
                diagnostics=diagnostics,
            )
        if not _ruleset_matches(definition.ruleset, intent.ruleset):
            return GenerationFailureV1(
                "ruleset_mismatch",
                "Generated definition ruleset does not match the requested ruleset",
            )

        now = self._clock()
        receipt = validate_definition(
            definition, ValidationMode.generation_candidate, validated_at=now
        )
        # Domain-invalid output still becomes a candidate: the parsed definition is
        # complete and editable, so the operator fixes flagged issues in place.
        # Durability stays gated by persistence-mode validation at accept time.
        if intent.source_definition is not None and intent.preserve_element_keys:
            receipt = _with_key_preservation_warnings(
                receipt, intent.source_definition, definition
            )

        asset_warnings: list[AssetWarningV1] = []
        assets: list[AssetRefV1] = []
        asset_brief_model: AssetBriefV1 | None = None
        if intent.generate_assets:
            # When images are requested, always persist the exact brief used.
            # Without an authored description brief, fall back to the creature name.
            effective_prompt = intent.asset_prompt or definition.identity.name
            asset_brief_model = AssetBriefV1(prompt=effective_prompt)
            if self._asset_gateway is None:
                asset_warnings.append(
                    AssetWarningV1(
                        code=AssetWarningCode.asset_generator_unconfigured,
                        message=(
                            "Asset generation was requested but no asset generator is configured."
                        ),
                    )
                )
            else:
                try:
                    assets = self._asset_gateway.generate(asset_brief_model)
                except Exception:
                    asset_warnings.append(
                        AssetWarningV1(
                            code=AssetWarningCode.asset_generation_failed,
                            message="Asset generation failed; review the candidate without assets.",
                        )
                    )
        elif intent.include_generation_brief and intent.asset_prompt is not None:
            asset_brief_model = AssetBriefV1(prompt=intent.asset_prompt)

        measured_latency_ms = int((time.monotonic() - started) * 1000)
        latency_ms = (
            outcome.latency_ms if outcome.latency_ms is not None else measured_latency_ms
        )

        candidate = GeneratedStatblockCandidateV1(
            candidate_id=reserved_candidate_id or self._candidate_id_factory(),
            contract=STATBLOCK_CONTRACT,
            contract_version=STATBLOCK_CONTRACT_VERSION,
            definition=definition,
            validation_receipt=receipt,
            generation_receipt=GenerationReceiptV1(
                request_id=intent.request_id,
                provider=self._provider.provider_name,
                model=self._settings.model,
                prompt_version=PROMPT_VERSION,
                schema_version=compiled.compiler_version,
                schema_fingerprint=compiled.fingerprint,
                generated_at=now,
                caller_scope=intent.caller.caller_scope,
                request_digest=intent.request_digest,
                actor=intent.caller.actor,
                source_description_digest=intent.source_description_digest,
                source_definition_digest=intent.source_definition_digest,
                source_locator=intent.source_locator,
                provider_request_id=outcome.request_id,
                provider_response_id=outcome.response_id,
                latency_ms=latency_ms,
                input_tokens=outcome.input_tokens,
                output_tokens=outcome.output_tokens,
            ),
            asset_brief=asset_brief_model,
            assets=assets,
            asset_warnings=asset_warnings,
            created_at=now,
            expires_at=now + timedelta(seconds=self._settings.candidate_ttl_seconds),
            source_locator=intent.source_locator,
        )
        if not persist:
            return candidate
        return self._candidates.create(candidate)


def _as_utc(value: datetime) -> datetime:
    """Normalize naive datetimes to UTC for equality checks."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _default_generate_lease_seconds(settings: GenerationSettingsV1) -> int:
    """Lease must outlast provider retries, asset generation, and fixed margin."""

    # Match StatblocksV1Settings default when composition does not pass an explicit lease.
    asset_timeout_seconds = float(
        os.getenv("STATBLOCKS_V1_ASSET_TIMEOUT_SECONDS", "20")
    )
    provider_budget = math.ceil(
        float(settings.timeout_seconds) * (settings.max_retries + 1)
        + asset_timeout_seconds
        + 30
    )
    return max(120, provider_budget)


def _pin_generate_intent(
    command: GenerateStatblockCommandV1,
) -> _PinnedOperationIntent | GenerationFailureV1:
    """Deep-copy and derive all generate inputs before any provider call."""

    snapshot = command.model_copy(deep=True)
    try:
        request_digest = compute_generate_candidate_digest(snapshot)
    except StatblockV1Error as error:
        return GenerationFailureV1(error.code, error.message)
    digest_error = _verified_source_digest(snapshot.source)
    if isinstance(digest_error, GenerationFailureV1):
        return digest_error
    return _PinnedOperationIntent(
        request_id=snapshot.request_id,
        request_digest=request_digest,
        ruleset=snapshot.ruleset,
        caller=snapshot.caller,
        prompt=build_generation_prompt(snapshot),
        source_description_digest=digest_error,
        source_definition_digest=None,
        source_locator=None,
        source_definition=None,
        preserve_element_keys=False,
        asset_prompt=(
            snapshot.source.description if snapshot.asset_options.include_generation_brief else None
        ),
        generate_assets=snapshot.asset_options.generate_images,
        include_generation_brief=snapshot.asset_options.include_generation_brief,
    )


@dataclass(frozen=True)
class _ReviseAuthorityPin:
    """Pre-begin revise authority: exact request identity without source I/O.

    Locator resolution and prompt construction are deferred until after
    ``begin_revise`` returns ``ReviseBeginClaimed``.
    """

    snapshot: ReviseStatblockCommandV1
    request_digest: str
    source_description_digest: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot", self.snapshot.model_copy(deep=True))


def _pin_revise_authority(
    command: ReviseStatblockCommandV1,
) -> _ReviseAuthorityPin | GenerationFailureV1:
    """Deep-copy, validate XOR/basic shape, and compute digest — no locator I/O."""

    snapshot = command.model_copy(deep=True)
    if (snapshot.source_definition is None) == (snapshot.source_locator is None):
        return GenerationFailureV1("invalid_request", "Revision source is missing")
    try:
        request_digest = compute_revise_candidate_digest(snapshot)
    except StatblockV1Error as error:
        return GenerationFailureV1(error.code, error.message)

    source_digest: str | None = None
    if snapshot.source is not None:
        digest_error = _verified_source_digest(snapshot.source)
        if isinstance(digest_error, GenerationFailureV1):
            return digest_error
        source_digest = digest_error

    return _ReviseAuthorityPin(
        snapshot=snapshot,
        request_digest=request_digest,
        source_description_digest=source_digest,
    )


def _materialize_revise_intent(
    authority: _ReviseAuthorityPin,
    definition_resolver: DefinitionResolver | None,
) -> _PinnedOperationIntent | GenerationFailureV1:
    """Resolve locator / inline definition only after a durable revise claim."""

    snapshot = authority.snapshot
    source = snapshot.source_definition
    source_locator = snapshot.source_locator
    if source is None:
        if source_locator is None:
            return GenerationFailureV1("invalid_request", "Revision source is missing")
        if definition_resolver is None:
            return GenerationFailureV1(
                "source_unavailable", "No definition resolver is configured"
            )
        try:
            source = definition_resolver.resolve(source_locator).model_copy(deep=True)
        except StatblockV1Error as error:
            return GenerationFailureV1(error.code, error.message)
        except Exception:
            return GenerationFailureV1(
                "source_unavailable", "Failed to resolve source revision"
            )
    else:
        source = source.model_copy(deep=True)

    return _PinnedOperationIntent(
        request_id=snapshot.request_id,
        request_digest=authority.request_digest,
        ruleset=snapshot.ruleset,
        caller=snapshot.caller,
        prompt=build_revision_prompt(snapshot, source),
        source_description_digest=authority.source_description_digest,
        source_definition_digest=compute_definition_digest(source),
        source_locator=source_locator,
        source_definition=source,
        preserve_element_keys=snapshot.preserve_element_keys,
        asset_prompt=(
            snapshot.source.description
            if snapshot.source and snapshot.asset_options.include_generation_brief
            else None
        ),
        generate_assets=snapshot.asset_options.generate_images,
        include_generation_brief=snapshot.asset_options.include_generation_brief,
    )


def _pin_revise_intent(
    command: ReviseStatblockCommandV1,
    definition_resolver: DefinitionResolver | None,
) -> _PinnedOperationIntent | GenerationFailureV1:
    """Compatibility helper: authority pin + immediate materialization.

    Production ``revise()`` must not use this for the begin path — it would
    resolve locators before consulting durable operation authority.
    """

    authority = _pin_revise_authority(command)
    if isinstance(authority, GenerationFailureV1):
        return authority
    return _materialize_revise_intent(authority, definition_resolver)


def _verified_source_digest(source: SourceSnapshotV1) -> str | GenerationFailureV1:
    computed = _digest_text(source.description)
    if source.description_digest is not None and source.description_digest != computed:
        return GenerationFailureV1(
            "source_digest_mismatch",
            "Caller-supplied source description digest does not match the description",
        )
    return computed


def _ruleset_matches(actual: RulesetRef, requested: RulesetRef) -> bool:
    return (
        actual.system == requested.system
        and actual.edition == requested.edition
        and actual.house_ruleset_id == requested.house_ruleset_id
    )


def _with_key_preservation_warnings(
    receipt: ValidationReceiptV1,
    source: StatblockDefinitionV1,
    revised: StatblockDefinitionV1,
) -> ValidationReceiptV1:
    issues = list(receipt.issues)
    source_by_identity = _group_by_identity(source.rule_elements)
    revised_by_identity = _group_by_identity(revised.rule_elements)
    revised_by_key = {
        element.key: (index, element)
        for index, element in enumerate(revised.rule_elements)
    }
    ambiguous_identities = {
        identity
        for identity, items in source_by_identity.items()
        if len(items) > 1
    } | {
        identity
        for identity, items in revised_by_identity.items()
        if len(items) > 1
    }

    for index, element in enumerate(source.rule_elements):
        identity = _element_identity(element.section.value, element.name)
        if identity in ambiguous_identities:
            issues.append(
                ValidationIssueV1(
                    code="ELEMENT_KEY_IDENTITY_AMBIGUOUS",
                    severity=ValidationSeverity.warning,
                    field_path=f"rule_elements[{index}].name",
                    message=(
                        f"Element '{element.name}' in section '{element.section.value}' "
                        "is not uniquely identifiable for key-preservation matching."
                    ),
                )
            )
            continue

        revised_matches = revised_by_identity.get(identity, [])
        if revised_matches:
            revised_index, match = revised_matches[0]
            if match.key != element.key:
                issues.append(
                    ValidationIssueV1(
                        code="ELEMENT_KEY_CHANGED",
                        severity=ValidationSeverity.warning,
                        field_path=f"rule_elements[{revised_index}].key",
                        message=(
                            f"Element '{element.name}' changed key from '{element.key}' "
                            f"to '{match.key}' despite preserve_element_keys."
                        ),
                    )
                )
            continue

        if element.key not in revised_by_key:
            issues.append(
                ValidationIssueV1(
                    code="ELEMENT_KEY_DROPPED",
                    severity=ValidationSeverity.warning,
                    field_path=f"rule_elements[{index}].key",
                    message=(
                        f"Source element key '{element.key}' was not preserved; "
                        "confirm the conceptual rule was intentionally replaced."
                    ),
                )
            )

    for index, element in enumerate(source.rule_elements):
        holder = revised_by_key.get(element.key)
        if holder is None:
            continue
        revised_index, revised_element = holder
        if _element_identity(
            revised_element.section.value, revised_element.name
        ) != _element_identity(element.section.value, element.name):
            issues.append(
                ValidationIssueV1(
                    code="ELEMENT_KEY_REPURPOSED",
                    severity=ValidationSeverity.warning,
                    field_path=f"rule_elements[{revised_index}].key",
                    message=(
                        f"Key '{element.key}' was reassigned from '{element.name}' "
                        f"to '{revised_element.name}' despite preserve_element_keys."
                    ),
                )
            )

    status = (
        ValidationStatus.invalid
        if any(issue.severity is ValidationSeverity.error for issue in issues)
        else ValidationStatus.warnings
        if issues
        else ValidationStatus.valid
    )
    return receipt.model_copy(
        update={
            "issues": issues,
            "status": status,
            "validator_version": f"{receipt.validator_version}+{KEY_PRESERVATION_PASS_VERSION}",
        }
    )


def _bound_public_text(value: str, *, max_len: int) -> str:
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized:
        return "Validation failed"
    if len(normalized) <= max_len:
        return normalized
    return normalized[: max_len - 1] + "…"


def _pydantic_error_code(error_type: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", error_type).strip("_").upper()
    if not normalized:
        normalized = "PYDANTIC_VALIDATION"
    if not re.match(r"^[A-Z][A-Z0-9_]*$", normalized):
        normalized = f"PYDANTIC_{normalized}"[:MAX_GENERATION_VALIDATION_CODE_LEN]
    return normalized[:MAX_GENERATION_VALIDATION_CODE_LEN]


_GENERIC_SCHEMA_DIAGNOSTIC_MESSAGE = "Validation failed for this field."

_SCHEMA_DIAGNOSTIC_MESSAGES: dict[str, str] = {
    "missing": "Required field is missing.",
    "extra_forbidden": "Unexpected field is not permitted.",
    "union_tag_invalid": (
        "Unrecognized element kind; the value does not match any supported kind "
        "for this field."
    ),
    "union_tag_not_found": (
        "Missing the discriminator field required to determine the element type."
    ),
    "literal_error": "Value must equal the required constant for this field.",
    "enum": "Value must be one of the allowed options.",
    "string_type": "Value must be a string.",
    "string_too_short": "String value is too short.",
    "string_too_long": "String value is too long.",
    "string_pattern_mismatch": "String value does not match the required pattern.",
    "int_type": "Value must be an integer.",
    "int_parsing": "Value must be a valid integer.",
    "float_type": "Value must be a number.",
    "float_parsing": "Value must be a valid number.",
    "greater_than": "Value must be greater than the allowed minimum.",
    "greater_than_equal": "Value must be greater than or equal to the allowed minimum.",
    "less_than": "Value must be less than the allowed maximum.",
    "less_than_equal": "Value must be less than or equal to the allowed maximum.",
    "list_type": "Value must be a list.",
    "too_short": "List has too few items.",
    "too_long": "List has too many items.",
    "dict_type": "Value must be an object.",
    "model_type": "Value must be a structured object with the expected fields.",
    "bool_type": "Value must be true or false.",
    "value_error": "Value is not valid for this field.",
}


def _pydantic_error_message(error_type: str) -> str:
    return _SCHEMA_DIAGNOSTIC_MESSAGES.get(error_type, _GENERIC_SCHEMA_DIAGNOSTIC_MESSAGE)


_UNEXPECTED_PROVIDER_KEY_FIELD = "<unexpected_key>"


def _field_path_from_pydantic_loc(
    loc: tuple[object, ...], *, error_type: str = ""
) -> str:
    if error_type == "extra_forbidden" and loc:
        parent_loc = loc[:-1]
        if not parent_loc:
            path = _UNEXPECTED_PROVIDER_KEY_FIELD
        else:
            path = (
                f"{_field_path_segments_to_public_path(parent_loc)}"
                f".{_UNEXPECTED_PROVIDER_KEY_FIELD}"
            )
        return _bound_public_text(
            path, max_len=MAX_GENERATION_VALIDATION_FIELD_PATH_LEN
        )
    return _field_path_segments_to_public_path(loc)


def _field_path_segments_to_public_path(loc: tuple[object, ...]) -> str:
    if not loc:
        return "$"
    segments: list[str] = []
    for part in loc:
        if isinstance(part, int):
            if not segments:
                segments.append(f"[{part}]")
            else:
                segments[-1] = f"{segments[-1]}[{part}]"
        else:
            segments.append(str(part))
    path = ".".join(segments)
    return _bound_public_text(path, max_len=MAX_GENERATION_VALIDATION_FIELD_PATH_LEN)


def _diagnostics_from_pydantic_validation_error(
    exc: ValidationError,
) -> GenerationValidationDiagnosticPacketV1 | None:
    try:
        raw_issues: list[GenerationValidationDiagnosticIssueV1] = []
        for item in exc.errors(include_url=False, include_input=False):
            error_type = str(item.get("type", "validation_error"))
            raw_issues.append(
                GenerationValidationDiagnosticIssueV1(
                    code=_pydantic_error_code(error_type),
                    severity=ValidationSeverity.error,
                    field_path=_field_path_from_pydantic_loc(
                        tuple(item.get("loc", ())),
                        error_type=error_type,
                    ),
                    message=_pydantic_error_message(error_type),
                    suggested_resolution=None,
                )
            )
        issues = sorted(
            raw_issues,
            key=lambda issue: (issue.field_path, issue.code, issue.message),
        )[:MAX_GENERATION_VALIDATION_DIAGNOSTIC_ISSUES]
        return GenerationValidationDiagnosticPacketV1(
            phase=GenerationValidationPhaseV1.schema_validation,
            issue_count=len(issues),
            issues=issues,
        )
    except Exception:
        return None


def _failure_snapshot_from_generation_failure(
    failure: GenerationFailureV1,
) -> CandidateGenerationFailureSnapshotV1:
    return CandidateGenerationFailureSnapshotV1(
        kind=failure.kind,
        message=failure.message,
        diagnostics=failure.diagnostics,
    )


def _generation_failure_from_snapshot(
    snapshot: CandidateGenerationFailureSnapshotV1,
) -> GenerationFailureV1:
    return GenerationFailureV1(
        snapshot.kind,
        snapshot.message,
        diagnostics=snapshot.diagnostics,
    )


def _group_by_identity(
    elements: list[RuleElement],
) -> dict[tuple[str, str], list[tuple[int, RuleElement]]]:
    groups: dict[tuple[str, str], list[tuple[int, RuleElement]]] = defaultdict(list)
    for index, element in enumerate(elements):
        groups[_element_identity(element.section.value, element.name)].append(
            (index, element)
        )
    return groups


def _element_identity(section: str, name: str) -> tuple[str, str]:
    return (section, unicodedata.normalize("NFC", name).casefold())


def _digest_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    return f"sha256:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"


def _new_candidate_id() -> str:
    return f"cand_{_base36(secrets.randbelow(36**16))}"


def _base36(value: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = "0"
    while value:
        value, remainder = divmod(value, 36)
        result = alphabet[remainder] + result.lstrip("0")
    return result
