"""Deterministic asset gateway fake for isolated v1 tests."""
from __future__ import annotations

from statblocks_v1.domain.assets import AssetBriefV1, AssetRefV1


class FakeAssetGateway:
    def __init__(self, assets: list[AssetRefV1] | None = None, error: Exception | None = None) -> None:
        self.assets = assets or []
        self.error = error
        self.briefs: list[AssetBriefV1] = []

    def generate(self, brief: AssetBriefV1) -> list[AssetRefV1]:
        self.briefs.append(brief)
        if self.error is not None:
            raise self.error
        return [asset.model_copy(deep=True) for asset in self.assets]
