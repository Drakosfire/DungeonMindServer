"""
Prompt compiler for map generation.

Two-stage pipeline:
1. generate_mapspec: User prompt + style options → MapSpec (structured JSON)
2. compile_image_prompt: MapSpec → Natural language image prompt

Reference style: The Migrating Forest battle map prompts
- Opening with scale and scene description
- Terrain/layout details with tactical implications
- Movement and cover considerations
- Environmental storytelling through absence/implication
- Style line at the end with palette, contrast, and composition notes
"""

import json
import logging
from datetime import datetime
from typing import Optional

from generationengine import TextGenerationService, TextGenerationRequest, TextModel

from .models import MapSpec
from .prompts import (
    MAPSPEC_SYSTEM_PROMPT,
    HARD_CONSTRAINTS_FORBID,
    PROMPT_COMPILER_TEMPLATE,
    SCALE_DESCRIPTIONS,
    RENDERING_DESCRIPTIONS,
    MASK_PROMPT_SUFFIX,
    INPAINTING_PROMPT_TEMPLATE,
)
from .prompt_config import get_defaults

logger = logging.getLogger(__name__)


async def generate_mapspec(
    user_prompt: str,
    style_options: Optional[dict] = None,
    defaults: Optional[dict] = None,
) -> MapSpec:
    """
    Stage 1: Convert user prompt + toggles into structured MapSpec.
    
    Uses OpenAI to parse and structure the user's intent.
    """
    if style_options is None:
        style_options = {}
    if defaults is None:
        defaults = get_defaults()
    
    text_service = TextGenerationService()
    
    combined_prompt = f"""
USER_TEXT:
<<<{user_prompt}>>>

OPTIONAL_FIELDS:
<<<{json.dumps(style_options)}>>>

DEFAULTS:
<<<{json.dumps(defaults)}>>>
"""
    
    # Get schema from MapSpec model
    schema = MapSpec.model_json_schema()
    
    request = TextGenerationRequest(
        system_prompt=MAPSPEC_SYSTEM_PROMPT,
        user_prompt=combined_prompt,
        model=TextModel.GPT_5_1,
        temperature=0.7,
        response_schema=schema,
        response_schema_name="mapspec",
        max_tokens=800,  # Constrain upfront to keep compiled prompt under 2000 chars
    )
    
    result = await text_service.generate(request)
    
    if not result.success:
        error_msg = result.error.message if result.error else "Unknown error"
        logger.error(f"❌ [PromptCompiler] MapSpec generation failed: {error_msg}")
        raise Exception(f"MapSpec generation failed: {error_msg}")
    
    # Parse and validate
    try:
        # Use parsed_content (already a dict) when structured outputs are used
        # Fall back to parsing content string if needed
        if result.parsed_content:
            mapspec_dict = result.parsed_content
        elif result.content:
            mapspec_dict = json.loads(result.content)
        else:
            raise ValueError("No content in response")
        
        mapspec = MapSpec.model_validate(mapspec_dict)
    except Exception as e:
        logger.error(f"❌ [PromptCompiler] Failed to parse MapSpec: {str(e)}")
        raise Exception(f"Failed to parse MapSpec: {str(e)}")
    
    # Ensure hard constraints are always included
    mapspec.constraints.forbid = list(set(
        mapspec.constraints.forbid + HARD_CONSTRAINTS_FORBID
    ))
    
    # Ensure meta fields are set
    if not mapspec.meta.timestamp:
        mapspec.meta.timestamp = datetime.now()
    if not mapspec.meta.source_prompt:
        mapspec.meta.source_prompt = user_prompt
    
    logger.info(f"✅ [PromptCompiler] MapSpec generated: {mapspec.intent.summary}")
    
    return mapspec


