"""Production asset pipeline: prose brief → image generator → Cloudflare Images.

``AssetBriefV1.prompt`` is generation intent (authored description / name), not an
image URL. This adapter generates a temporary image, then uploads it to Cloudflare
Images so the returned ``AssetRefV1`` carries a durable provider id and CDN URL.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

import httpx

from statblocks_v1.domain.assets import AssetBriefV1, AssetRefV1

_PORTRAIT_SUFFIX = (
    "Detailed fantasy creature portrait for a TTRPG statblock, centered subject, "
    "classic Dungeons & Dragons illustration style"
)


def production_asset_credentials_ready() -> bool:
    """True when both image generation and durable CDN upload credentials exist."""
    return bool(
        os.getenv("FAL_KEY", "").strip()
        and os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
        and os.getenv("CLOUDFLARE_IMAGES_API_TOKEN", "").strip()
    )


def generate_assets(brief: AssetBriefV1) -> list[AssetRefV1]:
    """Generate from prose intent and persist a durable Cloudflare Images asset."""
    if not production_asset_credentials_ready():
        raise RuntimeError("production asset pipeline credentials are not configured")
    prompt = brief.prompt.strip()
    if not prompt:
        raise RuntimeError("asset brief prompt is empty")
    temporary_url = _generate_temporary_image_url(prompt)
    return [_upload_temporary_url(temporary_url, prompt=prompt)]


def _generate_temporary_image_url(prompt: str) -> str:
    """Text-to-image via fal; returns a temporary provider URL (not durable)."""
    import fal_client

    composed = f"{prompt}. {_PORTRAIT_SUFFIX}"
    result = fal_client.subscribe(
        "fal-ai/flux/dev",
        arguments={
            "prompt": composed,
            "num_inference_steps": 28,
            "guidance_scale": 3.5,
            "num_images": 1,
        },
    )
    images = result.get("images") if isinstance(result, dict) else None
    if not images:
        raise RuntimeError("image generator returned no images")
    url = str(images[0].get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        raise RuntimeError("image generator omitted a usable image URL")
    return url


def _upload_temporary_url(image_url: str, *, prompt: str) -> AssetRefV1:
    return asyncio.run(_upload_temporary_url_async(image_url, prompt=prompt))


async def _upload_temporary_url_async(image_url: str, *, prompt: str) -> AssetRefV1:
    account_id = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    api_token = os.environ["CLOUDFLARE_IMAGES_API_TOKEN"]
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/images/v1"
    headers = {"Authorization": f"Bearer {api_token}"}
    files = {
        "url": (None, image_url),
        "requireSignedURLs": (None, "false"),
    }
    async with httpx.AsyncClient(timeout=60) as client:
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
        prompt=prompt,
        generation_provenance="statblocks_v1.infrastructure.production_asset_pipeline",
        created_at=datetime.now(timezone.utc),
    )
