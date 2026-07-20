"""
Map Generator Pydantic Models

These models define the API contracts for the Map Generator feature.
They match the TypeScript interfaces in Canvas/src/map/types/map.types.ts
"""

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# CORE ENTITIES
# =============================================================================

class GridConfig(BaseModel):
    """Grid overlay configuration"""
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    
    type: Literal["square", "hex"]
    cell_size_px: int = Field(alias="cellSizePx", ge=10, le=200)
    offset_x: int = Field(alias="offsetX", ge=-1000, le=1000, default=0)
    offset_y: int = Field(alias="offsetY", ge=-1000, le=1000, default=0)
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$", default="#000000")
    opacity: float = Field(ge=0, le=1, default=0.5)
    visible: bool = False


class MapLabel(BaseModel):
    """A text annotation placed on the map"""
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    
    id: str
    text: str = Field(min_length=1, max_length=200)
    x: float  # Can be negative if label is placed at edge and view is panned
    y: float  # Can be negative if label is placed at edge and view is panned
    rotation: int = Field(default=0, ge=0, le=359)  # Any angle, Transformer may produce non-45 values
    font_family: Literal[
        "MedievalSharp",
        "Pirata One",
        "Uncial Antiqua",
        "Cinzel",
        "IM Fell English"
    ] = Field(alias="fontFamily", default="MedievalSharp")
    font_size: int = Field(alias="fontSize", ge=8, le=200, default=24)
    color: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    
    # Stroke/outline properties
    stroke_color: Optional[str] = Field(alias="strokeColor", default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    stroke_width: Optional[float] = Field(alias="strokeWidth", default=None, ge=0, le=5)
    
    # Shadow properties
    shadow_enabled: Optional[bool] = Field(alias="shadowEnabled", default=None)
    shadow_color: Optional[str] = Field(alias="shadowColor", default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    shadow_blur: Optional[float] = Field(alias="shadowBlur", default=None, ge=0, le=20)
    shadow_offset_x: Optional[float] = Field(alias="shadowOffsetX", default=None)
    shadow_offset_y: Optional[float] = Field(alias="shadowOffsetY", default=None)


class ScaleMetadata(BaseModel):
    """Optional scale information for the map"""
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    
    cell_size: float = Field(alias="cellSize", gt=0)
    unit: Literal["ft", "m", "squares"]


class ProjectGeneratedImage(BaseModel):
    """A generated image associated with a project"""
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    
    id: str
    url: str
    prompt: str = ""
    created_at: str = Field(alias="createdAt", default="")
    session_id: str = Field(alias="sessionId", default="")
    service: str = "map"


class MapProject(BaseModel):
    """The root entity representing a saved map project"""
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    
    id: str
    name: str = Field(min_length=1, max_length=100)
    base_image_url: str = Field(alias="baseImageUrl")
    grid_config: GridConfig = Field(alias="gridConfig")
    labels: list[MapLabel] = Field(default_factory=list, max_length=100)
    scale_metadata: Optional[ScaleMetadata] = Field(None, alias="scaleMetadata")
    generated_images: list[ProjectGeneratedImage] = Field(
        alias="generatedImages", 
        default_factory=list,
        max_length=50,
        description="Gallery of generated images for this project"
    )
    mask_image_url: Optional[str] = Field(None, alias="maskImageUrl", description="URL to persisted mask image in R2")
    user_id: str = Field(alias="userId")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


# =============================================================================
# API REQUEST MODELS
# =============================================================================

class CreateMapProjectRequest(BaseModel):
    """Request to create a new map project"""
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    
    name: str = Field(min_length=1, max_length=100)
    base_image_url: Optional[str] = Field(
        None,
        alias="baseImageUrl",
        description="Legacy: CDN URL that must already be in the caller's asset registry",
    )
    base_image_asset_id: Optional[str] = Field(
        None,
        alias="baseImageAssetId",
        description="Preferred: opaque asset id; server resolves canonical URL",
    )
    grid_config: Optional[GridConfig] = Field(None, alias="gridConfig")
    scale_metadata: Optional[ScaleMetadata] = Field(None, alias="scaleMetadata")


class UpdateMapProjectRequest(BaseModel):
    """Request to update an existing map project"""
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    base_image_url: Optional[str] = Field(None, alias="baseImageUrl")
    base_image_asset_id: Optional[str] = Field(None, alias="baseImageAssetId")
    grid_config: Optional[GridConfig] = Field(None, alias="gridConfig")
    labels: Optional[list[MapLabel]] = Field(None, max_length=100)
    scale_metadata: Optional[ScaleMetadata] = Field(None, alias="scaleMetadata")
    generated_images: Optional[list[ProjectGeneratedImage]] = Field(
        None, 
        alias="generatedImages",
        max_length=50
    )
    mask_image_url: Optional[str] = Field(None, alias="maskImageUrl", description="URL to persisted mask image in R2")


class GenerateMapRequest(BaseModel):
    """Request to generate a battle map using AI"""
    prompt: str = Field(min_length=10, max_length=8000)
    style_options: Optional[dict] = Field(None, description="Style toggles from frontend (MapStyleOptions)")
    width: Literal[512, 1024, 2048] = 1024
    height: Literal[512, 1024, 2048] = 1024


class GenerateMaskedMapRequest(BaseModel):
    """Request model for masked map generation (inpainting/editing)."""
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    
    prompt: str = Field(..., min_length=1, max_length=8000)
    mask_base64: str = Field(
        ...,
        alias="maskBase64",
        description="Base64-encoded PNG mask",
        max_length=14_000_000,  # ~10 MiB decoded + data-URI overhead
    )
    base_image_base64: str = Field(
        ...,
        alias="baseImageBase64",
        description="Base64-encoded PNG base image",
        max_length=14_000_000,
    )
    style_options: Optional[dict] = Field(None, alias="styleOptions", description="Optional style configuration")
    mode: Literal["inpaint", "edit"] = Field(
        default="inpaint",
        description="Generation mode: 'inpaint' uses mask to define map structure and fills entire image; 'edit' modifies only masked region and preserves non-masked areas"
    )


class GenerateSvgMaskRequest(BaseModel):
    """Request to generate an SVG mask from text description"""
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    
    description: str = Field(
        ..., 
        min_length=10, 
        max_length=2000,
        description="Natural language description of the map layout (e.g., 'A dungeon with three chambers connected by corridors')"
    )
    width: int = Field(default=1024, ge=256, le=2048, description="Output mask width in pixels")
    height: int = Field(default=1024, ge=256, le=2048, description="Output mask height in pixels")


class ExportMapRequest(BaseModel):
    """Request to export a map as a flattened image"""
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    
    project_id: Optional[str] = Field(None, alias="projectId")
    project: Optional[dict] = None  # Inline project data for guests
    format: Literal["png", "jpeg"] = "png"
    quality: int = Field(default=90, ge=1, le=100)


# =============================================================================
# API RESPONSE MODELS
# =============================================================================

class MapProjectSummary(BaseModel):
    """Summary of a map project (for listing)"""
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    
    id: str
    name: str
    base_image_url: str = Field(alias="baseImageUrl")
    updated_at: datetime = Field(alias="updatedAt")


class ListMapProjectsResponse(BaseModel):
    """Response from project list endpoint"""
    projects: list[MapProjectSummary]
    total: int


class MaskItem(BaseModel):
    """A saved mask from a project"""
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    
    mask_url: str = Field(alias="maskUrl")
    project_id: str = Field(alias="projectId")
    project_name: str = Field(alias="projectName")
    updated_at: datetime = Field(alias="updatedAt")


class ListMasksResponse(BaseModel):
    """Response from masks list endpoint"""
    masks: list[MaskItem]
    total: int


class GenerateMapResponse(BaseModel):
    """Response from map generation endpoint"""
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    
    image_url: str = Field(alias="imageUrl")
    asset_id: Optional[str] = Field(
        None,
        alias="assetId",
        description="Opaque server-issued asset id for ownership / project binding",
    )
    width: int
    height: int
    generation_time: Optional[float] = Field(None, alias="generationTime")
    mapspec: Optional[dict] = Field(None, description="Structured MapSpec for debugging")
    compiled_prompt: Optional[str] = Field(None, alias="compiledPrompt", description="Final compiled image prompt")


class ExportMapResponse(BaseModel):
    """Response from export endpoint"""
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    
    image_url: str = Field(alias="imageUrl")
    file_size: int = Field(alias="fileSize")
    width: int
    height: int


class GenerateSvgMaskResponse(BaseModel):
    """Response from SVG mask generation endpoint"""
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    
    svg: str = Field(description="The generated SVG code")
    mask_base64: str = Field(
        alias="maskBase64", 
        description="Base64-encoded PNG mask (data:image/png;base64,...)"
    )
    width: int
    height: int
    generation_time: float = Field(alias="generationTime", description="Time taken in seconds")


# =============================================================================
# DEFAULT VALUES
# =============================================================================

DEFAULT_GRID_CONFIG = GridConfig(
    type="square",
    cellSizePx=50,
    offsetX=0,
    offsetY=0,
    color="#000000",
    opacity=0.5,
    visible=False,
)

DEFAULT_SCALE_METADATA = ScaleMetadata(
    cellSize=5,
    unit="ft",
)


# =============================================================================
# MAPSPEC MODELS (Prompt Tuning System)
# =============================================================================

class MapSpecMeta(BaseModel):
    """Metadata for MapSpec"""
    version: str = "1.0"
    generator: str = "map-generator"
    timestamp: datetime
    source_prompt: str


class MapSpecIntent(BaseModel):
    """Intent and tone of the map"""
    summary: str
    location_type: str
    tone: Literal["gritty", "neutral", "whimsical"]
    fantasy_level: Literal["low", "medium", "high"]
    implied_activity: list[str] = Field(default_factory=list)


class MapSpecLayout(BaseModel):
    """Layout and structure of the map"""
    scale: Literal["encounter", "small_area", "district"]
    focal_point: str
    central_feature: str
    surrounding_elements: list[str] = Field(default_factory=list)
    pathways: Literal["radial", "organic", "linear", "gridless"]
    elevation_present: bool = False
    elevation_description: Optional[str] = None


class MapSpecEnvironment(BaseModel):
    """Environmental elements of the map"""
    terrain: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    vegetation: list[str] = Field(default_factory=list)
    props: list[str] = Field(default_factory=list)
    water_features: list[str] = Field(default_factory=list)


class MapSpecPalette(BaseModel):
    """Color palette settings"""
    saturation: Literal["muted", "balanced", "vibrant"] = "muted"
    contrast: Literal["low", "medium", "high"] = "high"
    temperature: Literal["cool", "neutral", "warm"] = "neutral"


class MapSpecStyle(BaseModel):
    """Artistic style settings"""
    perspective: Literal["top-down-90"] = "top-down-90"
    rendering: Literal["hand-painted", "digital", "sketch", "pixel-art"]
    genre: str = "low-fantasy"
    palette: MapSpecPalette
    texture_density: Literal["low", "medium"] = "medium"


class MapSpecGameplay(BaseModel):
    """Gameplay-related settings"""
    system: str = "dnd5e"
    readability_priority: bool = True
    movement_space: Literal["open", "mixed", "tight"]
    cover_density: Literal["light", "medium", "heavy"]


class MapSpecConstraints(BaseModel):
    """Hard constraints for generation"""
    forbid: list[str] = Field(default_factory=list)
    require: list[str] = Field(default_factory=list)


class MapSpec(BaseModel):
    """Structured representation of a battle map concept."""
    meta: MapSpecMeta
    intent: MapSpecIntent
    layout: MapSpecLayout
    environment: MapSpecEnvironment
    style: MapSpecStyle
    gameplay: MapSpecGameplay
    constraints: MapSpecConstraints


