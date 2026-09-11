"""
Inpainting Service

Handles mask-based image generation for region-specific map content.
Implements TDD tests from T181, T202.
"""

import logging
from typing import Optional, Tuple

from PIL import Image

from generationengine import GenerationEngineError, ImageRequest
from shared.generation import get_generation_client
from shared.generated_images import publish_generated_image
from shared.inference_policy import inference_for
from security_limits.image_bounds import (
    decode_data_uri_bounded,
    encode_image_data_uri,
)

logger = logging.getLogger(__name__)


class InpaintingValidationError(Exception):
    """Raised when mask or base image validation fails."""
    pass


# Standard dimensions for all inpainting operations
STANDARD_INPAINT_SIZE = (1024, 1024)


def _decode_base64_image(base64_str: str, *, field: str) -> Image.Image:
    """Decode a data URI under encoded/decoded/dimension caps. Rejects on failure."""
    try:
        return decode_data_uri_bounded(base64_str, field=field)
    except Exception as e:
        # FastAPI HTTPException from bounds helpers → surface as validation error
        detail = getattr(e, "detail", None) or str(e)
        raise InpaintingValidationError(str(detail)) from e


def _encode_image_to_base64(image: Image.Image, format: str = "PNG") -> str:
    """Encode a PIL Image to a base64 data URI."""
    return encode_image_data_uri(image, fmt=format)


def _get_image_dimensions(base64_str: str, *, field: str) -> Tuple[int, int]:
    """Get dimensions of a base64-encoded image under bounded decode."""
    image = _decode_base64_image(base64_str, field=field)
    return image.size  # (width, height)


def _resize_image_to_standard(base64_str: str, *, field: str, use_nearest: bool = False) -> str:
    """
    Resize an image to the standard inpainting dimensions (1024x1024).

    Raises InpaintingValidationError if decode/bounds fail.
    """
    image = _decode_base64_image(base64_str, field=field)

    # For masks, preserve alpha channel and use NEAREST to keep hard edges
    if use_nearest:
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        resampling = Image.Resampling.NEAREST
    else:
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
        resampling = Image.Resampling.LANCZOS

    resized = image.resize(STANDARD_INPAINT_SIZE, resampling)
    return _encode_image_to_base64(resized, "PNG")


async def generate_inpainted_map(
    prompt: str,
    mask_base64: str,
    base_image_base64: str,
    style_options: Optional[dict] = None,
    negative_prompt: Optional[str] = None,
) -> str:
    """
    Generate content within masked regions of an image.

    Raises:
        InpaintingValidationError: If mask or base image is invalid / oversized
        Exception: If generation fails
    """
    logger.info("🎭 [Inpainting] Starting masked generation")

    if not mask_base64:
        raise InpaintingValidationError("Mask is required")
    if not base_image_base64:
        raise InpaintingValidationError("Base image is required")

    # Bound decode + dimension check first — reject, never proceed on failure
    mask_dims = _get_image_dimensions(mask_base64, field="maskBase64")
    base_dims = _get_image_dimensions(base_image_base64, field="baseImageBase64")

    logger.info(
        "Inpainting input dims mask=%sx%s base=%sx%s",
        mask_dims[0],
        mask_dims[1],
        base_dims[0],
        base_dims[1],
    )

    if mask_dims != STANDARD_INPAINT_SIZE:
        mask_base64 = _resize_image_to_standard(
            mask_base64, field="maskBase64", use_nearest=True
        )
    if base_dims != STANDARD_INPAINT_SIZE:
        base_image_base64 = _resize_image_to_standard(
            base_image_base64, field="baseImageBase64", use_nearest=False
        )

    logger.info(
        "Inpainting prompt_chars=%s mask_chars=%s base_chars=%s",
        len(prompt),
        len(mask_base64),
        len(base_image_base64),
    )

    if len(prompt) > 8000:
        prompt = prompt[:8000]

    action = inference_for("map_image_edit")
    client = get_generation_client()
    request = ImageRequest(
        prompt=prompt,
        negative_prompt=negative_prompt,
        profile=action.profile,
        model=action.model,
        num_images=1,
        width=STANDARD_INPAINT_SIZE[0],
        height=STANDARD_INPAINT_SIZE[1],
        mask_base64=mask_base64,
        base_image_base64=base_image_base64,
    )

    if not request.mask_base64 or not request.base_image_base64:
        raise InpaintingValidationError("ImageRequest missing mask or base_image")

    try:
        result = await client.edit_image(request)
    except GenerationEngineError as error:
        logger.error("❌ [Inpainting] Generation failed: %s", error.failure.message)
        raise Exception(f"Inpainting generation failed: {error.failure.message}") from error
    except Exception as e:
        logger.error("❌ [Inpainting] Generation failed: %s", type(e).__name__)
        raise

    if not result.images:
        raise Exception("Inpainting generation failed: no images returned")

    uploaded = await publish_generated_image(result.images[0])
    logger.info("✅ [Inpainting] Generation complete")
    return uploaded.url
