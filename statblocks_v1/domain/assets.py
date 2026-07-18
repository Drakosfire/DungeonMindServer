"""Typed CDN-backed asset references for the statblock v1 contract."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, HttpUrl

from statblocks_v1.domain.primitives import StrictModel

AssetRoleV1 = Literal["portrait", "token", "full_body", "encounter_art", "alternate"]
AssetProviderKindV1 = Literal["cloudflare_images", "cloudflare_r2", "image_pipeline"]


class AssetBriefV1(StrictModel):
    """Optional generation intent; never part of mechanics."""

    prompt: str = Field(min_length=1)
    recommended_roles: list[AssetRoleV1] = Field(
        default_factory=lambda: ["portrait", "token"]
    )


class AssetVariantV1(StrictModel):
    name: str = Field(min_length=1)
    url: HttpUrl


class AssetRefV1(StrictModel):
    """A durable provider-owned asset identifier and canonical CDN address."""

    asset_id: str = Field(min_length=1)
    provider_kind: AssetProviderKindV1
    url: HttpUrl
    mime_type: str = Field(pattern=r"^image/[a-z0-9.+-]+$")
    alt_text: str | None = None
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    prompt: str | None = None
    generation_provenance: str | None = None
    variants: list[AssetVariantV1] = Field(default_factory=list)
    created_at: datetime


class AssetBindingV1(StrictModel):
    """Associates a reusable CDN asset with a statblock form or presentation role."""

    asset: AssetRefV1
    role: AssetRoleV1
    phase_key: str | None = Field(default=None, min_length=1)
