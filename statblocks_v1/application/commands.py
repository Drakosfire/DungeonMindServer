"""Transport-neutral commands for statblock candidate generation."""
from __future__ import annotations

from pydantic import Field, model_validator

from statblocks_v1.domain.primitives import StrictModel
from statblocks_v1.domain.profiles import RulesetRef
from statblocks_v1.domain.resources import ExactRevisionLocatorV1
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1


class SourceSnapshotV1(StrictModel):
    name_hint: str = Field(min_length=1)
    description: str = Field(min_length=1)
    description_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")


class GenerationIntentV1(StrictModel):
    target_cr: str | None = None
    roles: list[str] = Field(default_factory=list)
    complexity: str | None = None
    must_include: list[str] = Field(default_factory=list)
    must_avoid: list[str] = Field(default_factory=list)


class EncounterContextV1(StrictModel):
    party_level: int | None = Field(default=None, ge=1)
    party_size: int | None = Field(default=None, ge=1)
    terrain_notes: list[str] = Field(default_factory=list)


class AssetOptionsV1(StrictModel):
    include_generation_brief: bool = True
    generate_images: bool = False


class CallerProvenanceV1(StrictModel):
    caller_scope: str = Field(min_length=1)
    actor: str | None = None


class GenerateStatblockCommandV1(StrictModel):
    request_id: str = Field(min_length=1)
    ruleset: RulesetRef
    source: SourceSnapshotV1
    intent: GenerationIntentV1 = Field(default_factory=GenerationIntentV1)
    context: EncounterContextV1 = Field(default_factory=EncounterContextV1)
    asset_options: AssetOptionsV1 = Field(default_factory=AssetOptionsV1)
    caller: CallerProvenanceV1


class ReviseStatblockCommandV1(StrictModel):
    request_id: str = Field(min_length=1)
    ruleset: RulesetRef
    revision_instructions: list[str] = Field(min_length=1)
    caller: CallerProvenanceV1
    source_definition: StatblockDefinitionV1 | None = None
    source_locator: ExactRevisionLocatorV1 | None = None
    source: SourceSnapshotV1 | None = None
    intent: GenerationIntentV1 = Field(default_factory=GenerationIntentV1)
    context: EncounterContextV1 = Field(default_factory=EncounterContextV1)
    asset_options: AssetOptionsV1 = Field(default_factory=AssetOptionsV1)
    preserve_element_keys: bool = True

    @model_validator(mode="after")
    def has_exactly_one_source(self) -> "ReviseStatblockCommandV1":
        if (self.source_definition is None) == (self.source_locator is None):
            raise ValueError("provide exactly one of source_definition or source_locator")
        return self


class AssetBriefV1(StrictModel):
    prompt: str = Field(min_length=1)
    recommended_roles: list[str] = Field(default_factory=lambda: ["portrait", "token"])
