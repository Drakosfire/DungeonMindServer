"""
Shared image generation model configuration.

Single source of truth for model mappings used across routers.
"""

from generationengine import ImageModel

# Map frontend model IDs to GenerationEngine ImageModel enum
MODEL_MAP = {
    "flux-pro": ImageModel.FLUX_PRO,
    "openai": ImageModel.OPENAI,
    "nano-banana": ImageModel.NANO_BANANA,
    "hunyuan": ImageModel.HUNYUAN,
    "dreamina": ImageModel.DREAMINA,
    "flux-kontext": ImageModel.FLUX_KONTEXT,
}

# Capabilities returned by /api/images/capabilities
# This defines what the frontend UI shows in the model selector
IMAGE_CAPABILITIES = {
    "models": [
        {
            "id": "flux-pro",
            "name": "FLUX Pro",
            "description": "High quality, balanced speed (~10s)",
            "default": True,
            "tier": "free"
        },
        {
            "id": "flux-kontext",
            "name": "FLUX Kontext Max",
            "description": "Advanced FLUX with context understanding (~12s)",
            "tier": "free"
        },
        {
            "id": "hunyuan",
            "name": "Hunyuan v3",
            "description": "Tencent's high-quality model (~8s)",
            "tier": "free"
        },
        {
            "id": "dreamina",
            "name": "Dreamina v3.1",
            "description": "ByteDance's creative model (~6s)",
            "tier": "free"
        },
        {
            "id": "nano-banana",
            "name": "Nano Banana",
            "description": "Ultra-fast, aspect ratio support (~3s)",
            "tier": "free"
        },
        {
            "id": "openai",
            "name": "OpenAI GPT-Image",
            "description": "Fast, cost-effective (~5s)",
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

