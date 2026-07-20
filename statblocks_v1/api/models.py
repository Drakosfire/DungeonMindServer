"""HTTP DTOs for the DungeonBuddy statblock v1 candidate workflow."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from statblocks_v1.application.commands import (
    AssetOptionsV1,
    EncounterContextV1,
    GenerationIntentV1,
    SourceSnapshotV1,
)
from statblocks_v1.domain.assets import AssetBindingV1
from statblocks_v1.domain.profiles import RulesetRef
from statblocks_v1.domain.receipts import ValidationReceiptV1
from statblocks_v1.domain.resources import (
    ContractNameV1,
    ContractVersionV1,
    ExactRevisionLocatorV1,
    StatblockResourceV1,
    StatblockRevisionResourceV1,
)
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1


class StrictModel(BaseModel):
    """Shared base for v1 transport models (extra fields forbidden)."""

    model_config = ConfigDict(extra="forbid")


class ErrorDetailV1(StrictModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorEnvelopeV1(StrictModel):
    """Top-level typed error body returned by v1 routes (never nested under ``detail``)."""

    error: ErrorDetailV1


class HealthResponseV1(StrictModel):
    status: str
    contract: ContractNameV1
    contract_version: ContractVersionV1
    capabilities: list[str] = Field(default_factory=list)


class ReadinessResponseV1(StrictModel):
    """Authenticated readiness payload (200 ready or 503 not_ready)."""

    status: str
    contract: ContractNameV1
    generation_enabled: bool = False
    read_routes_enabled: bool = False
    errors: list[str] = Field(default_factory=list)
    detail: str | None = None


class GenerateCandidateRequestV1(StrictModel):
    request_id: str = Field(min_length=1)
    ruleset: RulesetRef
    source: SourceSnapshotV1
    intent: GenerationIntentV1 = Field(default_factory=GenerationIntentV1)
    context: EncounterContextV1 = Field(default_factory=EncounterContextV1)
    asset_options: AssetOptionsV1 = Field(default_factory=AssetOptionsV1)
    actor: str | None = None


class ReviseCandidateRequestV1(StrictModel):
    request_id: str = Field(min_length=1)
    ruleset: RulesetRef
    revision_instructions: list[str] = Field(min_length=1)
    source_definition: StatblockDefinitionV1 | None = None
    source_locator: ExactRevisionLocatorV1 | None = None
    source: SourceSnapshotV1 | None = None
    intent: GenerationIntentV1 = Field(default_factory=GenerationIntentV1)
    context: EncounterContextV1 = Field(default_factory=EncounterContextV1)
    asset_options: AssetOptionsV1 = Field(default_factory=AssetOptionsV1)
    preserve_element_keys: bool = True
    actor: str | None = None

    @model_validator(mode="after")
    def exactly_one_revision_source(self) -> "ReviseCandidateRequestV1":
        if (self.source_definition is None) == (self.source_locator is None):
            raise ValueError("provide exactly one of source_definition or source_locator")
        return self


class ValidateDefinitionRequestV1(StrictModel):
    definition: StatblockDefinitionV1


class ValidationResponseV1(StrictModel):
    validation_receipt: ValidationReceiptV1
    definition_digest: str


class CreateStatblockRequestV1(StrictModel):
    """Accept a reviewed definition into a new logical statblock + first revision.

    Free-form ``provenance`` is intentionally absent: callers may supply typed
    acceptance metadata only. Server-owned candidate audit evidence is attached
    when ``candidate_id`` is present. ``actor`` is provenance data, not
    authenticated ownership of ``created_by``.
    """

    idempotency_key: str = Field(min_length=1)
    definition: StatblockDefinitionV1
    candidate_id: str | None = Field(default=None, pattern=r"^cand_[a-z0-9]+$")
    change_summary: str = Field(min_length=1)
    actor: str | None = None
    accepted_through: dict[str, Any] = Field(default_factory=dict)
    asset_bindings: list[AssetBindingV1] = Field(default_factory=list)


class AppendRevisionRequestV1(StrictModel):
    """Append an immutable revision under compare-and-swap parent semantics."""

    idempotency_key: str = Field(min_length=1)
    parent_revision_id: str = Field(pattern=r"^rev_[a-z0-9]+$")
    definition: StatblockDefinitionV1
    candidate_id: str | None = Field(default=None, pattern=r"^cand_[a-z0-9]+$")
    change_summary: str = Field(min_length=1)
    actor: str | None = None
    accepted_through: dict[str, Any] = Field(default_factory=dict)
    asset_bindings: list[AssetBindingV1] = Field(default_factory=list)


class CreateStatblockResponseV1(StrictModel):
    statblock: StatblockResourceV1
    revision: StatblockRevisionResourceV1


class RevisionListResponseV1(StrictModel):
    revisions: list[StatblockRevisionResourceV1]
