"""Thin v1 adapter for a configured Cloudflare/image-pipeline callable."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from statblocks_v1.domain.assets import AssetBriefV1, AssetRefV1

PipelineGenerate = Callable[[AssetBriefV1], list[AssetRefV1 | dict[str, Any]]]


class CloudflareAssetGateway:
    """Normalizes pipeline responses without importing or altering legacy routers.

    The wrapped pipeline must return its durable asset ID and canonical CDN URL.
    This adapter intentionally never derives IDs from URLs.
    """

    def __init__(self, generate: PipelineGenerate) -> None:
        self._generate = generate

    def generate(self, brief: AssetBriefV1) -> list[AssetRefV1]:
        return [asset if isinstance(asset, AssetRefV1) else AssetRefV1.model_validate(asset)
                for asset in self._generate(brief)]
