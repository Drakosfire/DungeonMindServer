"""
SVG Mask Generation Service

Generates mask images from text descriptions using LLM-generated SVG.

Flow:
1. User text → LLM → SVG string
2. SVG string → cairosvg → PNG bytes  
3. PNG color conversion → RGBA mask (transparent = generate, opaque = keep)
"""

import base64
import io
import logging
import re

import cairosvg
from PIL import Image

from generationengine import GenerationEngineError, TextRequest
from shared.generation import get_generation_client
from shared.inference_policy import profile_for

logger = logging.getLogger(__name__)

# Standard dimensions matching inpainting system
STANDARD_MASK_SIZE = 1024

# SVG generation prompt template
SVG_SYSTEM_PROMPT = """You are an expert at creating SVG masks for fantasy TTRPG battle maps.

Your task is to generate an SVG that represents a map layout mask based on a text description.

CRITICAL RULES:
1. Output ONLY valid SVG code - no explanation, no markdown, no commentary
2. The SVG must have viewBox="0 0 768 768" and xmlns="http://www.w3.org/2000/svg"
3. Use ONLY these elements: rect, circle, ellipse, path, polygon, line
4. Use ONLY solid fills - no gradients, no patterns, no filters
5. WHITE (#FFFFFF or white) areas represent the MAP CONTENT (will be kept)
6. BLACK (#000000 or black) areas represent SURROUNDING/WALLS (will be regenerated)
7. Start with a black background rectangle, then add white shapes for the map content
8. No text, no labels, no images
9. Keep shapes simple and recognizable from top-down view

SHAPE GUIDELINES:
- Rooms/chambers: Use rect or polygon with rounded appearance
- Corridors: Use long thin rect or path elements
- Caves: Use organic path or ellipse elements
- Rivers/water: Use wavy path elements
- Circular areas: Use circle or ellipse

EXAMPLE OUTPUT for "a dungeon with three rooms connected by corridors":
<svg viewBox="0 0 768 768" xmlns="http://www.w3.org/2000/svg">
  <rect width="768" height="768" fill="black"/>
  <rect x="100" y="100" width="200" height="200" fill="white" rx="10"/>
  <rect x="468" y="100" width="200" height="200" fill="white" rx="10"/>
  <rect x="284" y="468" width="200" height="200" fill="white" rx="10"/>
  <rect x="200" y="175" width="268" height="50" fill="white"/>
  <rect x="359" y="300" width="50" height="168" fill="white"/>
</svg>
"""

SVG_USER_PROMPT_TEMPLATE = """Create an SVG mask for this map description:

{description}

Remember:
- Black background for walls/surroundings
- White shapes for map content areas
- Keep it simple and tactical
- Output ONLY the SVG code"""


def _validate_svg(svg_string: str) -> bool:
    """
    Validate that the SVG string is safe and well-formed.
    
    Args:
        svg_string: The SVG string to validate
        
    Returns:
        True if valid, raises ValueError otherwise
    """
    # Check for required elements
    if '<svg' not in svg_string.lower():
        raise ValueError("Missing <svg> element")
    
    if '</svg>' not in svg_string.lower():
        raise ValueError("Missing closing </svg> tag")
    
    # Check for viewBox (case-insensitive)
    if 'viewbox' not in svg_string.lower():
        raise ValueError("Missing viewBox attribute")
    
    # Security checks - disallow potentially dangerous elements
    dangerous_patterns = [
        r'<script',
        r'javascript:',
        r'on\w+\s*=',  # Event handlers like onclick, onload
        r'<foreignObject',
        r'<iframe',
        r'<embed',
        r'<object',
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, svg_string, re.IGNORECASE):
            raise ValueError(f"Potentially dangerous content detected: {pattern}")
    
    return True


def _extract_svg(response_text: str) -> str:
    """
    Extract SVG content from LLM response.
    
    Handles cases where the LLM wraps SVG in markdown code blocks.
    
    Args:
        response_text: Raw LLM response
        
    Returns:
        Clean SVG string
    """
    text = response_text.strip()
    
    # Try to extract from markdown code block
    svg_match = re.search(r'```(?:svg|xml)?\s*(.*?)\s*```', text, re.DOTALL)
    if svg_match:
        text = svg_match.group(1).strip()
    
    # Find the SVG tag
    svg_start = text.lower().find('<svg')
    svg_end = text.lower().rfind('</svg>')
    
    if svg_start == -1 or svg_end == -1:
        raise ValueError("Could not find valid SVG in response")
    
    # Extract the SVG (preserve original case)
    svg_string = text[svg_start:svg_end + 6]
    
    return svg_string


