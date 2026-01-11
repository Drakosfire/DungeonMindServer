"""
Map Generator Router

API endpoints for map project management, AI generation, and export.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional
from urllib.parse import unquote
import logging
import time
import httpx
import io
from PIL import Image

# Auth
from .auth_router import get_current_user
from auth_service import User

# GenerationEngine
from generationengine import (
    ImageService,
    ImageGenerationRequest as GEImageGenerationRequest,
    ImageModel,
    ImageSize,
)

from mapgenerator.models import (
    MapProject,
    CreateMapProjectRequest,
    UpdateMapProjectRequest,
    GenerateMapRequest,
    GenerateMapResponse,
    GenerateMaskedMapRequest,
    ExportMapRequest,
    ExportMapResponse,
    ListMapProjectsResponse,
    ListMasksResponse,
    MaskItem,
    MapProjectSummary,
    GridConfig,
    MapLabel,
    ScaleMetadata,
    ProjectGeneratedImage,
    DEFAULT_GRID_CONFIG,
)
from mapgenerator.compositing import composite_map_export
from mapgenerator.prompt_compiler import (
    generate_mapspec,
    compile_image_prompt,
    compile_inpainting_prompt,
    get_inpainting_negative_prompt,
)
from mapgenerator.prompt_config import get_defaults
from mapgenerator.inpainting import generate_inpainted_map, InpaintingValidationError
from cloudflareR2.cloudflareR2_utils import upload_temp_file_and_get_url

# Firestore
from firestore.firebase_config import db
from google.cloud.firestore_v1.base_query import FieldFilter
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

# Firestore collection name
MAP_PROJECTS_COLLECTION = "map_projects"

# Initialize ImageService (singleton pattern)
_image_service: Optional[ImageService] = None


def get_image_service() -> ImageService:
    """Get or create the ImageService singleton."""
    global _image_service
    if _image_service is None:
        _image_service = ImageService()
    return _image_service

router = APIRouter(prefix="/api/mapgenerator", tags=["mapgenerator"])


# =============================================================================
# HEALTH CHECK
# =============================================================================

@router.get("/health")
async def health_check():
    """Health check endpoint for map generator service"""
    logger.info("📍 [MapGenerator] Health check requested")
    return {
        "status": "ok",
        "service": "mapgenerator",
    }


# =============================================================================
# MAP GENERATION
# =============================================================================

@router.post("/generate", response_model=GenerateMapResponse)
async def generate_map(
    request: GenerateMapRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Generate a battle map using AI.
    
    Uses two-stage prompt compilation:
    1. User prompt + style options → MapSpec (structured JSON)
    2. MapSpec → Optimized image prompt
    3. Image prompt → GPT Image 1.5 via Fal.ai
    
    Requires authentication.
    """
    logger.info(f"🗺️ [MapGenerator] Generate request: prompt={request.prompt[:50]}..., user={current_user.sub}")
    
    start_time = time.time()
    
    try:
        # Stage 1: Generate MapSpec
        defaults = get_defaults()
        style_options = request.style_options or {}
        
        logger.info("📋 [MapGenerator] Generating MapSpec...")
        mapspec = await generate_mapspec(
            user_prompt=request.prompt,
            style_options=style_options,
            defaults=defaults,
        )
        
        # Stage 2: Compile image prompt
        logger.info("🔧 [MapGenerator] Compiling image prompt...")
        image_prompt = compile_image_prompt(mapspec)
        
        # Stage 3: Generate image with GPT Image 1.5
        # Map width/height to ImageSize enum
        size_map = {
            (512, 512): ImageSize.SQUARE,
            (1024, 1024): ImageSize.SQUARE,
            (2048, 2048): ImageSize.SQUARE,
            (768, 1024): ImageSize.PORTRAIT,
            (1024, 768): ImageSize.LANDSCAPE,
        }
        image_size = size_map.get((request.width, request.height), ImageSize.SQUARE)
        
        # Build negative prompt from MapSpec constraints
        negative_prompt = ", ".join(mapspec.constraints.forbid) if mapspec.constraints.forbid else None
        
        ge_request = GEImageGenerationRequest(
            prompt=image_prompt,
            negative_prompt=negative_prompt,
            model=ImageModel.GPT_IMAGE_15,  # OpenAI GPT Image 1.5 via Fal.ai
            num_images=1,
            size=image_size,
        )
        
        # Call GenerationEngine
        image_service = get_image_service()
        response = await image_service.generate(ge_request)
        
        if not response.success:
            error_msg = response.error.message if response.error else "Unknown error"
            logger.error(f"❌ [MapGenerator] Generation failed: {error_msg}")
            raise HTTPException(
                status_code=500,
                detail=f"Map generation failed: {error_msg}"
            )
        
        if not response.images or len(response.images) == 0:
            logger.error("❌ [MapGenerator] No images returned from generation")
            raise HTTPException(
                status_code=500,
                detail="Map generation returned no images"
            )
        
        generation_time = time.time() - start_time
        image = response.images[0]
        
        logger.info(f"✅ [MapGenerator] Generation complete: {generation_time:.2f}s, size={image.width}x{image.height}")
        
        return GenerateMapResponse(
            imageUrl=image.url,
            width=image.width,
            height=image.height,
            generationTime=generation_time,
            mapspec=mapspec.model_dump(),
            compiledPrompt=image_prompt,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [MapGenerator] Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Map generation failed: {str(e)}"
        )


