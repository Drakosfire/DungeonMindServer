"""Server-owned resource envelopes for persisted statblock v1 content."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from statblocks_v1.domain.primitives import StrictModel
from statblocks_v1.domain.receipts import ValidationReceiptV1
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1

STATBLOCK_CONTRACT = "dungeonbuddy-statblock"
STATBLOCK_CONTRACT_VERSION = "v1"


class ResourceLocatorV1(StrictModel):
    resource_type: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)


class GenerationReceiptV1(StrictModel):
    """Extensible, server-owned audit data populated by the generation service."""

    request_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    schema_fingerprint: str = Field(min_length=1)
    generated_at: datetime
    source_description_digest: str | None = None
    source_locator: ResourceLocatorV1 | None = None
    provider_request_id: str | None = None
    provider_response_id: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class GeneratedStatblockCandidateV1(StrictModel):
    candidate_id: str = Field(pattern=r"^cand_[a-z0-9]+$")
    contract: str = STATBLOCK_CONTRACT
    contract_version: str = STATBLOCK_CONTRACT_VERSION
    definition: StatblockDefinitionV1
    validation_receipt: ValidationReceiptV1
    generation_receipt: GenerationReceiptV1 | None = None
    asset_brief: dict[str, Any] | None = None
    assets: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    expires_at: datetime
    source_locator: ResourceLocatorV1 | None = None


class StatblockResourceV1(StrictModel):
    statblock_id: str = Field(pattern=r"^sb_[a-z0-9]+$")
    latest_revision_id: str = Field(pattern=r"^rev_[a-z0-9]+$")
    created_at: datetime
    created_by: str = Field(min_length=1)


class StatblockRevisionResourceV1(StrictModel):
    statblock_id: str = Field(pattern=r"^sb_[a-z0-9]+$")
    revision_id: str = Field(pattern=r"^rev_[a-z0-9]+$")
    parent_revision_id: str | None = Field(default=None, pattern=r"^rev_[a-z0-9]+$")
    contract: str = STATBLOCK_CONTRACT
    contract_version: str = STATBLOCK_CONTRACT_VERSION
    definition: StatblockDefinitionV1
    canonical_definition: str = Field(min_length=2)
    definition_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    validation_receipt: ValidationReceiptV1
    provenance: dict[str, Any] = Field(default_factory=dict)
    asset_bindings: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime


class IdempotencyRecordV1(StrictModel):
    caller_scope: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    outcome: ResourceLocatorV1
    created_at: datetime
