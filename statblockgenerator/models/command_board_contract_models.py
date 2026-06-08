"""Command-board draft contract models for StatBlockGenerator v2."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

from statblockgenerator.models.statblock_models import StatBlockDetails

DraftMode = Literal[
    "generate_from_prompt",
    "generate_from_source_statblock",
    "revise_existing",
    "quick_reinforcement",
    "terrain_pressure",
]

LifecycleState = Literal["live_draft"]
ReviewStatus = Literal["needs_dm_review", "warnings", "failed"]


class DraftIntent(BaseModel):
    """High-level command-board intent for a statblock draft."""

    summary: str
    target_cr: Optional[Union[str, float]] = None
    target_role: Optional[str] = None
    tone: Optional[str] = None
    complexity: Optional[str] = None


class EncounterContext(BaseModel):
    """Encounter details that should influence draft generation."""

    party_level: Optional[int] = None
    party_size: Optional[int] = None
    round: Optional[int] = None
    threat_pressure: Optional[str] = None
    objective: Optional[str] = None


class TerrainContext(BaseModel):
    """Terrain details that should influence draft generation and warnings."""

    summary: Optional[str] = None
    features: List[str] = Field(default_factory=list)
    hazards: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)


class SourceRef(BaseModel):
    """Stable reference to command-board, map, encounter, or source data."""

    id: str
    kind: str
    label: Optional[str] = None


class OutputOptions(BaseModel):
    """Caller-selected response sections and persistence behavior."""

    include_markdown: bool = True
    include_combat_defaults: bool = True
    include_review_warnings: bool = True
    persist: bool = False


class StatBlockDraftRequest(BaseModel):
    """Request envelope for v2 command-board statblock draft generation."""

    request_id: Optional[str] = None
    mode: DraftMode
    intent: DraftIntent
    prompt: Optional[str] = None
    source_statblock: Optional[Union[StatBlockDetails, Dict[str, Any]]] = None
    revision_instructions: List[str] = Field(default_factory=list)
    encounter_context: Optional[EncounterContext] = None
    terrain_context: Optional[TerrainContext] = None
    source_refs: List[SourceRef] = Field(default_factory=list)
    output_options: OutputOptions = Field(default_factory=OutputOptions)

    @model_validator(mode="after")
    def validate_generation_inputs(self) -> "StatBlockDraftRequest":
        prompt = (self.prompt or "").strip()
        source_present = self.source_statblock is not None
        instructions_present = any(i.strip() for i in self.revision_instructions)

        if self.mode in {"generate_from_prompt", "quick_reinforcement", "terrain_pressure"} and not prompt:
            raise ValueError(f"prompt is required for mode '{self.mode}'")

        if self.mode in {"generate_from_source_statblock", "revise_existing"}:
            if not (prompt or source_present or instructions_present):
                raise ValueError(
                    f"mode '{self.mode}' requires prompt, source_statblock, or revision_instructions"
                )

        return self


class CombatDefaults(BaseModel):
    """Deterministic combat defaults derived from the structured statblock."""

    name: str
    armor_class: int
    hit_points: int
    initiative_bonus: Optional[int] = None
    passive_perception: Optional[int] = None
    speed_summary: str
    primary_actions: List[str] = Field(default_factory=list)
    save_dcs: List[int] = Field(default_factory=list)
    senses_summary: Optional[str] = None
    condition_immunities: Optional[str] = None
    suggested_tactics: List[str] = Field(default_factory=list)


class ReviewWarning(BaseModel):
    """Lightweight warning for DM review."""

    code: str
    message: str
    severity: Literal["info", "warning", "error"] = "warning"


class DraftProvenance(BaseModel):
    """Generation provenance for downstream review and traceability."""

    request_id: Optional[str] = None
    mode: DraftMode
    source_refs: List[SourceRef] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    generator: str = "StatBlockGenerator.generate_creature"
    adapter_version: str = "0.1.0"
    persist_requested: bool = False
    generation_info: Dict[str, Any] = Field(default_factory=dict)


class StatBlockDraft(BaseModel):
    """Stable v2 statblock draft envelope payload."""

    draft_id: str
    lifecycle_state: LifecycleState = "live_draft"
    review_status: ReviewStatus = "needs_dm_review"
    statblock: StatBlockDetails
    markdown: str
    combat_defaults: CombatDefaults
    warnings: List[ReviewWarning] = Field(default_factory=list)
    provenance: DraftProvenance


class ContractError(BaseModel):
    """Stable error envelope for v2 contract failures."""

    code: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class StatBlockDraftResponse(BaseModel):
    """Top-level response envelope for v2 draft generation."""

    success: bool
    draft: Optional[StatBlockDraft] = None
    error: Optional[ContractError] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @model_validator(mode="after")
    def validate_success_envelope(self) -> "StatBlockDraftResponse":
        if self.success and self.draft is None:
            raise ValueError("successful draft responses require draft")

        if not self.success and self.error is None:
            raise ValueError("failed draft responses require error")

        return self
