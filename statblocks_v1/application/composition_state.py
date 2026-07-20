"""Composition readiness helpers shared by health and route gates."""
from __future__ import annotations

_asset_pipeline_ready = False


def set_asset_pipeline_ready(ready: bool) -> None:
    global _asset_pipeline_ready
    _asset_pipeline_ready = ready


def asset_pipeline_ready() -> bool:
    return _asset_pipeline_ready


def generation_available(
    *,
    feature_enabled: bool,
    openai_api_key: str | None,
    firestore_enabled: bool,
    asset_gateway_enabled: bool,
) -> bool:
    """Generation requires feature flag, provider key, Firestore, and assets when enabled."""
    if not feature_enabled:
        return False
    if not openai_api_key:
        return False
    if not firestore_enabled:
        return False
    if asset_gateway_enabled and not _asset_pipeline_ready:
        return False
    return True
