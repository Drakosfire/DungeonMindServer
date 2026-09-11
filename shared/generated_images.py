"""Publish GenerationEngine image bytes through DungeonMindServer Cloudflare."""

from __future__ import annotations

from generationengine import GeneratedImage
from cloudflare.handle_images import CloudflareUploadResult, upload_generated_image_bytes


async def publish_generated_image(image: GeneratedImage) -> CloudflareUploadResult:
    return await upload_generated_image_bytes(
        image.content,
        media_type=image.media_type or "image/png",
    )
