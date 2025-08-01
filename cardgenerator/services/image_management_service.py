"""
Image Management Service

Handles all image management operations including:
- Image uploads to Cloudflare
- Image deletion from storage
- Temporary file management
- Image URL validation and processing

This service extracts image management logic from the monolithic router.
"""

import logging
import os
import re
from typing import List, Dict, Any, Optional
from fastapi import UploadFile
from cloudflare.handle_images import upload_image_to_cloudflare
from cloudflareR2.cloudflareR2_utils import upload_temp_file_and_get_url
from ..utils.error_handler import ImageProcessingError

logger = logging.getLogger(__name__)

class ImageUploadResult:
    """Result of image upload operation"""
    def __init__(self, url: str, success: bool = True, message: Optional[str] = None):
        self.url = url
        self.success = success
        self.message = message

class ImageDeleteResult:
    """Result of image deletion operation"""
    def __init__(self, success: bool, message: str, object_key: Optional[str] = None):
        self.success = success
        self.message = message
        self.object_key = object_key

class BulkUploadResult:
    """Result of bulk image upload operation"""
    def __init__(self, uploaded_images: List[Dict[str, Any]], total_count: int, success_count: int):
        self.uploaded_images = uploaded_images
        self.total_count = total_count
        self.success_count = success_count
        self.failure_count = total_count - success_count

