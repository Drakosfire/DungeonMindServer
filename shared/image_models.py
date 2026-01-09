"""
Shared image generation model configuration.

Single source of truth for model mappings used across routers.
"""

from generationengine import ImageModel

# Map frontend model IDs to GenerationEngine ImageModel enum
# All models support both text-to-image and inpainting via /edit endpoints
MODEL_MAP = {
    "flux-2-pro": ImageModel.FLUX_2_PRO,
    "nano-banana-pro": ImageModel.NANO_BANANA_PRO,
    "gpt-image-1.5": ImageModel.GPT_IMAGE_15,
}

# Capabilities returned by /api/images/capabilities
# This defines what the frontend UI shows in the model selector
IMAGE_CAPABILITIES = {
    "models": [
        {
            "id": "flux-2-pro",
            "name": "FLUX 2 Pro",
            "description": "High quality, balanced speed (~10s)",
            "default": True,
            "tier": "free"
        },
        {
            "id": "nano-banana-pro",
            "name": "Nano Banana Pro",
            "description": "Ultra-fast, aspect ratio support (~3s)",
            "tier": "free"
        },
        {
            "id": "gpt-image-1.5",
            "name": "GPT Image 1.5",
            "description": "OpenAI GPT-4 Vision powered (~5s)",
            "tier": "free"
        },
    ],
    "styles": [
        {
            "id": "classic_dnd",
            "name": "Classic D&D",
            "suffix": "in the style of classic Dungeons & Dragons art, detailed fantasy illustration, TSR era artwork",
            "default": True
        },
        {
            "id": "oil_painting",
            "name": "Oil Painting",
            "suffix": "oil painting, traditional fantasy art, detailed brushwork, museum quality"
        },
        {
            "id": "fantasy_book",
            "name": "Fantasy Book Cover",
            "suffix": "epic fantasy book cover art, dramatic lighting, professional illustration, cinematic composition"
        },
        {
            "id": "dark_gothic",
            "name": "Dark Gothic",
            "suffix": "dark gothic fantasy art, dramatic shadows, moody atmosphere, horror elements"
        },
        {
            "id": "anime",
            "name": "Anime Style",
            "suffix": "anime fantasy art, vibrant colors, dynamic pose, Japanese animation style"
        },
        {
            "id": "sketch",
            "name": "Pencil Sketch",
            "suffix": "detailed pencil sketch, fantasy concept art, monochrome, graphite drawing"
        },
        {
            "id": "watercolor",
            "name": "Watercolor",
            "suffix": "watercolor painting, soft colors, fantasy illustration, flowing pigments"
        },
        {
            "id": "digital_art",
            "name": "Modern Digital",
            "suffix": "modern digital fantasy art, high detail, concept art quality, professional rendering"
        },
        {
            "id": "realistic",
            "name": "Photorealistic",
            "suffix": "photorealistic fantasy creature, highly detailed, 8k resolution, cinematic lighting"
        }
    ],
    "maxImages": 4,
    "defaultNumImages": 4
}

