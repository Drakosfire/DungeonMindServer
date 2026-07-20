"""Unit coverage for the production prose→image→CDN asset adapter."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from statblocks_v1.domain.assets import AssetBriefV1
from statblocks_v1.infrastructure import production_asset_pipeline as pipeline


def test_credentials_ready_requires_fal_and_cloudflare(monkeypatch) -> None:
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_IMAGES_API_TOKEN", raising=False)
    assert pipeline.production_asset_credentials_ready() is False

    monkeypatch.setenv("FAL_KEY", "fal")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_IMAGES_API_TOKEN", "token")
    assert pipeline.production_asset_credentials_ready() is True


def test_generate_assets_uses_prose_prompt_not_url(monkeypatch) -> None:
    monkeypatch.setenv("FAL_KEY", "fal")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_IMAGES_API_TOKEN", "token")

    captured: dict[str, str] = {}

    def fake_generate(prompt: str) -> str:
        captured["prompt"] = prompt
        return "https://fal.media/tmp/generated.png"

    def fake_upload(image_url: str, *, prompt: str):
        captured["upload_url"] = image_url
        captured["upload_prompt"] = prompt
        from statblocks_v1.domain.assets import AssetRefV1

        return AssetRefV1(
            asset_id="cf_durable_1",
            provider_kind="cloudflare_images",
            url="https://imagedelivery.net/acct/cf_durable_1/Full",
            mime_type="image/png",
            prompt=prompt,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    monkeypatch.setattr(pipeline, "_generate_temporary_image_url", fake_generate)
    monkeypatch.setattr(pipeline, "_upload_temporary_url", fake_upload)

    refs = pipeline.generate_assets(
        AssetBriefV1(prompt="A scarred ironhide brute with cracked armor")
    )
    assert "scarred ironhide" in captured["prompt"].lower()
    assert not captured["prompt"].startswith("http")
    assert captured["upload_url"] == "https://fal.media/tmp/generated.png"
    assert refs[0].asset_id == "cf_durable_1"
    assert str(refs[0].url).endswith("/Full")


def test_generate_assets_fails_closed_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv("FAL_KEY", raising=False)
    with pytest.raises(RuntimeError, match="credentials"):
        pipeline.generate_assets(AssetBriefV1(prompt="a goblin"))
