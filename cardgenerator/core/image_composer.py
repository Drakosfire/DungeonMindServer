"""
Image composition and management for card generation
"""
import logging
from typing import Tuple
from PIL import Image
from ..config.layout_config import CARD_LAYOUT
from ..utils.error_handler import ErrorHandler, ImageLoadError

logger = logging.getLogger(__name__)

class ImageComposer:
    """Handles image loading, validation, and basic composition operations"""
    
    def __init__(self):
        self.layout = CARD_LAYOUT
        self.expected_dimensions = (
            self.layout['dimensions']['width'],
            self.layout['dimensions']['height']
        )
        logger.info(f"ImageComposer initialized with expected dimensions: {self.expected_dimensions}")
    
    async def load_and_resize(self, image_url: str) -> Image.Image:
        """
        Load image from URL and ensure it matches expected dimensions
        
        Args:
            image_url: URL of the image to load
            
        Returns:
            PIL Image resized to expected dimensions
            
        Raises:
            ImageLoadError: If image cannot be loaded or processed
        """
        try:
            # Load image with error handling
            image = await ErrorHandler.handle_image_load(image_url)
            
            # Validate and resize to expected dimensions
            image = ErrorHandler.validate_dimensions(
                image, 
                self.expected_dimensions[0], 
                self.expected_dimensions[1]
            )
            
            logger.info(f"Successfully loaded and resized image to {image.size}")
            return image
            
        except Exception as e:
            logger.error(f"Failed to load and resize image from {image_url}: {e}")
            raise ImageLoadError(f"Image composition failed: {e}")
    
    def validate_image_format(self, image: Image.Image) -> Image.Image:
        """
        Validate and convert image format for card composition
        
        Args:
            image: PIL Image to validate
            
        Returns:
            Image in appropriate format for composition
        """
        # Ensure image is in RGB or RGBA mode for proper composition
        if image.mode not in ['RGB', 'RGBA']:
            logger.info(f"Converting image from {image.mode} to RGB")
            if image.mode == 'P':
                # Palette mode - convert via RGBA to preserve transparency
                image = image.convert('RGBA').convert('RGB')
            else:
                image = image.convert('RGB')
        
        return image
    
    def get_expected_dimensions(self) -> Tuple[int, int]:
        """
        Get the expected dimensions for card images
        
        Returns:
            Tuple of (width, height)
        """
        return self.expected_dimensions
    
    def create_blank_card(self, color: str = 'white') -> Image.Image:
        """
        Create a blank card image with the expected dimensions
        
        Args:
            color: Background color for the blank card
            
        Returns:
            Blank PIL Image with card dimensions
        """
        blank_image = Image.new('RGB', self.expected_dimensions, color)
        logger.info(f"Created blank card image: {blank_image.size}")
        return blank_image