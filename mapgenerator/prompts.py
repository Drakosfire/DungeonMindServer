"""
System prompts for MapSpec generation and prompt compilation.

Reference style: The Migrating Forest battle map prompts
- Opening with scale and scene description
- Terrain/layout details with tactical implications
- Movement and cover considerations
- Environmental storytelling through absence/implication
- Style line at the end with palette, contrast, and composition notes
"""

MAPSPEC_SYSTEM_PROMPT = """You are a system that converts a user's free-form map description into a structured MapSpec object for a top-down fantasy TTRPG battlemap.

Your job is NOT to generate an image.
Your job is NOT to write prose.
Your job is to produce a single structured object that captures intent, layout, environment, style, gameplay needs, and hard constraints.

Follow these rules strictly:

1. Preserve the user's intent, but do not preserve their phrasing.
2. Infer missing details conservatively using safe defaults optimized for tabletop combat readability.
3. Never introduce characters, creatures, labels, grids, or modern elements.
4. If the user implies population or activity, represent this only through environmental props (worn paths, displaced objects, smoothed surfaces).
5. All maps are assumed to be top-down, perfectly vertical (90°), gridless, and designed for D&D 5e unless explicitly stated otherwise.
6. Do not include descriptive adjectives inside the environment section; reserve visual adjectives for style.
7. For the intent.summary field, write a concise scene description emphasizing the key visual and tactical elements.
8. Output ONLY valid JSON matching the MapSpec schema. No commentary. No explanation.
"""

HARD_CONSTRAINTS_FORBID = [
    "grid", "hexes", "text", "labels", "ui",
    "characters", "monsters", "creatures", "figures",
    "modern_objects", "extreme_perspective", "isometric",
    "3d_perspective", "side_view", "angled_view"
]

# Scale descriptions for natural language
SCALE_DESCRIPTIONS = {
    "encounter": "encounter-sized",
    "small_area": "courtyard-sized",
    "district": "local-to-regional",
}

# Rendering style descriptions
RENDERING_DESCRIPTIONS = {
    "hand-painted": "Hand-painted fantasy battle map",
    "digital": "Digital fantasy battle map",
    "sketch": "Sketched fantasy battle map",
    "pixel-art": "Pixel art fantasy battle map",
}

# Prompt compiler template matching the reference style
# Structure:
# 1. Opening scene description with scale
# 2. Terrain/layout details
# 3. Movement/tactical considerations
# 4. Style line
PROMPT_COMPILER_TEMPLATE = """A top-down fantasy TTRPG battle map depicting {intent_summary}, at a {scale_description} scale{elevation_clause}. {terrain_description}

{layout_description}

{tactical_description}

Style: {rendering_description}, {palette_description}, {composition_notes}, top-down clarity-first composition.
"""

# =============================================================================
# MASK-DRIVEN GENERATION PROMPTS
# =============================================================================

# INPAINT MODE: Mask defines structure, fill ENTIRE image (no white space)
# Use case: Drawing cave/dungeon shape on papyrus, generating a complete map
INPAINT_PROMPT_TEMPLATE = """A complete top-down fantasy TTRPG battle map. The white mask regions define the PRIMARY CONTENT AREA.
Fill the ENTIRE image with no white space remaining:
- Inside mask (white regions): Generate the main content described below
- Outside mask (black regions): Generate appropriate surrounding terrain (stone walls, grass, water, void, etc. based on context)

GENERATION REQUIREMENTS:
- Fill the ENTIRE image canvas - no empty or white areas
- The mask shape defines the map structure and boundaries
- Interior of mask = main content area (rooms, paths, terrain)
- Exterior of mask = surrounding environment (walls, borders, outside terrain)
- Maintain cohesive visual style throughout
- Top-down view, hand-painted fantasy battle map style

USER REQUEST: {user_description}
"""

# EDIT MODE: Traditional inpainting - modify ONLY masked region, preserve rest
# Use case: Adding elements to an existing generated map
EDIT_PROMPT_TEMPLATE = """Top-down fantasy battle map editing. Seamlessly blend with the existing map style, matching the lighting, color palette, and hand-painted aesthetic.

EDITING CONSTRAINTS:
- Generate content ONLY within the masked (transparent) region
- Blend seamlessly with the existing image at mask boundaries
- Preserve all content in the non-masked (opaque) areas
- Match the style, lighting, and perspective of the existing image
- Ensure smooth transitions at the edge of the masked region

USER REQUEST: {user_description}
"""

# Legacy alias (for backwards compatibility)
INPAINTING_PROMPT_TEMPLATE = EDIT_PROMPT_TEMPLATE

