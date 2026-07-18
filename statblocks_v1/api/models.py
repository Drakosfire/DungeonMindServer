"""Preliminary HTTP DTOs for the DungeonBuddy statblock v1 contract."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    contract: str
    contract_version: str
    capabilities: list[str] = Field(default_factory=list)
