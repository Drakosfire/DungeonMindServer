"""Asset gateway boundary for optional candidate image generation."""
from __future__ import annotations

from typing import Protocol

from statblocks_v1.domain.assets import AssetBriefV1, AssetRefV1


class AssetGateway(Protocol):
    """Creates durable CDN-backed refs; it never returns image bytes."""

    def generate(self, brief: AssetBriefV1) -> list[AssetRefV1]: ...
