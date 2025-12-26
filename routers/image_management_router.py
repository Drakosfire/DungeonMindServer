"""
Image Management Router

Focused router handling only image upload/delete operations.
Clean separation from card generation logic.

"""

import logging
from typing import List
from fastapi import APIRouter, HTTPException, File, UploadFile, Query
from pydantic import BaseModel
# TODO: This is a fragile dependency, need to fix this
from cardgenerator.services.image_management_service import image_management_service
from cardgenerator.utils.error_handler import ImageProcessingError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/images", tags=["Image Management"])

# Request models
class BulkUploadRequest(BaseModel):
    image_urls: List[str]

@router.post('/upload')
async def upload_single_image(file: UploadFile = File(...)):
    """
    Upload a single image file to cloud storage
    
    Simple, focused endpoint for image uploads
    """
    try:
        logger.info(f"Image upload request: {file.filename}")
        
        # Delegate to service layer
        result = await image_management_service.upload_single_image(file)
        
        return {
            "url": result.url,
            "success": result.success,
            "message": result.message
        }
        
    except ImageProcessingError as e:
        logger.error(f"Image upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in image upload: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post('/upload-bulk')
async def upload_multiple_images(request: BulkUploadRequest):
    """
    Upload multiple images to permanent storage
    
    Used for batch uploading generated images
    """
    try:
        # Validate input
        if not request.image_urls:
            raise HTTPException(status_code=422, detail="No image URLs provided")
        if len(request.image_urls) > 20:
            raise HTTPException(status_code=422, detail="Maximum 20 images per batch")
        
        logger.info(f"Bulk upload request: {len(request.image_urls)} images")
        
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
    return {
        "models": [
            {
                "id": "flux-pro",
                "name": "FLUX Pro",
                "description": "High quality, balanced speed (~10s)",
                "default": True,
                "tier": "free"
            },
            {
                "id": "imagen4",
                "name": "Imagen 4",
                "description": "Google's model, premium quality (~15s)",
                "tier": "free"
            },
            {
                "id": "openai",
                "name": "OpenAI GPT-Image",
                "description": "Fast, cost-effective (~5s)",
                "tier": "free"
            }
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


@router.delete('/delete')
async def delete_image(image_url: str = Query(..., description="URL of the image to delete")):
    """
    Delete an image from cloud storage
    
    Supports multiple storage backends (Cloudflare Images, R2)
    """
    try:
        # Validate input
        if not image_url.strip():
            raise HTTPException(status_code=422, detail="Image URL cannot be empty")
        
        logger.info(f"Image deletion request: {image_url}")
        
        # Delegate to service layer
        result = await image_management_service.delete_image(image_url)
        
        if result.success:
            return {
                "success": True,
                "message": result.message,
                "object_key": result.object_key
            }
        else:
            return {
                "success": False,
                "message": result.message
            }
        
    except Exception as e:
        logger.error(f"Unexpected error in image deletion: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")