# =============================================================================
# MASKED MAP GENERATION (INPAINTING)
# =============================================================================

@router.post("/generate-masked", response_model=GenerateMapResponse)
async def generate_masked_map(
    request: GenerateMaskedMapRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Generate content within masked regions of an existing map.
    
    Uses inpainting to fill only transparent regions of the mask
    while preserving opaque (non-masked) areas.
    
    Requires authentication.
    
    Implements TDD tests T178-T180.
    """
    logger.info(f"🎭 [MapGenerator] Masked generation request: prompt={request.prompt[:50]}..., user={current_user.sub}")
    
    start_time = time.time()
    
    # Validate required fields
    if not request.mask_base64:
        raise HTTPException(
            status_code=400,
            detail="mask_base64 is required"
        )
    
    if not request.base_image_base64:
        raise HTTPException(
            status_code=400,
            detail="base_image_base64 is required"
        )
    
    # Validate base64 format
    if not request.mask_base64.startswith('data:image/'):
        raise HTTPException(
            status_code=400,
            detail="Invalid mask format: must be base64-encoded image"
        )
    
    if not request.base_image_base64.startswith('data:image/'):
        raise HTTPException(
            status_code=400,
            detail="Invalid base image format: must be base64-encoded image"
        )
    
    try:
        # For inpainting, we use a SIMPLE targeted prompt instead of full MapSpec
        # The user describes what goes in the masked region, not the entire map
        logger.info("🎭 [MapGenerator] Compiling targeted inpainting prompt...")
        image_prompt = compile_inpainting_prompt(request.prompt)
        
        # Get standard negative prompt (grid, text, characters, etc.)
        negative_prompt = get_inpainting_negative_prompt()
        
        # Call inpainting service
        logger.info("🎨 [MapGenerator] Calling inpainting service...")
        image_url = await generate_inpainted_map(
            prompt=image_prompt,
            mask_base64=request.mask_base64,
            base_image_base64=request.base_image_base64,
            style_options=request.style_options,
            negative_prompt=negative_prompt,
        )
        
        generation_time = time.time() - start_time
        
        logger.info(f"✅ [MapGenerator] Masked generation complete: {generation_time:.2f}s, image_url={image_url}")
        
        return GenerateMapResponse(
            imageUrl=image_url,
            width=1024,  # TODO: Get actual dimensions from inpainting result
            height=1024,
            generationTime=generation_time,
            mapspec=None,  # No MapSpec for inpainting
            compiledPrompt=image_prompt,
        )
        
    except InpaintingValidationError as e:
        logger.warning(f"⚠️ [MapGenerator] Inpainting validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [MapGenerator] Masked generation error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Masked map generation failed: {str(e)}"
        )


# =============================================================================
# PROJECT CRUD
# =============================================================================

@router.get("/projects", response_model=ListMapProjectsResponse)
async def list_projects(
    current_user: User = Depends(get_current_user),
    limit: int = 20,
    offset: int = 0,
):
    """
    List user's map projects.
    
    Requires authentication.
    """
    logger.info(f"📋 [MapGenerator] List projects: user={current_user.sub}, limit={limit}, offset={offset}")
    
    try:
        user_id = current_user.sub
        
        # Query Firestore for user's projects
        projects_ref = db.collection(MAP_PROJECTS_COLLECTION)
        query = projects_ref.where(filter=FieldFilter("userId", "==", user_id))
        
        # Apply limit and offset
        query = query.limit(limit).offset(offset)
        
        projects = []
        for doc in query.stream():
            project_data = doc.to_dict()
            # Get updated_at as datetime (Firestore stores as datetime)
            updated_at_raw = project_data.get("updated_at")
            if isinstance(updated_at_raw, datetime):
                updated_at = updated_at_raw
            elif isinstance(updated_at_raw, str):
                updated_at = datetime.fromisoformat(updated_at_raw.replace("Z", "+00:00"))
            else:
                updated_at = datetime.now()
            
            # Convert to summary format
            projects.append(MapProjectSummary(
                id=doc.id,
                name=project_data.get("name", "Untitled"),
                baseImageUrl=project_data.get("base_image_url", ""),
                updatedAt=updated_at
            ))
        
        # Get total count (separate query)
        total_query = projects_ref.where(filter=FieldFilter("userId", "==", user_id))
        total = len(list(total_query.stream()))
        
        logger.info(f"✅ [MapGenerator] Found {len(projects)} projects (total: {total})")
        
        return ListMapProjectsResponse(projects=projects, total=total)
        
    except Exception as e:
        logger.error(f"❌ [MapGenerator] Error listing projects: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list projects: {str(e)}")


@router.get("/masks", response_model=ListMasksResponse)
async def list_masks(
    current_user: User = Depends(get_current_user),
):
    """
    List all saved masks from user's map projects.
    
    Returns masks from all projects that have a mask_image_url saved.
    Requires authentication.
    """
    logger.info(f"🎭 [MapGenerator] List masks: user={current_user.sub}")
    
    try:
        user_id = current_user.sub
        
        # Query Firestore for user's projects
        projects_ref = db.collection(MAP_PROJECTS_COLLECTION)
        query = projects_ref.where(filter=FieldFilter("userId", "==", user_id))
        
        masks = []
        for doc in query.stream():
            project_data = doc.to_dict()
            
            # Only include projects with a saved mask
            mask_url = project_data.get("mask_image_url")
            if not mask_url:
                continue
            
            # Get updated_at as datetime
            updated_at_raw = project_data.get("updated_at")
            if isinstance(updated_at_raw, datetime):
                updated_at = updated_at_raw
            elif isinstance(updated_at_raw, str):
                updated_at = datetime.fromisoformat(updated_at_raw.replace("Z", "+00:00"))
            else:
                updated_at = datetime.now()
            
            masks.append(MaskItem(
                mask_url=mask_url,
                project_id=doc.id,
                project_name=project_data.get("name", "Untitled"),
                updated_at=updated_at
            ))
        
        logger.info(f"🎭 [MapGenerator] Found {len(masks)} masks from projects")
        
        return ListMasksResponse(masks=masks, total=len(masks))
        
    except Exception as e:
        logger.error(f"❌ [MapGenerator] Error listing masks: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list masks: {str(e)}")


@router.post("/projects", response_model=MapProject, status_code=201)
async def create_project(
    request: CreateMapProjectRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Create a new map project.
    
    Requires authentication.
    """
    logger.info(f"➕ [MapGenerator] Create project: name={request.name}, user={current_user.sub}")
    
    try:
        user_id = current_user.sub
        now = datetime.now()
        project_id = str(uuid.uuid4())
        
        # Build project with defaults
        grid_config = request.grid_config or DEFAULT_GRID_CONFIG
        
        project = MapProject(
            id=project_id,
            name=request.name,
            base_image_url=request.base_image_url,
            grid_config=grid_config,
            labels=[],
            scale_metadata=request.scale_metadata,
            user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        
        # Save to Firestore (use snake_case for storage, consistent with Firestore conventions)
        doc_ref = db.collection(MAP_PROJECTS_COLLECTION).document(project_id)
        project_dict = {
            "id": project_id,
            "name": request.name,
            "base_image_url": request.base_image_url or "",
            "grid_config": grid_config.model_dump(by_alias=False),  # Store as snake_case
            "labels": [],
            "generated_images": [],  # Initialize empty gallery
            "scale_metadata": request.scale_metadata.model_dump(by_alias=False) if request.scale_metadata else None,
            "userId": user_id,  # Keep userId as-is for Firestore querying
            "created_at": now,
            "updated_at": now,
        }
        doc_ref.set(project_dict)
        
        logger.info(f"✅ [MapGenerator] Created project: {project_id}")
        
        return project
        
    except Exception as e:
        logger.error(f"❌ [MapGenerator] Error creating project: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create project: {str(e)}")


@router.get("/projects/{project_id}", response_model=MapProject)
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific project by ID.
    
    Requires authentication and ownership.
    """
    logger.info(f"📖 [MapGenerator] Get project: id={project_id}, user={current_user.sub}")
    
    try:
        user_id = current_user.sub
        
        doc_ref = db.collection(MAP_PROJECTS_COLLECTION).document(project_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        
        project_data = doc.to_dict()
        
        # Verify ownership
        if project_data.get("userId") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Convert Firestore data to MapProject model (snake_case storage)
        created_at_raw = project_data.get("created_at")
        updated_at_raw = project_data.get("updated_at")
        
        # Handle datetime conversion
        if isinstance(created_at_raw, datetime):
            created_at = created_at_raw
        elif isinstance(created_at_raw, str):
            created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
        else:
            created_at = datetime.now()
            
        if isinstance(updated_at_raw, datetime):
            updated_at = updated_at_raw
        elif isinstance(updated_at_raw, str):
            updated_at = datetime.fromisoformat(updated_at_raw.replace("Z", "+00:00"))
        else:
            updated_at = datetime.now()
        
        # Get grid_config with fallback to default
        grid_config_data = project_data.get("grid_config", {})
        if not grid_config_data:
            grid_config = DEFAULT_GRID_CONFIG
        else:
            grid_config = GridConfig(**grid_config_data)
        
        # Get scale_metadata if present
        scale_metadata_data = project_data.get("scale_metadata")
        scale_metadata = ScaleMetadata(**scale_metadata_data) if scale_metadata_data else None
        
        # Get generated_images if present
        generated_images_data = project_data.get("generated_images", [])
        generated_images = [ProjectGeneratedImage(**img) for img in generated_images_data]
        
        project = MapProject(
            id=doc.id,
            name=project_data.get("name", "Untitled"),
            base_image_url=project_data.get("base_image_url", ""),
            grid_config=grid_config,
            labels=[MapLabel(**label) for label in project_data.get("labels", [])],
            scale_metadata=scale_metadata,
            generated_images=generated_images,
            mask_image_url=project_data.get("mask_image_url"),
            user_id=project_data.get("userId"),
            created_at=created_at,
            updated_at=updated_at,
        )
        
        logger.info(f"✅ [MapGenerator] Retrieved project: {project_id} with {len(generated_images)} images, mask: {bool(project.mask_image_url)}")
        
        return project
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [MapGenerator] Error getting project: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get project: {str(e)}")


@router.patch("/projects/{project_id}", response_model=MapProject)
async def update_project(
    project_id: str,
    request: UpdateMapProjectRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Update an existing project.
    
    Requires authentication and ownership.
    """
    logger.info(f"✏️ [MapGenerator] Update project: id={project_id}, user={current_user.sub}")
    
    try:
        user_id = current_user.sub
        
        doc_ref = db.collection(MAP_PROJECTS_COLLECTION).document(project_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        
        project_data = doc.to_dict()
        
        # Verify ownership
        if project_data.get("userId") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Build update dict (only include provided fields, use snake_case for Firestore)
        updates = {}
        if request.name is not None:
            updates["name"] = request.name
        if request.base_image_url is not None:
            updates["base_image_url"] = request.base_image_url
        if request.grid_config is not None:
            updates["grid_config"] = request.grid_config.model_dump(by_alias=False)
        if request.labels is not None:
            updates["labels"] = [label.model_dump(by_alias=False) for label in request.labels]
        if request.scale_metadata is not None:
            updates["scale_metadata"] = request.scale_metadata.model_dump(by_alias=False)
        if request.generated_images is not None:
            updates["generated_images"] = [img.model_dump(by_alias=False) for img in request.generated_images]
        if request.mask_image_url is not None:
            updates["mask_image_url"] = request.mask_image_url
        
        # Always update timestamp
        updates["updated_at"] = datetime.now()
        
        # Update Firestore
        doc_ref.update(updates)
        
        # Fetch updated project
        updated_doc = doc_ref.get()
        updated_data = updated_doc.to_dict()
        
        # Convert to MapProject model (snake_case storage)
        created_at_raw = updated_data.get("created_at")
        updated_at_raw = updated_data.get("updated_at")
        
        if isinstance(created_at_raw, datetime):
            created_at = created_at_raw
        elif isinstance(created_at_raw, str):
            created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
        else:
            created_at = datetime.now()
            
        if isinstance(updated_at_raw, datetime):
            updated_at = updated_at_raw
        elif isinstance(updated_at_raw, str):
            updated_at = datetime.fromisoformat(updated_at_raw.replace("Z", "+00:00"))
        else:
            updated_at = datetime.now()
        
        # Get grid_config with fallback
        grid_config_data = updated_data.get("grid_config", {})
        grid_config = GridConfig(**grid_config_data) if grid_config_data else DEFAULT_GRID_CONFIG
        
        # Get scale_metadata if present
        scale_metadata_data = updated_data.get("scale_metadata")
        scale_metadata = ScaleMetadata(**scale_metadata_data) if scale_metadata_data else None
        
        # Get generated_images if present
        generated_images_data = updated_data.get("generated_images", [])
        generated_images = [ProjectGeneratedImage(**img) for img in generated_images_data]
        
        project = MapProject(
            id=updated_doc.id,
            name=updated_data.get("name", "Untitled"),
            base_image_url=updated_data.get("base_image_url", ""),
            grid_config=grid_config,
            labels=[MapLabel(**label) for label in updated_data.get("labels", [])],
            scale_metadata=scale_metadata,
            generated_images=generated_images,
            mask_image_url=updated_data.get("mask_image_url"),
            user_id=updated_data.get("userId"),
            created_at=created_at,
            updated_at=updated_at,
        )
        
        logger.info(f"✅ [MapGenerator] Updated project: {project_id} with {len(generated_images)} images, mask: {bool(project.mask_image_url)}")
        
        return project
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [MapGenerator] Error updating project: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update project: {str(e)}")


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Delete a project.
    
    Requires authentication and ownership.
    """
    logger.info(f"🗑️ [MapGenerator] Delete project: id={project_id}, user={current_user.sub}")
    
    try:
        user_id = current_user.sub
        
        doc_ref = db.collection(MAP_PROJECTS_COLLECTION).document(project_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        
        project_data = doc.to_dict()
        
        # Verify ownership
        if project_data.get("userId") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Delete from Firestore
        doc_ref.delete()
        
        logger.info(f"✅ [MapGenerator] Deleted project: {project_id}")
        
        return None  # 204 No Content
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [MapGenerator] Error deleting project: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {str(e)}")


# =============================================================================
# EXPORT
# =============================================================================

@router.post("/export", response_model=ExportMapResponse)
async def export_map(request: ExportMapRequest):
    """
    Export a map as a flattened image.
    
    Composites base image, grid overlay, and labels into a single PNG/JPEG.
    
    - Authenticated users can export by projectId
    - Guests can export with inline project data
    """
    logger.info(f"📤 [MapGenerator] Export request: format={request.format}")
    
    try:
        # Get project data (either from projectId or inline)
        project_data = None
        if request.project_id:
            # Load project from Firestore by projectId
            # Note: Export endpoint doesn't require auth (guests can export)
            # But if projectId is provided, we need to load it
            doc_ref = db.collection(MAP_PROJECTS_COLLECTION).document(request.project_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                raise HTTPException(
                    status_code=404,
                    detail=f"Project {request.project_id} not found"
                )
            
            project_data = doc.to_dict()
            logger.info(f"📥 [MapGenerator] Loaded project from Firestore: {request.project_id}")
        
        # Use inline project data if provided, otherwise use loaded project
        if request.project:
            project_data = request.project
        
        if not project_data:
            raise HTTPException(
                status_code=400,
                detail="Either projectId or inline project data must be provided"
            )
        
        # Extract project data (handle both Firestore format and inline format)
        base_image_url = project_data.get("baseImageUrl") or project_data.get("base_image_url")
        if not base_image_url:
            raise HTTPException(
                status_code=400,
                detail="baseImageUrl is required in project data"
            )
        
        # Parse grid config (handle both formats)
        grid_config_dict = project_data.get("gridConfig") or project_data.get("grid_config", {})
        grid_config = GridConfig(**grid_config_dict)
        
        # Parse labels (handle both formats)
        labels_dict = project_data.get("labels", [])
        labels = [MapLabel(**label_dict) for label_dict in labels_dict]
        
        # Download base image
        logger.info(f"📥 [MapGenerator] Downloading base image from {base_image_url}")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(base_image_url)
            response.raise_for_status()
            base_image_bytes = response.content
        
        # Get image dimensions
        base_image = Image.open(io.BytesIO(base_image_bytes))
        width, height = base_image.size
        
        # Composite map export
        logger.info(f"🎨 [MapGenerator] Compositing map: {width}x{height}, grid={grid_config.visible}, labels={len(labels)}")
        composite_image = composite_map_export(
            base_image_bytes,
            grid_config,
            labels,
            width,
            height
        )
        
        # Save to bytes
        # Validate and normalize format
        requested_format = request.format.lower()
        if requested_format not in ['png', 'jpeg']:
            logger.warning(f"⚠️ [MapGenerator] Invalid format '{requested_format}', defaulting to PNG")
            requested_format = 'png'
        
        output_format = requested_format.upper()  # PNG or JPEG
        logger.info(f"💾 [MapGenerator] Saving image with format: {output_format} (requested: {request.format})")
        output_bytes = io.BytesIO()
        save_kwargs = {}
        
        if output_format == 'JPEG':
            save_kwargs['quality'] = request.quality
            # Convert to RGB if needed for JPEG (JPEG doesn't support alpha channel)
            if composite_image.mode != 'RGB':
                logger.info(f"🔄 [MapGenerator] Converting image from {composite_image.mode} to RGB for JPEG")
                composite_image = composite_image.convert('RGB')
        elif output_format == 'PNG':
            # PNG can handle RGBA, so no conversion needed
            pass
        else:
            logger.error(f"❌ [MapGenerator] Unsupported format: {output_format}, defaulting to PNG")
            output_format = 'PNG'
        
        # Ensure format is explicitly set (PIL requires uppercase format names)
        composite_image.save(output_bytes, format=output_format, **save_kwargs)
        output_bytes.seek(0)
        file_size = len(output_bytes.getvalue())
        logger.info(f"✅ [MapGenerator] Image saved: format={output_format}, size={file_size} bytes")
        output_bytes.seek(0)
        file_size = len(output_bytes.getvalue())
        
        # Upload to Cloudflare R2 (temporary file)
        logger.info(f"☁️ [MapGenerator] Uploading exported image to R2 ({file_size} bytes)")
        # Save to temp file first
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{request.format}') as tmp_file:
            tmp_file.write(output_bytes.getvalue())
            tmp_path = tmp_file.name
        
        try:
            # Upload to R2 (1 hour expiration for exports)
            image_url = await upload_temp_file_and_get_url(
                tmp_path,
                expiration_days=1,  # 1 day expiration for exports
                bucket_name='temp-images'
            )
        finally:
            # Clean up temp file
            os.unlink(tmp_path)
        
        logger.info(f"✅ [MapGenerator] Export complete: {image_url}")
        
        return ExportMapResponse(
            imageUrl=image_url,
            fileSize=file_size,
            width=width,
            height=height
        )
        
    except HTTPException:
        # Re-raise HTTPExceptions (like 400 Bad Request) as-is
        raise
    except httpx.HTTPError as e:
        logger.error(f"❌ [MapGenerator] HTTP error downloading image: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to download base image: {str(e)}"
        )
    except Exception as e:
        logger.error(f"❌ [MapGenerator] Export failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Map export failed: {str(e)}"
        )


# =============================================================================
# DOWNLOAD PROXY (for CORS bypass)
# =============================================================================

@router.get("/download")
async def download_proxy(url: str, filename: Optional[str] = None):
    """
    Proxy endpoint for downloading images from R2.
    
    Bypasses CORS by fetching server-side and streaming to client.
    Used for exporting maps where the R2 presigned URL can't be fetched
    directly from the browser.
    
    Args:
        url: The R2 presigned URL to fetch
        filename: Optional filename for Content-Disposition header
    """
    logger.info("📥 [MapGenerator] Download proxy request")
    
    try:
        # Decode URL if it was URL-encoded
        decoded_url = unquote(url)
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(decoded_url)
            response.raise_for_status()
            
            # Determine content type from response or infer from URL
            content_type = response.headers.get('content-type', 'image/png')
            
            # Set up response headers
            headers = {
                'Content-Type': content_type,
                'Content-Length': str(len(response.content)),
            }
            
            # Add Content-Disposition if filename provided
            if filename:
                headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            logger.info(f"✅ [MapGenerator] Download proxy complete: {len(response.content)} bytes")
            
            return StreamingResponse(
                iter([response.content]),
                media_type=content_type,
                headers=headers
            )
            
    except httpx.HTTPError as e:
        logger.error(f"❌ [MapGenerator] Download proxy HTTP error: {str(e)}")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to download from upstream: {str(e)}"
        )
    except Exception as e:
        logger.error(f"❌ [MapGenerator] Download proxy error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Map export failed: {str(e)}"
        )
