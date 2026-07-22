"""Durable candidate-generation operation records (PR23).

Separate from PR15 ``IdempotencyRecordV1``, which is completed-only and shaped for
immutable statblock/revision create+append outcomes.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import Field

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
