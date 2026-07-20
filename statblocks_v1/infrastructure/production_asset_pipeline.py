"""Production asset pipeline bridge for Cloudflare-backed portraits.

Owns the sync ``PipelineGenerate`` surface used by ``CloudflareAssetGateway``.
Failures raise so ``GenerationServiceV1`` can emit asset warnings without
failing mechanics generation.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

import httpx

from statblocks_v1.domain.assets import AssetBriefV1, AssetRefV1


def generate_assets(brief: AssetBriefV1) -> list[AssetRefV1]:
    """Upload a source image URL to Cloudflare Images and return a durable AssetRef.

    The brief prompt must be an ``https`` image source until a dedicated portrait
    generator is configured. Cloudflare's response supplies both ``id`` and CDN URL
    — this adapter never invents IDs from URLs alone.
    """
    prompt = brief.prompt.strip()
    if not prompt.startswith(("http://", "https://")):
        raise RuntimeError(
            "production asset pipeline requires an https image source URL in the brief prompt "
            "until a dedicated portrait generator is configured"
        )
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
    api_token = os.getenv("CLOUDFLARE_IMAGES_API_TOKEN")
    if not account_id or not api_token:
        raise RuntimeError("Cloudflare Images credentials are not configured")

    async def _upload() -> AssetRefV1:
        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/images/v1"
        headers = {"Authorization": f"Bearer {api_token}"}
        files = {
            "url": (None, prompt),
            "requireSignedURLs": (None, "false"),
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, files=files)
        if response.status_code != 200:
            raise RuntimeError(f"Cloudflare Images upload failed: HTTP {response.status_code}")
        result = response.json().get("result") or {}
        asset_id = str(result.get("id") or "").strip()
        variants = result.get("variants") or []
        public_url = str(variants[0] if variants else "").strip()
        if not asset_id or not public_url:
            raise RuntimeError("Cloudflare Images upload omitted durable id/url")
        if not public_url.endswith("/Full"):
            public_url = "/".join(public_url.split("/")[:-1]) + "/Full"
        return AssetRefV1(
            asset_id=asset_id,
            provider_kind="cloudflare_images",
            url=public_url,
            mime_type="image/png",
            prompt=brief.prompt,
            generation_provenance="statblocks_v1.infrastructure.production_asset_pipeline",
            created_at=datetime.now(timezone.utc),
        )

    return [asyncio.run(_upload())]
