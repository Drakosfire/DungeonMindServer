"""
Inpainting Service

Handles mask-based image generation for region-specific map content.
Implements TDD tests from T181, T202.
"""

import logging
from typing import Optional

from generationengine import ImageService, ImageGenerationRequest, ImageModel, ImageSize

logger = logging.getLogger(__name__)


class InpaintingValidationError(Exception):
    """Raised when mask or base image validation fails."""
    pass


async def generate_inpainted_map(
    prompt: str,
    mask_base64: str,
    base_image_base64: str,
    style_options: Optional[dict] = None,
    negative_prompt: Optional[str] = None,
) -> str:
    """
    Generate content within masked regions of an image.
    
    Args:
        prompt: Text prompt describing what to generate
        mask_base64: Base64-encoded PNG mask (transparent = generate)
        base_image_base64: Base64-encoded PNG base image
        style_options: Optional style configuration
        negative_prompt: Elements to exclude from generation (e.g., "grid, text, characters")
        
    Returns:
        URL to the generated image
        
    Raises:
        InpaintingValidationError: If mask or base image is invalid
        Exception: If generation fails
    """
    logger.info("🎭 [Inpainting] Starting masked generation")
    
    # Validate base64 format
    if not mask_base64:
        raise InpaintingValidationError("Mask is required")
    
    if not base_image_base64:
        raise InpaintingValidationError("Base image is required")
    
    if not mask_base64.startswith('data:image/'):
        raise InpaintingValidationError("Invalid mask format: must be base64-encoded image (data:image/...)")
    
    if not base_image_base64.startswith('data:image/'):
        raise InpaintingValidationError("Invalid base image format: must be base64-encoded image (data:image/...)")
    
    # Log validation success
    mask_size_kb = len(mask_base64) / 1024
    base_size_kb = len(base_image_base64) / 1024
    logger.info(f"✅ [Inpainting] Validation passed: mask={mask_size_kb:.1f}KB, base_image={base_size_kb:.1f}KB")
    
    # Note: prompt already includes mask constraints from compile_image_prompt()
    # No need to append MASK_PROMPT_SUFFIX again here
    logger.info(f"🎭 [Inpainting] Prompt length: {len(prompt)} chars")
    logger.debug(f"🎭 [Inpainting] Prompt (first 200 chars): {prompt[:200]}...")
    logger.info(f"🎭 [Inpainting] Mask: {len(mask_base64)} chars, Base image: {len(base_image_base64)} chars")
    
    # Validate prompt length (should be handled by prompt compiler, but double-check)
    if len(prompt) > 2000:
        logger.warning(f"⚠️ [Inpainting] Prompt still exceeds 2000 chars ({len(prompt)}), truncating to 2000...")
        prompt = prompt[:2000]
    
    # Initialize image service
    image_service = ImageService()
    
    # Create generation request with inpainting parameters
    # Using GPT_IMAGE_15 with fal-ai/gpt-image-1.5/edit endpoint (best for inpainting)
    logger.info("🎨 [Inpainting] Creating ImageGenerationRequest with GPT Image 1.5 for edit")
    request = ImageGenerationRequest(
        prompt=prompt,
        negative_prompt=negative_prompt,
        model=ImageModel.GPT_IMAGE_15,  # Uses fal-ai/gpt-image-1.5/edit endpoint
        num_images=1,
        size=ImageSize.SQUARE,
        mask_base64=mask_base64,
        base_image_base64=base_image_base64,
    )
    
    # Verify request has inpainting parameters
    if not request.mask_base64 or not request.base_image_base64:
        raise InpaintingValidationError("ImageGenerationRequest missing mask or base_image")
    logger.info("✅ [Inpainting] ImageGenerationRequest validated with inpainting parameters")
    
    try:
        result = await image_service.generate(request)
    except Exception as e:
        logger.error(f"❌ [Inpainting] Generation failed: {e}")
        raise
    
    if not result.success or not result.images:
        error_msg = result.error.message if result.error else "Unknown error"
        raise Exception(f"Inpainting generation failed: {error_msg}")
    
    image_url = result.images[0].url
    if not image_url:
        raise Exception("Inpainting generation failed: no image URL in response")
    
    logger.info(f"✅ [Inpainting] Generation complete: {image_url[:50]}...")
    return image_url