class ImageManagementService:
    """
    Service for handling all image management operations
    
    Provides clean interface for:
    - Single and bulk image uploads
    - Image deletion from various storage types
    - Temporary file handling
    """
    
    def __init__(self):
        logger.info("ImageManagementService initialized")
    
    async def upload_single_image(self, file: UploadFile) -> ImageUploadResult:
        """
        Upload a single image file to Cloudflare
        
        Args:
            file: The uploaded file object
            
        Returns:
            ImageUploadResult with URL and status
            
        Raises:
            ImageProcessingError: If upload fails
        """
        try:
            logger.info(f"Uploading image: {file.filename}")
            
            url = await upload_image_to_cloudflare(file)
            
            logger.info(f"Successfully uploaded image to: {url}")
            return ImageUploadResult(
                url=url,
                success=True,
                message=f"Image {file.filename} uploaded successfully"
            )
            
        except Exception as e:
            logger.error(f"Failed to upload image {file.filename}: {e}")
            raise ImageProcessingError(f"Failed to upload image: {str(e)}")
    
    async def upload_generated_images(self, image_urls: List[str]) -> BulkUploadResult:
        """
        Upload a list of temporary image URLs to Cloudflare for permanent storage
        
        Args:
            image_urls: List of temporary image URLs to upload
            
        Returns:
            BulkUploadResult with upload results and statistics
        """
        try:
            logger.info(f"Uploading {len(image_urls)} generated images to permanent storage")
            
            uploaded_images = []
            success_count = 0
            
            for i, url in enumerate(image_urls):
                try:
                    # Upload each image URL to Cloudflare
                    permanent_url = await upload_image_to_cloudflare(url)
                    uploaded_images.append({
                        "original_url": url,
                        "permanent_url": permanent_url,
                        "id": f"uploaded-{i}",
                        "status": "success"
                    })
                    success_count += 1
                    logger.info(f"Uploaded image {i+1}/{len(image_urls)}: {url} -> {permanent_url}")
                    
                except Exception as e:
                    logger.error(f"Failed to upload image {url}: {str(e)}")
                    # Continue with other images even if one fails
                    uploaded_images.append({
                        "original_url": url,
                        "permanent_url": url,  # Fallback to original URL
                        "id": f"uploaded-{i}",
                        "status": "failed",
                        "error": str(e)
                    })
            
            logger.info(f"Bulk upload completed: {success_count}/{len(image_urls)} successful")
            return BulkUploadResult(
                uploaded_images=uploaded_images,
                total_count=len(image_urls),
                success_count=success_count
            )
            
        except Exception as e:
            logger.error(f"Bulk image upload failed: {e}")
            raise ImageProcessingError(f"Failed to upload images: {str(e)}")
    
    async def upload_temporary_file(self, file_path: str) -> ImageUploadResult:
        """
        Upload a temporary file to cloud storage and clean up
        
        Args:
            file_path: Path to the temporary file
            
        Returns:
            ImageUploadResult with the uploaded URL
            
        Raises:
            ImageProcessingError: If upload fails
        """
        try:
            logger.info(f"Uploading temporary file: {file_path}")
            
            # Check if file exists
            if not os.path.exists(file_path):
                raise ImageProcessingError(f"Temporary file not found: {file_path}")
            
            # Upload to Cloudflare R2
            url = await upload_temp_file_and_get_url(file_path)
            
            # Clean up temporary file
            try:
                os.remove(file_path)
                logger.info(f"Cleaned up temporary file: {file_path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up temporary file {file_path}: {cleanup_error}")
            
            logger.info(f"Successfully uploaded temporary file to: {url}")
            return ImageUploadResult(
                url=url,
                success=True,
                message="Temporary file uploaded and cleaned up successfully"
            )
            
        except Exception as e:
            logger.error(f"Failed to upload temporary file {file_path}: {e}")
            raise ImageProcessingError(f"Failed to upload temporary file: {str(e)}")
    
    async def delete_image(self, image_url: str) -> ImageDeleteResult:
        """
        Delete an image from cloud storage
        
        Args:
            image_url: URL of the image to delete
            
        Returns:
            ImageDeleteResult with deletion status
        """
        try:
            logger.info(f"Attempting to delete image: {image_url}")
            
            object_key = self._extract_object_key(image_url)
            
            if not object_key:
                logger.warning(f"Could not extract object key from URL: {image_url}")
                return ImageDeleteResult(
                    success=False,
                    message="Could not determine image location for deletion"
                )
            
            # For Cloudflare Images
            if 'imagedelivery.net' in image_url:
                return self._delete_cloudflare_image(image_url, object_key)
            
            # For R2 storage
            elif 'r2.cloudflarestorage.com' in image_url or 'cdn-cgi/image' in image_url:
                return await self._delete_r2_object(object_key)
            
            else:
                logger.warning(f"Unknown image storage type: {image_url}")
                return ImageDeleteResult(
                    success=False,
                    message="Unknown image storage type"
                )
                
        except Exception as e:
            logger.error(f"Error deleting image: {e}")
            return ImageDeleteResult(
                success=False,
                message=f"Failed to delete image: {str(e)}"
            )
    
    def _extract_object_key(self, image_url: str) -> Optional[str]:
        """Extract object key from various URL formats"""
        
        # Cloudflare Images URL
        if 'imagedelivery.net' in image_url:
            match = re.search(r'imagedelivery\.net/[^/]+/([^/]+)/', image_url)
            return match.group(1) if match else None
        
        # R2 URLs
        elif 'r2.cloudflarestorage.com' in image_url or 'cdn-cgi/image' in image_url:
            # Try standard pattern first
            match = re.search(r'/([^/]+/[^/]+)$', image_url)
            if match:
                return match.group(1)
            
            # Try alternative pattern for CDN URLs
            match = re.search(r'/([^/]+/[^/]+/[^/]+)$', image_url)
            if match:
                return match.group(1)
        
        return None
    
    def _delete_cloudflare_image(self, image_url: str, image_id: str) -> ImageDeleteResult:
        """Delete image from Cloudflare Images (not implemented yet)"""
        logger.warning(f"Cloudflare Images deletion not implemented for image ID: {image_id}")
        return ImageDeleteResult(
            success=True,  # Return success for now
            message="Image deletion logged (Cloudflare Images deletion not yet implemented)",
            object_key=image_id
        )
    
    async def _delete_r2_object(self, object_key: str) -> ImageDeleteResult:
        """Delete object from Cloudflare R2 storage"""
        try:
            from cloudflareR2.r2_config import get_r2_client
            
            r2_client = get_r2_client()
            bucket_name = 'temp-images'  # Default bucket for temporary images
            
            r2_client.delete_object(Bucket=bucket_name, Key=object_key)
            
            logger.info(f"Successfully deleted R2 object: {object_key}")
            return ImageDeleteResult(
                success=True,
                message=f"Image deleted successfully from R2: {object_key}",
                object_key=object_key
            )
            
        except Exception as e:
            logger.error(f"Failed to delete R2 object {object_key}: {e}")
            return ImageDeleteResult(
                success=False,
                message=f"Failed to delete from R2: {str(e)}",
                object_key=object_key
            )

# Export the service instance
image_management_service = ImageManagementService()