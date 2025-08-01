"""
Image Management Router

Focused router handling only image upload/delete operations.
Clean separation from card generation logic.

Extracted from monolithic cardgenerator_router.py as part of architectural refactoring.
"""

import logging
from typing import List
from fastapi import APIRouter, HTTPException, File, UploadFile, Query
from pydantic import BaseModel

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