def compile_image_prompt(mapspec: MapSpec, has_mask: bool = False) -> str:
    """
    Stage 2: Convert structured MapSpec into natural language image prompt.
    
    Output style matches The Migrating Forest battle map prompts:
    - Opening with scale and scene description
    - Terrain/layout details with tactical implications
    - Movement and cover considerations
    - Style line with palette, contrast, and composition
    
    Args:
        mapspec: Structured MapSpec to compile
        has_mask: If True, append mask boundary constraints for inpainting
    
    Returns:
        Compiled natural language prompt
    """
    # Get scale description
    scale_description = SCALE_DESCRIPTIONS.get(
        mapspec.layout.scale, 
        mapspec.layout.scale
    )
    
    # Build elevation clause
    elevation_clause = ""
    if mapspec.layout.elevation_present and mapspec.layout.elevation_description:
        elevation_clause = f" with {mapspec.layout.elevation_description}"
    
    # Build terrain description
    env = mapspec.environment
    terrain_parts = []
    
    if env.terrain:
        terrain_parts.append(f"The terrain features {', '.join(env.terrain)}")
    if env.vegetation:
        terrain_parts.append(f"with {', '.join(env.vegetation)}")
    if env.materials:
        terrain_parts.append(f"composed of {', '.join(env.materials)}")
    if env.water_features:
        terrain_parts.append(f"including {', '.join(env.water_features)}")
    if env.props:
        terrain_parts.append(f"featuring {', '.join(env.props)}")
    
    terrain_description = " ".join(terrain_parts) if terrain_parts else "Natural terrain with varied surfaces."
    
    # Build layout description
    layout = mapspec.layout
    layout_parts = []
    
    if layout.central_feature:
        layout_parts.append(f"The layout centers on {layout.central_feature}")
    if layout.focal_point:
        layout_parts.append(f"with {layout.focal_point} as the focal point")
    if layout.surrounding_elements:
        layout_parts.append(f"surrounded by {', '.join(layout.surrounding_elements)}")
    
    # Add pathway description
    pathway_descriptions = {
        "radial": "Paths radiate outward from the center",
        "organic": "Paths curve organically through the space",
        "linear": "Clear linear paths cross the area",
        "gridless": "Movement flows freely without defined paths",
    }
    if layout.pathways in pathway_descriptions:
        layout_parts.append(pathway_descriptions[layout.pathways])
    
    layout_description = ". ".join(layout_parts) + "." if layout_parts else ""
    
    # Build tactical description based on gameplay settings
    gameplay = mapspec.gameplay
    tactical_parts = []
    
    # Movement space
    movement_descriptions = {
        "open": "Broad open areas allow tactical freedom and clear sightlines",
        "mixed": "A mix of open areas and obstacles creates varied tactical options",
        "tight": "Narrow passages and dense obstacles create close-quarters tactical challenges",
    }
    if gameplay.movement_space in movement_descriptions:
        tactical_parts.append(movement_descriptions[gameplay.movement_space])
    
    # Cover density
    cover_descriptions = {
        "light": "with minimal hard cover, emphasizing positioning over protection",
        "medium": "with moderate cover distributed across the battlefield",
        "heavy": "with abundant cover creating ambush-friendly terrain",
    }
    if gameplay.cover_density in cover_descriptions:
        tactical_parts.append(cover_descriptions[gameplay.cover_density])
    
    tactical_description = ", ".join(tactical_parts) + "." if tactical_parts else ""
    
    # Build rendering description
    rendering_description = RENDERING_DESCRIPTIONS.get(
        mapspec.style.rendering,
        "Hand-painted fantasy battle map"
    )
    
    # Build palette description
    palette = mapspec.style.palette
    palette_parts = []
    
    # Saturation
    if palette.saturation == "muted":
        palette_parts.append("muted colors")
    elif palette.saturation == "balanced":
        palette_parts.append("balanced saturation")
    elif palette.saturation == "vibrant":
        palette_parts.append("vibrant colors")
    
    # Temperature
    if palette.temperature == "cool":
        palette_parts.append("cool tones")
    elif palette.temperature == "warm":
        palette_parts.append("warm undertones")
    # neutral omitted as it's the default
    
    # Contrast
    if palette.contrast == "high":
        palette_parts.append("high contrast between paths and obstacles")
    elif palette.contrast == "low":
        palette_parts.append("low contrast for subtle transitions")
    elif palette.contrast == "medium":
        palette_parts.append("moderate contrast")
    
    palette_description = ", ".join(palette_parts) if palette_parts else "muted colors, high contrast"
    
    # Build composition notes based on tone and readability
    composition_parts = ["clean silhouettes", "optimized for tabletop readability"]
    
    if mapspec.intent.tone == "gritty":
        composition_parts.insert(0, "earthy muted palette")
    elif mapspec.intent.tone == "whimsical":
        composition_parts.insert(0, "soft natural lighting")
    else:  # neutral
        composition_parts.insert(0, "cool neutral lighting")
    
    composition_notes = ", ".join(composition_parts)
    
    # Compile final prompt
    prompt = PROMPT_COMPILER_TEMPLATE.format(
        intent_summary=mapspec.intent.summary,
        scale_description=scale_description,
        elevation_clause=elevation_clause,
        terrain_description=terrain_description,
        layout_description=layout_description,
        tactical_description=tactical_description,
        rendering_description=rendering_description,
        palette_description=palette_description,
        composition_notes=composition_notes,
    )
    
    # Clean up any double spaces or trailing whitespace
    prompt = " ".join(prompt.split())
    prompt = prompt.replace(" .", ".").replace("..", ".")
    
    # Append mask constraints if inpainting mode
    if has_mask:
        prompt = f"{prompt}\n{MASK_PROMPT_SUFFIX}"
        logger.info("🎭 [PromptCompiler] Mask constraints appended to prompt")
    
    # Warn if prompt exceeds limit (shouldn't happen with max_tokens=800 on MapSpec)
    if len(prompt) > 2000:
        logger.warning(f"⚠️ [PromptCompiler] Prompt exceeds 2000 chars ({len(prompt)}), may be truncated by image API")
    
    logger.info(f"✅ [PromptCompiler] Image prompt compiled: {len(prompt)} chars")
    
    return prompt


def compile_inpainting_prompt(user_description: str) -> str:
    """
    Compile a targeted prompt for inpainting.
    
    Unlike compile_image_prompt (which describes an entire map),
    this creates a focused prompt for filling a masked region.
    
    Args:
        user_description: What the user wants in the masked region
            (e.g., "a campfire with bedrolls", "a stone bridge over a stream")
    
    Returns:
        Compiled inpainting prompt (~200-400 chars vs ~800+ for full map)
    """
    # Clean up user input
    description = user_description.strip()
    
    # Capitalize first letter if not already
    if description and description[0].islower():
        description = description[0].upper() + description[1:]
    
    # Compile using the inpainting template
    prompt = INPAINTING_PROMPT_TEMPLATE.format(user_description=description)
    
    # Clean up whitespace
    prompt = prompt.strip()
    
    logger.info(f"🎭 [PromptCompiler] Inpainting prompt compiled: {len(prompt)} chars")
    logger.debug(f"🎭 [PromptCompiler] Inpainting prompt: {prompt[:100]}...")
    
    return prompt


def get_inpainting_negative_prompt() -> str:
    """
    Get the standard negative prompt for map inpainting.
    
    Returns:
        Comma-separated list of elements to avoid
    """
    return ", ".join(HARD_CONSTRAINTS_FORBID)