def _convert_colors_to_alpha(image: Image.Image) -> Image.Image:
    """
    Convert a black/white image to RGBA mask format.
    
    The inpainting system uses alpha channel for masking:
    - Transparent (alpha=0) = generate new content
    - Opaque (alpha=255) = keep existing content
    
    In our SVG:
    - Black = walls/surroundings → should be REGENERATED → transparent
    - White = map content → should be KEPT → opaque
    
    Args:
        image: PIL Image (RGB or RGBA)
        
    Returns:
        RGBA image with proper alpha channel
    """
    # Convert to RGBA if needed
    if image.mode != 'RGBA':
        image = image.convert('RGBA')
    
    # Get pixel data
    pixels = image.load()
    width, height = image.size
    
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            
            # Calculate luminance (brightness)
            luminance = (r + g + b) / 3
            
            # White (high luminance) → opaque (keep)
            # Black (low luminance) → transparent (regenerate)
            if luminance > 128:
                # White - keep opaque
                pixels[x, y] = (255, 255, 255, 255)
            else:
                # Black - make transparent
                pixels[x, y] = (0, 0, 0, 0)
    
    return image


async def generate_svg_from_description(description: str) -> str:
    """
    Generate SVG mask code from a text description using LLM.
    
    Args:
        description: User's natural language description of the map layout
        
    Returns:
        Valid SVG string
        
    Raises:
        Exception: If generation or validation fails
    """
    logger.info(f"🎨 [SVGMask] Generating SVG from description: {description[:50]}...")
    
    client = get_generation_client()
    user_prompt = SVG_USER_PROMPT_TEMPLATE.format(description=description)
    try:
        result = await client.generate_text(
            TextRequest(
                system_prompt=SVG_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                profile=profile_for("svg_mask_generation"),
                temperature=0.7,
            )
        )
    except GenerationEngineError as error:
        logger.error("❌ [SVGMask] LLM generation failed: %s", error.failure.message)
        raise Exception(f"SVG generation failed: {error.failure.message}") from error

    if not result.text:
        raise Exception("Empty response from LLM")

    # Extract and validate SVG
    svg_string = _extract_svg(result.text)
    _validate_svg(svg_string)
    
    logger.info(f"✅ [SVGMask] Generated valid SVG: {len(svg_string)} chars")
    
    return svg_string


def render_svg_to_mask(
    svg_string: str,
    width: int = STANDARD_MASK_SIZE,
    height: int = STANDARD_MASK_SIZE,
) -> bytes:
    """
    Render SVG string to PNG mask bytes.
    
    Converts the SVG to a PNG and processes colors to create a proper
    alpha-based mask for the inpainting system.
    
    Args:
        svg_string: Valid SVG string
        width: Output width in pixels
        height: Output height in pixels
        
    Returns:
        PNG bytes in RGBA format (transparent = generate, opaque = keep)
    """
    logger.info(f"🖼️ [SVGMask] Rendering SVG to {width}x{height} PNG mask")
    
    # Validate first
    _validate_svg(svg_string)
    
    # Render SVG to PNG using cairosvg
    png_bytes = cairosvg.svg2png(
        bytestring=svg_string.encode('utf-8'),
        output_width=width,
        output_height=height,
    )
    
    # Load into PIL
    image = Image.open(io.BytesIO(png_bytes))
    
    # Convert black/white to alpha mask
    mask_image = _convert_colors_to_alpha(image)
    
    # Save back to bytes
    output_buffer = io.BytesIO()
    mask_image.save(output_buffer, format='PNG')
    output_buffer.seek(0)
    
    mask_bytes = output_buffer.getvalue()
    
    logger.info(f"✅ [SVGMask] Rendered mask: {len(mask_bytes)} bytes")
    
    return mask_bytes


def mask_bytes_to_base64(mask_bytes: bytes) -> str:
    """
    Convert PNG mask bytes to base64 data URI.
    
    Args:
        mask_bytes: PNG image bytes
        
    Returns:
        Base64 data URI string (data:image/png;base64,...)
    """
    base64_data = base64.b64encode(mask_bytes).decode('utf-8')
    return f"data:image/png;base64,{base64_data}"


async def generate_mask_from_description(
    description: str,
    width: int = STANDARD_MASK_SIZE,
    height: int = STANDARD_MASK_SIZE,
) -> tuple[str, str]:
    """
    Full pipeline: description → SVG → mask PNG (base64).
    
    Args:
        description: User's natural language description of the map layout
        width: Output mask width
        height: Output mask height
        
    Returns:
        Tuple of (svg_string, mask_base64)
    """
    logger.info(f"🎭 [SVGMask] Full pipeline: {description[:50]}...")
    
    # Step 1: Generate SVG
    svg_string = await generate_svg_from_description(description)
    
    # Step 2: Render to mask
    mask_bytes = render_svg_to_mask(svg_string, width, height)
    
    # Step 3: Convert to base64
    mask_base64 = mask_bytes_to_base64(mask_bytes)
    
    logger.info(f"✅ [SVGMask] Pipeline complete: SVG={len(svg_string)} chars, mask={len(mask_base64)} chars")
    
    return svg_string, mask_base64
