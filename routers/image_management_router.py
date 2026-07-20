"""
Image Management Router

Handles image operations:
- Upload (single/bulk)
- Delete
- Capabilities (available models/styles)
- Generate (AI image generation)

"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Query
from pydantic import BaseModel, Field

# Image management service (TODO: This is a fragile dependency, need to fix this)
from cardgenerator.services.image_management_service import image_management_service
from cardgenerator.utils.error_handler import ImageProcessingError

# Auth
from .auth_router import get_current_user
from auth_service import User
from security_limits.paid_budget import paid_budget_store
from security_limits.input_limits import enforce_max_chars, clamp_num_images, MAX_PROMPT_CHARS
from services.image_asset_registry import register_image_asset, get_asset_for_owner, delete_asset_record
from cloudflare.handle_images import delete_cloudflare_image_by_id

# GenerationEngine
from generationengine import (
    ImageService,
    ImageGenerationRequest as GEImageGenerationRequest,
    ImageSize,
)

# Shared configuration
from shared.image_models import MODEL_MAP, IMAGE_CAPABILITIES

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/images", tags=["Image Management"])

# Initialize ImageService (singleton pattern)
_image_service: Optional[ImageService] = None


def get_image_service() -> ImageService:
    """Get or create the ImageService singleton."""
    global _image_service
    if _image_service is None:
        _image_service = ImageService()
    return _image_service


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class BulkUploadRequest(BaseModel):
    image_urls: List[str]


class ImageGenerateRequest(BaseModel):
    """Request model for image generation."""
    prompt: str = Field(..., description="Text prompt for image generation")
    model: str = Field("flux-2-pro", description="Model: flux-2-pro, nano-banana-pro, gpt-image-1.5")
    num_images: int = Field(1, ge=1, le=8, description="Number of images to generate")
    # Future: size, aspect_ratio, style could be added here


class GeneratedImage(BaseModel):
    """Single generated image (snake_case to match frontend contract)."""
    id: str
    url: str
    prompt: str
    created_at: str  # snake_case for API contract


class ImageGenerationInfo(BaseModel):
    """Generation metadata."""
    prompt: str
    model: str
    num_images: int


class ImageGenerationData(BaseModel):
    """Response data containing images and metadata."""
    images: List[GeneratedImage]
    generation_info: ImageGenerationInfo


class ImageGenerateResponse(BaseModel):
    """
    Response model for image generation.
    
    Contract matches: ApiImageGenerationResponse in frontend types.ts
    """
    success: bool
    data: Optional[ImageGenerationData] = None
    error: Optional[str] = None

@router.post('/upload')
async def upload_single_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a single image file to cloud storage.
    Registers a server-controlled opaque asset_id for later deletion.
    """
    try:
        logger.info("Image upload request user_id=%s", current_user.user_id)
        
        result = await image_management_service.upload_single_image(file)
        asset = register_image_asset(
            owner_id=current_user.user_id,
            provider="cloudflare_images",
            object_key=result.provider_image_id or "",
            canonical_url=result.url,
            account_or_bucket="",
            service="images",
        )
        
        return {
            "url": result.url,
            "asset_id": asset.asset_id,
            "success": result.success,
            "message": result.message
        }
        
    except HTTPException:
        raise
    except ImageProcessingError as e:
        # Surface validation failures (400/413) that were wrapped by the service
        detail = str(e)
        if "not a recognized image" in detail.lower() or "exceeds maximum" in detail.lower():
            code = 413 if "exceeds" in detail.lower() else 400
            raise HTTPException(status_code=code, detail=detail)
        logger.error(f"Image upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in image upload: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post('/upload-bulk')
async def upload_multiple_images(
    request: BulkUploadRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Upload multiple images to permanent storage.
    Requires an authenticated session.
    """
    try:
        # Validate input
        if not request.image_urls:
            raise HTTPException(status_code=422, detail="No image URLs provided")
        if len(request.image_urls) > 20:
            raise HTTPException(status_code=422, detail="Maximum 20 images per batch")
        
        logger.info(
            f"Bulk upload request: {len(request.image_urls)} images "
            f"user={getattr(current_user, 'email', None)}"
        )
        
        # Delegate to service layer
        result = await image_management_service.upload_generated_images(request.image_urls)
        
        return {
            "uploaded_images": result.uploaded_images,
            "total_count": result.total_count,
            "success_count": result.success_count,
            "failure_count": result.failure_count,
            "success": result.success_count > 0
        }
        
    except ImageProcessingError as e:
        logger.error(f"Bulk upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in bulk upload: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# =============================================================================
# IMAGE GENERATION CAPABILITIES
# =============================================================================

@router.get('/capabilities')
async def get_image_capabilities():
    """
    Get available image generation models and styles.
    
    Returns configuration for the Generation Drawer Engine UI.
    No authentication required - this is configuration data.
    
    Future: Could be user-tier gated (e.g., pro models for paid users).
    """
    return IMAGE_CAPABILITIES


# =============================================================================
# IMAGE GENERATION
# =============================================================================

@router.post('/generate', response_model=ImageGenerateResponse)
async def generate_image(
    request: ImageGenerateRequest,
    current_user: User = Depends(get_current_user)
) -> ImageGenerateResponse:
    """
    Generate images using AI models.
    
    Supports:
    - flux-2-pro: High quality, balanced speed (~10s)
    - nano-banana-pro: Ultra-fast, aspect ratio support (~3s)
    - gpt-image-1.5: OpenAI GPT-4 Vision powered (~5s)
    
    Requires authentication - AI generation costs money and images need CDN storage.
    """
    try:
        enforce_max_chars(request.prompt, field="prompt", limit=MAX_PROMPT_CHARS)
        num_images = clamp_num_images(request.num_images)
        paid_budget_store.consume(current_user.user_id, units=num_images)
        logger.info(
            "ImageGenerate user_id=%s model=%s prompt_chars=%s num_images=%s",
            current_user.user_id,
            request.model,
            len(request.prompt or ""),
            num_images,
        )
        
        # Use shared model map
        ge_model = MODEL_MAP.get(request.model)
        if not ge_model:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown model: {request.model}. Available: {list(MODEL_MAP.keys())}"
            )
        
        # Build GenerationEngine request
        ge_request = GEImageGenerationRequest(
            prompt=request.prompt,
            model=ge_model,
            num_images=num_images,
            size=ImageSize.SQUARE,  # Default 1024x1024
        )
        
        # Call GenerationEngine
        image_service = get_image_service()
        response = await image_service.generate(ge_request)
        
        if not response.success:
            error_msg = response.error.message if response.error else "Unknown error"
            logger.error(f"❌ [ImageGenerate] Failed: {error_msg}")
            return ImageGenerateResponse(
                success=False,
                error=error_msg
            )
        
        # Transform to response format (matching frontend ApiImageGenerationResponse)
        generated_images: List[GeneratedImage] = []
        if response.images:
            for idx, img_result in enumerate(response.images):
                generated_images.append(GeneratedImage(
                    id=f"img_{datetime.now().timestamp()}_{idx}",
                    url=img_result.url,
                    prompt=request.prompt,
                    created_at=datetime.now().isoformat()
                ))
        
        logger.info(f"✅ [ImageGenerate] Generated {len(generated_images)} images")
        
        # Log metrics if available
        if response.metrics:
            logger.info(
                f"📊 [ImageGenerate] duration={response.metrics.duration_ms}ms, "
                f"model={response.metrics.model_used}, retries={response.metrics.retry_count}"
            )
        
        model_used = response.metrics.model_used if response.metrics else request.model
        
        return ImageGenerateResponse(
            success=True,
            data=ImageGenerationData(
                images=generated_images,
                generation_info=ImageGenerationInfo(
                    prompt=request.prompt,
                    model=model_used,
                    num_images=len(generated_images)
                )
            )
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [ImageGenerate] Unexpected error: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)}")


# =============================================================================
# IMAGE LIBRARY
# =============================================================================

# Service-to-collection mapping
SERVICE_COLLECTION_MAP = {
    "statblock": "statblock_projects",
    "card": "card_projects",
    "pcg": "pcg_projects",
    "map": "map_projects",
}


def _owner_field_for_service(service: str) -> str:
    # map/card/pcg store owner as userId; statblock uses createdBy
    if service in ("map", "card", "pcg"):
        return "userId"
    return "createdBy"


def user_owns_image_url(user_id: str, image_url: str, service: str) -> bool:
    """
    True if image_url appears in one of the caller's projects for this service.
    Must be checked before any cloud delete.
    """
    from firebase_admin import firestore

    db = firestore.client()
    collection_name = SERVICE_COLLECTION_MAP.get(service, "statblock_projects")
    user_field = _owner_field_for_service(service)
    query = db.collection(collection_name).where(user_field, "==", user_id)

    for doc in query.stream():
        project_data = doc.to_dict() or {}
        if service == "map":
            if project_data.get("base_image_url") == image_url:
                return True
            if project_data.get("baseImageUrl") == image_url:
                return True
        else:
            images = (
                project_data.get("state", {})
                .get("generatedContent", {})
                .get("images", [])
            )
            for img in images:
                if img.get("url") == image_url:
                    return True
    return False


class LibraryImage(BaseModel):
    """Image in user's library."""
    id: str
    url: str
    prompt: str = ""
    createdAt: str  # camelCase for frontend contract
    sessionId: str = ""
    service: str


class LibraryResponse(BaseModel):
    """Paginated library response."""
    images: List[LibraryImage]
    total: int
    totalPages: int
    page: int
    limit: int


@router.get('/library', response_model=LibraryResponse)
async def get_image_library(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    service: str = Query("statblock", description="Service: statblock, card, pcg"),
    sessionId: Optional[str] = Query(None, description="Optional session filter"),
    current_user: User = Depends(get_current_user)
) -> LibraryResponse:
    """
    Get user's image library with pagination.
    
    Returns all images from user's projects for the specified service.
    Used by the GenerationDrawerEngine Library tab.
    """
    from firebase_admin import firestore
    db = firestore.client()
    
    try:
        user_id = current_user.user_id
        collection_name = SERVICE_COLLECTION_MAP.get(service, "statblock_projects")
        
        logger.info(
            f"📚 [ImageLibrary] user={current_user.email}, service={service}, "
            f"collection={collection_name}, page={page}, limit={limit}"
        )
        
        # Query user's projects
        # Note: Different services use different field names for user ownership
        # - map/card/pcg: uses "userId"
        # - statblock: uses "createdBy"
        projects_ref = db.collection(collection_name)
        user_field = _owner_field_for_service(service)
        query = projects_ref.where(user_field, "==", user_id)
        
        # Aggregate all images from all projects
        all_images: List[LibraryImage] = []
        seen_urls: set = set()
        
        for doc in query.stream():
            project_data = doc.to_dict()
            project_id = project_data.get("id", doc.id)
            
            # Handle map projects differently - they store base_image_url directly
            if service == "map":
                img_url = project_data.get("base_image_url")
                if img_url and img_url not in seen_urls:
                    seen_urls.add(img_url)
                    # Get created_at from project, handle both datetime and string
                    created_at = project_data.get("created_at", "")
                    if hasattr(created_at, 'isoformat'):
                        created_at = created_at.isoformat()
                    all_images.append(LibraryImage(
                        id=project_id,
                        url=img_url,
                        prompt=project_data.get("name", "Map"),
                        createdAt=str(created_at),
                        sessionId=project_id,
                        service=service
                    ))
            else:
                # Extract images from generatedContent (common pattern for other services)
                generated_content = project_data.get("state", {}).get("generatedContent", {})
                images = generated_content.get("images", [])
                
                for img in images:
                    img_url = img.get("url")
                    if img_url and img_url not in seen_urls:
                        seen_urls.add(img_url)
                        all_images.append(LibraryImage(
                            id=img.get("id", f"{project_id}_{len(all_images)}"),
                            url=img_url,
                            prompt=img.get("prompt", ""),
                            createdAt=img.get("timestamp", img.get("createdAt", "")),
                            sessionId=img.get("sessionId", sessionId or ""),
                            service=service
                        ))
        
        # Sort by createdAt (most recent first)
        all_images.sort(key=lambda x: x.createdAt, reverse=True)
        
        # Paginate
        total = len(all_images)
        total_pages = max(1, (total + limit - 1) // limit)
        start = (page - 1) * limit
        end = start + limit
        paginated_images = all_images[start:end]
        
        logger.info(f"✅ [ImageLibrary] Returning {len(paginated_images)} of {total} images")
        
        return LibraryResponse(
            images=paginated_images,
            total=total,
            totalPages=total_pages,
            page=page,
            limit=limit
        )
        
    except Exception as e:
        logger.error(f"❌ [ImageLibrary] Error: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Failed to fetch library: {str(e)}")


# =============================================================================
# IMAGE DELETION
# =============================================================================

@router.delete('/delete')
async def delete_image(
    asset_id: str = Query(..., description="Opaque server-issued asset ID"),
    service: str = Query("statblock", description="Service hint for project cleanup"),
    current_user: User = Depends(get_current_user)
):
    """
    Delete an image by opaque asset_id from the server-controlled registry.

    User-supplied URLs and mutable project references never authorize deletion.
    """
    from firebase_admin import firestore

    try:
        if not asset_id.strip():
            raise HTTPException(status_code=422, detail="asset_id is required")

        user_id = current_user.user_id
        asset = get_asset_for_owner(asset_id, user_id)
        if asset is None:
            raise HTTPException(
                status_code=403,
                detail="Asset not found or not owned by caller",
            )

        logger.info(
            "ImageDelete asset_id=%s user_id=%s provider=%s",
            asset_id,
            user_id,
            asset.provider,
        )

        cloud_deleted = False
        if asset.provider == "cloudflare_images" and asset.object_key:
            cloud_deleted = await delete_cloudflare_image_by_id(asset.object_key)
        elif asset.canonical_url:
            # Legacy R2 path using trusted key from registry only
            result = await image_management_service.delete_image(asset.canonical_url)
            cloud_deleted = result.success

        delete_asset_record(asset_id)

        # Best-effort remove URL refs from caller's projects
        firestore_deleted = False
        db = firestore.client()
        collection_name = SERVICE_COLLECTION_MAP.get(service, "statblock_projects")
        user_field = _owner_field_for_service(service)
        image_url = asset.canonical_url
        query = db.collection(collection_name).where(user_field, "==", user_id)
        for doc in query.stream():
            project_data = doc.to_dict() or {}
            if service == "map":
                if project_data.get("base_image_asset_id") == asset_id or (
                    image_url
                    and (
                        project_data.get("base_image_url") == image_url
                        or project_data.get("baseImageUrl") == image_url
                    )
                ):
                    doc.reference.update({
                        "base_image_url": None,
                        "baseImageUrl": None,
                        "base_image_asset_id": None,
                    })
                    firestore_deleted = True
                continue
            images = (
                project_data.get("state", {})
                .get("generatedContent", {})
                .get("images", [])
            )
            updated = [
                img for img in images
                if img.get("asset_id") != asset_id and img.get("url") != image_url
            ]
            if len(updated) < len(images):
                doc.reference.update({"state.generatedContent.images": updated})
                firestore_deleted = True

        return {
            "success": True,
            "cloud_deleted": cloud_deleted,
            "firestore_deleted": firestore_deleted,
            "asset_id": asset_id,
            "message": f"Asset deleted (cloud={cloud_deleted}, firestore={firestore_deleted})",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("ImageDelete error: %s", type(e).__name__)
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail="Internal server error")
