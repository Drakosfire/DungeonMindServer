"""Durable candidate-generation operation records (PR23).

Separate from PR15 ``IdempotencyRecordV1``, which is completed-only and shaped for
immutable statblock/revision create+append outcomes.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from statblocks_v1.domain.primitives import StrictModel
from statblocks_v1.domain.receipts import ValidationSeverity

GENERATION_VALIDATION_DIAGNOSTICS_VERSION: Literal[
    "generation-validation-diagnostics-v1"
] = "generation-validation-diagnostics-v1"

MAX_GENERATION_VALIDATION_DIAGNOSTIC_ISSUES = 32
MAX_GENERATION_VALIDATION_FIELD_PATH_LEN = 256
MAX_GENERATION_VALIDATION_CODE_LEN = 64
MAX_GENERATION_VALIDATION_MESSAGE_LEN = 512
MAX_GENERATION_VALIDATION_SUGGESTED_RESOLUTION_LEN = 512


class GenerationValidationPhaseV1(str, Enum):
    schema_validation = "schema_validation"
    domain_validation = "domain_validation"


class GenerationValidationDiagnosticIssueV1(StrictModel):
    """Bounded public issue for generation validation failures."""

    code: str = Field(min_length=1, max_length=MAX_GENERATION_VALIDATION_CODE_LEN)
    severity: ValidationSeverity
    field_path: str = Field(
        min_length=1, max_length=MAX_GENERATION_VALIDATION_FIELD_PATH_LEN
    )
    message: str = Field(min_length=1, max_length=MAX_GENERATION_VALIDATION_MESSAGE_LEN)
    suggested_resolution: str | None = Field(
        default=None, max_length=MAX_GENERATION_VALIDATION_SUGGESTED_RESOLUTION_LEN
    )


class GenerationValidationDiagnosticPacketV1(StrictModel):
    """Safe diagnostic packet persisted on terminal definition_invalid failures."""

    schema_version: Literal["generation-validation-diagnostics-v1"] = (
        GENERATION_VALIDATION_DIAGNOSTICS_VERSION
    )
    phase: GenerationValidationPhaseV1
    issue_count: int = Field(ge=0)
    issues: list[GenerationValidationDiagnosticIssueV1] = Field(default_factory=list)

    @field_validator("issues")
    @classmethod
    def _bounded_issue_list(
        cls, issues: list[GenerationValidationDiagnosticIssueV1]
    ) -> list[GenerationValidationDiagnosticIssueV1]:
        if len(issues) > MAX_GENERATION_VALIDATION_DIAGNOSTIC_ISSUES:
            return issues[:MAX_GENERATION_VALIDATION_DIAGNOSTIC_ISSUES]
        return issues

    @model_validator(mode="after")
    def issue_count_matches_issues(self) -> Self:
        if self.issue_count != len(self.issues):
            raise ValueError("issue_count must equal len(issues)")
        return self

GENERATE_CANDIDATE_OPERATION: Literal["generate_candidate"] = "generate_candidate"
REVISE_CANDIDATE_OPERATION: Literal["revise_candidate"] = "revise_candidate"


class CandidateGenerationStatusV1(str, Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"


class CandidateGenerationFailureSnapshotV1(StrictModel):
    """Stable, safe terminal failure for replay. Never stores provider exception text."""

    kind: str = Field(min_length=1)
    message: str = Field(min_length=1)
    diagnostics: GenerationValidationDiagnosticPacketV1 | None = None

    @model_validator(mode="after")
    def diagnostics_only_for_definition_invalid(self) -> Self:
        if self.diagnostics is not None and self.kind != "definition_invalid":
            raise ValueError(
                "diagnostics are only permitted for definition_invalid failures"
            )
        return self


class CandidateGenerationOperationV1(StrictModel):
    """Lease-bearing generate operation bound to one reserved candidate_id."""

    caller_scope: str = Field(min_length=1)
    operation: Literal["generate_candidate"] = GENERATE_CANDIDATE_OPERATION
    request_id: str = Field(min_length=1)
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    candidate_id: str = Field(pattern=r"^cand_[a-z0-9]+$")
    status: CandidateGenerationStatusV1
    lease_owner: str = Field(min_length=1)
    lease_expires_at: datetime
    attempt_count: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    failure: CandidateGenerationFailureSnapshotV1 | None = None
    # Retained on completion so premature TTL/deletion can be distinguished from
    # normal expiry without keeping the full candidate mechanics.
    candidate_expires_at: datetime | None = None
    # Canonical fingerprint of the generated outcome (definition/assets/warnings).
    # Bound at completion so replay cannot accept a recreated document that only
    # copies request receipt metadata.
    outcome_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )

    @model_validator(mode="after")
    def status_field_invariants(self) -> Self:
        """Reject impossible pending/completed/failed field combinations."""

        if self.status is CandidateGenerationStatusV1.pending:
            if self.failure is not None:
                raise ValueError("pending generate operations must not carry failure")
            if self.candidate_expires_at is not None:
                raise ValueError(
                    "pending generate operations must not carry candidate_expires_at"
                )
            if self.completed_at is not None:
                raise ValueError(
                    "pending generate operations must not carry completed_at"
                )
            if self.outcome_digest is not None:
                raise ValueError(
                    "pending generate operations must not carry outcome_digest"
                )
            return self

        if self.status is CandidateGenerationStatusV1.completed:
            if self.candidate_expires_at is None:
                raise ValueError(
                    "completed generate operations require candidate_expires_at"
                )
            if self.outcome_digest is None:
                raise ValueError(
                    "completed generate operations require outcome_digest"
                )
            if self.failure is not None:
                raise ValueError(
                    "completed generate operations must not carry failure"
                )
            if self.completed_at is None:
                raise ValueError(
                    "completed generate operations require completed_at"
                )
            return self

        if self.status is CandidateGenerationStatusV1.failed:
            if self.failure is None:
                raise ValueError("failed generate operations require failure")
            if self.candidate_expires_at is not None:
                raise ValueError(
                    "failed generate operations must not carry candidate_expires_at"
                )
            if self.outcome_digest is not None:
                raise ValueError(
                    "failed generate operations must not carry outcome_digest"
                )
            if self.completed_at is None:
                raise ValueError("failed generate operations require completed_at")
            return self

        return self


class CandidateRevisionOperationV1(StrictModel):
    """Lease-bearing revise operation bound to one reserved candidate_id."""

    caller_scope: str = Field(min_length=1)
    operation: Literal["revise_candidate"] = REVISE_CANDIDATE_OPERATION
    request_id: str = Field(min_length=1)
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    candidate_id: str = Field(pattern=r"^cand_[a-z0-9]+$")
    status: CandidateGenerationStatusV1
    lease_owner: str = Field(min_length=1)
    lease_expires_at: datetime
    attempt_count: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    failure: CandidateGenerationFailureSnapshotV1 | None = None
    candidate_expires_at: datetime | None = None
    outcome_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )

    @model_validator(mode="after")
    def status_field_invariants(self) -> Self:
        if self.status is CandidateGenerationStatusV1.pending:
            if self.failure is not None:
                raise ValueError("pending revise operations must not carry failure")
            if self.candidate_expires_at is not None:
                raise ValueError(
                    "pending revise operations must not carry candidate_expires_at"
                )
            if self.completed_at is not None:
                raise ValueError(
                    "pending revise operations must not carry completed_at"
                )
            if self.outcome_digest is not None:
                raise ValueError(
                    "pending revise operations must not carry outcome_digest"
                )
            return self

        if self.status is CandidateGenerationStatusV1.completed:
            if self.candidate_expires_at is None:
                raise ValueError(
                    "completed revise operations require candidate_expires_at"
                )
            if self.outcome_digest is None:
                raise ValueError(
                    "completed revise operations require outcome_digest"
                )
            if self.failure is not None:
                raise ValueError(
                    "completed revise operations must not carry failure"
                )
            if self.completed_at is None:
                raise ValueError(
                    "completed revise operations require completed_at"
                )
            return self

        if self.status is CandidateGenerationStatusV1.failed:
            if self.failure is None:
                raise ValueError("failed revise operations require failure")
            if self.candidate_expires_at is not None:
                raise ValueError(
                    "failed revise operations must not carry candidate_expires_at"
                )
            if self.outcome_digest is not None:
                raise ValueError(
                    "failed revise operations must not carry outcome_digest"
                )
            if self.completed_at is None:
                raise ValueError("failed revise operations require completed_at")
            return self

        return self
