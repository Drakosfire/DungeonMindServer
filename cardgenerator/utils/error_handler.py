"""
Comprehensive error handling for card generation pipeline
"""
import logging
import requests
from PIL import Image
from io import BytesIO
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Custom exceptions for different failure modes
class CardRenderingError(Exception):
    """Base exception for card rendering errors"""
    pass

class ImageLoadError(CardRenderingError):
    """Failed to load image from URL"""
    pass

class TextRenderingError(CardRenderingError):
    """Failed to render text on image"""
    pass

class AssetLoadError(CardRenderingError):
    """Failed to load overlay/sticker assets"""
    pass

class ValidationError(CardRenderingError):
    """Input validation failed"""
    pass

class ErrorHandler:
    """Centralized error handling and recovery utilities"""
    
    @staticmethod
    async def handle_image_load(url: str, timeout: int = 30) -> Image.Image:
        """
        Load image with comprehensive error handling and validation
        
        Args:
            url: Image URL to load
            timeout: Request timeout in seconds
            
        Returns:
            PIL Image object
            
        Raises:
            ImageLoadError: If image cannot be loaded or is invalid
        """
        try:
            logger.info(f"Loading image from URL: {url}")
            
            # Make request with timeout and proper headers
            headers = {'User-Agent': 'Mozilla/5.0 (CardGenerator/1.0)'}
            response = requests.get(url, timeout=timeout, headers=headers)
            response.raise_for_status()
            
            # Validate content type (skip for Gradio URLs)
            if not url.startswith("http://127.0.0.1:7860/gradio_api/file="):
                content_type = response.headers.get('content-type', '')
                if 'image' not in content_type:
                    raise ImageLoadError(f"URL does not point to an image. Content-Type: {content_type}")
            
            # Load and validate image
            image_data = BytesIO(response.content)
            image = Image.open(image_data)
            
            # Ensure image can be processed
            image.verify()
            
            # Reload image after verify (verify() makes image unusable)
            image_data.seek(0)
            image = Image.open(image_data)
            
            logger.info(f"Successfully loaded image: {image.size} {image.mode}")
            return image
            
        except requests.exceptions.Timeout as e:
            raise ImageLoadError(f"Timeout loading image from {url}: {e}")
        except requests.exceptions.RequestException as e:
            raise ImageLoadError(f"Network error loading image from {url}: {e}")
        except Image.UnidentifiedImageError as e:
            raise ImageLoadError(f"Cannot identify image format from {url}: {e}")
        except Exception as e:
            raise ImageLoadError(f"Unexpected error loading image from {url}: {e}")
    
    @staticmethod
    def validate_item_details(item_details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate required fields in item details
        
        Args:
            item_details: Dictionary containing item information
            
        Returns:
            Validated item details dictionary
            
        Raises:
            ValidationError: If required fields are missing or invalid
        """
        required_fields = [
            'Name', 'Type', 'Rarity', 'Value', 'Properties', 
            'Weight', 'Description', 'Quote', 'SD Prompt'
        ]
        
        # Check for missing fields
        for field in required_fields:
            if field not in item_details:
                raise ValidationError(f"Missing required field: {field}")
            
            # Check for empty values (except Properties which can be empty list)
            if field == 'Properties':
                if not isinstance(item_details[field], list):
                    raise ValidationError(f"Field '{field}' must be a list")
            else:
                if not item_details[field] or (isinstance(item_details[field], str) and not item_details[field].strip()):
                    raise ValidationError(f"Empty required field: {field}")
        
        # Validate specific field formats
        valid_rarities = ['Common', 'Uncommon', 'Rare', 'Very Rare', 'Legendary']
        if item_details['Rarity'] not in valid_rarities:
            raise ValidationError(f"Invalid rarity '{item_details['Rarity']}'. Must be one of: {valid_rarities}")
        
        # Validate value format (should contain currency)
        value = item_details['Value'].strip()
        if not any(currency in value for currency in ['cp', 'sp', 'ep', 'gp', 'pp']):
            logger.warning(f"Value '{value}' may not contain valid currency denomination")
        
        logger.info(f"Successfully validated item details for: {item_details['Name']}")
        return item_details
    
    @staticmethod
    def validate_dimensions(image: Image.Image, expected_width: int, expected_height: int) -> Image.Image:
        """
        Validate and resize image to expected dimensions if needed
        
        Args:
            image: PIL Image to validate
            expected_width: Expected image width
            expected_height: Expected image height
            
        Returns:
            Image resized to expected dimensions
        """
        current_size = image.size
        expected_size = (expected_width, expected_height)
        
        if current_size != expected_size:
            logger.info(f"Resizing image from {current_size} to {expected_size}")
            image = image.resize(expected_size, Image.Resampling.LANCZOS)
        
        return image
    
    @staticmethod
    def handle_asset_load_error(asset_name: str, error: Exception) -> None:
        """
        Handle asset loading errors with appropriate logging and fallback suggestions
        
        Args:
            asset_name: Name of the asset that failed to load
            error: The exception that occurred
        """
        logger.error(f"Failed to load asset '{asset_name}': {error}")
        
        # Log suggestions for common issues
        if "timeout" in str(error).lower():
            logger.warning(f"Asset '{asset_name}' timed out. Consider using a CDN or local cache.")
        elif "not found" in str(error).lower() or "404" in str(error):
            logger.warning(f"Asset '{asset_name}' not found. Check URL validity.")
        elif "ssl" in str(error).lower():
            logger.warning(f"SSL error loading '{asset_name}'. Check certificate validity.")