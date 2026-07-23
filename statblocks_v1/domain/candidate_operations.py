"""Durable candidate-generation operation records (PR23).

Separate from PR15 ``IdempotencyRecordV1``, which is completed-only and shaped for
immutable statblock/revision create+append outcomes.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Self

from pydantic import Field, model_validator

from statblocks_v1.domain.primitives import StrictModel

GENERATE_CANDIDATE_OPERATION: Literal["generate_candidate"] = "generate_candidate"


class CandidateGenerationStatusV1(str, Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"


class CandidateGenerationFailureSnapshotV1(StrictModel):
    """Stable, safe terminal failure for replay. Never stores provider exception text."""

    kind: str = Field(min_length=1)
    message: str = Field(min_length=1)


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
            return self

        if self.status is CandidateGenerationStatusV1.completed:
            if self.candidate_expires_at is None:
                raise ValueError(
                    "completed generate operations require candidate_expires_at"
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
            if self.completed_at is None:
                raise ValueError("failed generate operations require completed_at")
            return self

        return self
