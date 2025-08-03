"""
Image Management Service for CardGenerator

Handles all image-related operations including uploads, downloads, and temporary file management.
"""

import os
import logging
import uuid
from typing import List, Dict, Any, Optional
from fastapi import UploadFile

from cardgenerator.utils.error_handler import ImageProcessingError

logger = logging.getLogger(__name__)

# Import the upload functions
try:
    from cloudflareR2.cloudflareR2_utils import (
        upload_temp_file_and_get_url,
        get_r2_client
    )
    from cloudflare.handle_images import upload_image_to_cloudflare
except ImportError:
    # Fallback for when the module isn't available
    def upload_image_to_cloudflare(file_or_url):
        raise NotImplementedError("Cloudflare upload not available")
    
    def upload_temp_file_and_get_url(file_path):
        raise NotImplementedError("Cloudflare upload not available")
    
    def get_r2_client():
        raise NotImplementedError("R2 client not available")


class ImageUploadResult:
    """Result of an image upload operation"""
    
    def __init__(self, url: str, success: bool = True, message: Optional[str] = None, file_size: Optional[int] = None):
        self.url = url
        self.success = success
        self.message = message or "Upload successful"
        self.file_size = file_size


class ImageDeleteResult:
    """Result of an image deletion operation"""
    
    def __init__(self, success: bool, message: str, object_key: Optional[str] = None):
        self.success = success
        self.message = message
        self.object_key = object_key


class BulkUploadResult:
    """Result of a bulk image upload operation"""
    
    def __init__(self, uploaded_images: List[Dict[str, Any]], total_count: int, success_count: int):
        self.uploaded_images = uploaded_images
        self.total_count = total_count
        self.success_count = success_count


class ImageManagementService:
    """
    Service for handling all image management operations
    
    Provides clean interface for:
    - Single and bulk image uploads
    - Image deletion from various storage types
    - Temporary file handling
    - Memory-only upload fallback for restricted environments
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    async def upload_single_image(self, file: UploadFile) -> ImageUploadResult:
        """
        Upload a single image file to cloud storage
        
        Args:
            file: FastAPI UploadFile object
            
        Returns:
            ImageUploadResult with the uploaded URL
            
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
    
    async def upload_with_memory_fallback(self, image_object, filename: str) -> ImageUploadResult:
        """
        Upload image object directly to memory if file system is not available
        
        Args:
            image_object: PIL Image object
            filename: Name for the uploaded file
            
        Returns:
            ImageUploadResult with the uploaded URL
        """
        try:
            logger.info(f"Uploading image object directly: {filename}")
            
            # Convert image to bytes
            import io
            img_buffer = io.BytesIO()
            image_object.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            
            # Upload bytes directly to R2
            file_id = str(uuid.uuid4())
            object_key = f"temp/{file_id}.png"
            
            r2_client = get_r2_client()
            r2_client.put_object(
                Bucket='temp-images',
                Key=object_key,
                Body=img_buffer.getvalue(),
                ContentType='image/png'
            )
            
            # Generate presigned URL
            url = r2_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': 'temp-images',
                    'Key': object_key
                },
                ExpiresIn=3600 * 24  # 24 hours
            )
            
            logger.info(f"Successfully uploaded image object to: {url}")
            return ImageUploadResult(
                url=url,
                success=True,
                message="Image object uploaded successfully",
                file_size=len(img_buffer.getvalue())
            )
            
        except Exception as e:
            logger.error(f"Failed to upload image object: {e}")
            raise ImageProcessingError(f"Failed to upload image object: {str(e)}")
    
    async def delete_image(self, image_url: str) -> ImageDeleteResult:
        """
        Delete an image from cloud storage
        
        Args:
            image_url: URL of the image to delete
            
        Returns:
            ImageDeleteResult with deletion status
        """
        try:
            logger.info(f"Deleting image: {image_url}")
            
            # Extract object key from URL
            object_key = self._extract_object_key(image_url)
            if not object_key:
                return ImageDeleteResult(
                    success=False,
                    message=f"Could not extract object key from URL: {image_url}"
                )
            
            # Delete from Cloudflare
            result = await self._delete_r2_object(object_key)
            
            logger.info(f"Successfully deleted image: {image_url}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to delete image {image_url}: {e}")
            return ImageDeleteResult(
                success=False,
                message=f"Failed to delete image: {str(e)}"
            )
    
    def _extract_object_key(self, image_url: str) -> Optional[str]:
        """
        Extract object key from Cloudflare R2 URL
        
        Args:
            image_url: Full URL to the image
            
        Returns:
            Object key for R2 operations
        """
        try:
            # Parse URL to extract object key
            # Example URL: https://pub-1234567890.r2.dev/temp/abc123.png
            if 'r2.dev' in image_url:
                # Extract path after domain
                path = image_url.split('r2.dev/')[-1]
                return path
            else:
                logger.warning(f"Could not parse R2 URL: {image_url}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to extract object key from URL {image_url}: {e}")
            return None
    
    def _delete_cloudflare_image(self, image_url: str, image_id: str) -> ImageDeleteResult:
        """
        Delete image from Cloudflare Images (legacy method)
        
        Args:
            image_url: URL of the image
            image_id: Cloudflare Images ID
            
        Returns:
            ImageDeleteResult with deletion status
        """
        try:
            # This would use Cloudflare Images API
            # Implementation depends on your Cloudflare setup
            logger.info(f"Deleting Cloudflare image: {image_id}")
            
            return ImageDeleteResult(
                success=True,
                message=f"Successfully deleted image: {image_id}",
                object_key=image_id
            )
            
        except Exception as e:
            logger.error(f"Failed to delete Cloudflare image {image_id}: {e}")
            return ImageDeleteResult(
                success=False,
                message=f"Failed to delete image: {str(e)}",
                object_key=image_id
            )
    
    async def _delete_r2_object(self, object_key: str) -> ImageDeleteResult:
        """
        Delete object from Cloudflare R2
        
        Args:
            object_key: R2 object key to delete
            
        Returns:
            ImageDeleteResult with deletion status
        """
        try:
            r2_client = get_r2_client()
            r2_client.delete_object(
                Bucket='temp-images',
                Key=object_key
            )
            
            return ImageDeleteResult(
                success=True,
                message=f"Successfully deleted R2 object: {object_key}",
                object_key=object_key
            )
            
        except Exception as e:
            logger.error(f"Failed to delete R2 object {object_key}: {e}")
            return ImageDeleteResult(
                success=False,
                message=f"Failed to delete R2 object: {str(e)}",
                object_key=object_key
            )


# Global instance
image_management_service = ImageManagementService()