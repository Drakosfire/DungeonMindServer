"""
Main card renderer - orchestrates the entire card generation pipeline
"""
import logging
from typing import Dict, Any
from PIL import Image, ImageFilter
from .text_processor import TextProcessor
from .image_composer import ImageComposer
from .asset_manager import AssetManager
from ..utils.error_handler import ErrorHandler, CardRenderingError

logger = logging.getLogger(__name__)

class CardRenderer:
    """
    Main card renderer that orchestrates the entire card generation pipeline
    
    This class provides a clean interface for generating cards by coordinating
    the text processor, image composer, and asset manager components.
    """
    
    def __init__(self):
        self.text_processor = TextProcessor()
        self.image_composer = ImageComposer()
        self.asset_manager = AssetManager()
        logger.info("CardRenderer initialized with all components")
    
    async def render_card(self, image_url: str, item_details: Dict[str, Any]) -> Image.Image:
        """
        Main entry point for card generation
        
        Args:
            image_url: URL of the base image for the card
            item_details: Dictionary containing all item information
            
        Returns:
            Final rendered card as PIL Image
            
        Raises:
            CardRenderingError: If card generation fails
        """
        try:
            logger.info(f"Starting card generation for item: {item_details.get('Name', 'Unknown')}")
            
            # Step 1: Validate input data
            validated_details = ErrorHandler.validate_item_details(item_details)
            logger.info("✅ Input validation completed")
            
            # Step 2: Load and prepare base image
            base_image = await self.image_composer.load_and_resize(image_url)
            base_image = self.image_composer.validate_image_format(base_image)
            logger.info("✅ Base image loaded and prepared")
            
            # Step 3: Prepare text elements
            text_elements = self.text_processor.prepare_text_elements(validated_details)
            logger.info("✅ Text elements prepared")
            
            # Step 4: Render text onto image
            image_with_text = await self.text_processor.render_text(base_image, text_elements)
            logger.info("✅ Text rendered onto image")
            
            # Step 5: Add overlays and assets
            image_with_assets = await self.asset_manager.add_assets(image_with_text, validated_details)
            logger.info("✅ Assets and overlays applied")
            
            # Step 6: Apply final effects
            final_image = image_with_assets.filter(ImageFilter.GaussianBlur(0.5))
            logger.info("✅ Final effects applied")
            
            logger.info(f"🎉 Card generation completed successfully for: {validated_details['Name']}")
            return final_image
            
        except Exception as e:
            error_msg = f"Card rendering failed for {item_details.get('Name', 'Unknown')}: {e}"
            logger.error(error_msg)
            raise CardRenderingError(error_msg)
    
    async def render_card_from_validated_data(self, image_url: str, validated_details: Dict[str, Any]) -> Image.Image:
        """
        Render card from already validated item details (skips validation step)
        
        Args:
            image_url: URL of the base image for the card
            validated_details: Pre-validated dictionary containing item information
            
        Returns:
            Final rendered card as PIL Image
        """
        try:
            logger.info(f"Starting card generation (pre-validated) for item: {validated_details.get('Name', 'Unknown')}")
            
            # Load and prepare base image
            base_image = await self.image_composer.load_and_resize(image_url)
            base_image = self.image_composer.validate_image_format(base_image)
            
            # Prepare and render text
            text_elements = self.text_processor.prepare_text_elements(validated_details)
            image_with_text = await self.text_processor.render_text(base_image, text_elements)
            
            # Add assets
            image_with_assets = await self.asset_manager.add_assets(image_with_text, validated_details)
            
            # Apply final effects
            final_image = image_with_assets.filter(ImageFilter.GaussianBlur(0.5))
            
            logger.info(f"🎉 Pre-validated card generation completed for: {validated_details['Name']}")
            return final_image
            
        except Exception as e:
            error_msg = f"Pre-validated card rendering failed for {validated_details.get('Name', 'Unknown')}: {e}"
            logger.error(error_msg)
            raise CardRenderingError(error_msg)
    
    def get_supported_rarities(self) -> list:
        """
        Get list of supported rarity levels
        
        Returns:
            List of supported rarity level names
        """
        return self.asset_manager.get_available_rarities()
    
    def get_card_dimensions(self) -> tuple:
        """
        Get the expected card dimensions
        
        Returns:
            Tuple of (width, height)
        """
        return self.image_composer.get_expected_dimensions()
    
    async def create_test_card(self) -> Image.Image:
        """
        Create a test card for debugging and validation
        
        Returns:
            Test card image
        """
        test_item = {
            'Name': 'Test Blade',
            'Type': 'Weapon',
            'Rarity': 'Rare',
            'Value': '250 gp',
            'Properties': ['Magical', 'Sharp'],
            'Weight': '3 lb',
            'Description': 'A finely crafted blade imbued with magical properties.',
            'Quote': 'The edge that cuts through darkness itself.',
            'SD Prompt': 'A magical sword with glowing runes'
        }
        
        # Create blank image for test
        blank_image = self.image_composer.create_blank_card()
        
        # Use a placeholder URL (will create blank if URL fails)
        try:
            return await self.render_card("https://via.placeholder.com/768x1024", test_item)
        except Exception as e:
            logger.warning(f"Test card generation failed, creating minimal version: {e}")
            return blank_image