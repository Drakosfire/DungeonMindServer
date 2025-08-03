"""
Asset management for card generation - handles overlays, stickers, and other decorative elements
"""
import logging
import urllib.request
from typing import Dict, Any, Optional
from PIL import Image
from urllib.request import urlopen
from ..config.layout_config import ASSET_CONFIG
from ..utils.error_handler import ErrorHandler, AssetLoadError

logger = logging.getLogger(__name__)

class AssetManager:
    """Manages loading and application of card assets like overlays and stickers"""
    
    def __init__(self):
        self.asset_config = ASSET_CONFIG
        logger.info("AssetManager initialized with asset configuration")
    
    async def add_background_assets(self, image: Image.Image, item_details: Dict[str, Any]) -> Image.Image:
        """
        Add background assets (overlays that go behind text)
        
        Args:
            image: Base card image
            item_details: Item information for asset selection
            
        Returns:
            Image with background assets applied
        """
        try:
            # Add value overlay (background asset)
            image = await self._add_value_overlay(image)
            
            logger.info("Successfully added background assets to card")
            return image
            
        except Exception as e:
            logger.error(f"Failed to add background assets to card: {e}")
            # Continue without assets rather than failing completely
            logger.warning("Continuing without background assets due to error")
            return image
    
    async def add_foreground_assets(self, image: Image.Image, item_details: Dict[str, Any]) -> Image.Image:
        """
        Add foreground assets (overlays that go on top of text)
        
        Args:
            image: Base card image with text rendered
            item_details: Item information for asset selection
            
        Returns:
            Image with foreground assets applied
        """
        try:
            # Add rarity sticker (foreground asset)
            image = await self._add_rarity_sticker(image, item_details.get('Rarity', 'Default'))
            
            logger.info("Successfully added foreground assets to card")
            return image
            
        except Exception as e:
            logger.error(f"Failed to add foreground assets to card: {e}")
            # Continue without assets rather than failing completely
            logger.warning("Continuing without foreground assets due to error")
            return image
    
    async def add_assets(self, image: Image.Image, item_details: Dict[str, Any]) -> Image.Image:
        """
        Add all configured assets to the card image (legacy method for backward compatibility)
        
        Args:
            image: Base card image with text rendered
            item_details: Item information for asset selection
            
        Returns:
            Image with all assets applied
        """
        try:
            # Add background assets first
            image = await self.add_background_assets(image, item_details)
            
            # Add foreground assets
            image = await self.add_foreground_assets(image, item_details)
            
            logger.info("Successfully added all assets to card")
            return image
            
        except Exception as e:
            logger.error(f"Failed to add assets to card: {e}")
            # Continue without assets rather than failing completely
            logger.warning("Continuing without assets due to error")
            return image
    
    async def _add_value_overlay(self, image: Image.Image) -> Image.Image:
        """
        Add the value box overlay to the card
        
        Args:
            image: Base card image
            
        Returns:
            Image with value overlay applied
        """
        try:
            overlay_config = self.asset_config['value_overlay']
            
            # Load overlay image
            overlay_image = await self._load_asset_image(
                overlay_config['url'], 
                "value_overlay"
            )
            
            # Resize overlay to match card dimensions
            overlay_size = (
                overlay_config['size']['width'],
                overlay_config['size']['height']
            )
            overlay_image = overlay_image.resize(overlay_size)
            
            # Apply overlay
            position = (
                overlay_config['position']['x'],
                overlay_config['position']['y']
            )
            
            image = self._paste_with_transparency(image, overlay_image, position)
            
            logger.info("Successfully added value overlay")
            return image
            
        except Exception as e:
            ErrorHandler.handle_asset_load_error("value_overlay", e)
            return image
    
    async def _add_rarity_sticker(self, image: Image.Image, rarity: str) -> Image.Image:
        """
        Add the rarity sticker to the card
        
        Args:
            image: Base card image
            rarity: Item rarity level
            
        Returns:
            Image with rarity sticker applied
        """
        try:
            sticker_config = self.asset_config['rarity_stickers']
            
            # Get sticker URL for rarity, fallback to Default
            sticker_url = sticker_config['urls'].get(rarity, sticker_config['urls']['Default'])
            
            # Load sticker image
            sticker_image = await self._load_asset_image(
                sticker_url, 
                f"rarity_sticker_{rarity}"
            )
            
            # Resize sticker
            sticker_size = (
                sticker_config['size']['width'],
                sticker_config['size']['height']
            )
            sticker_image = sticker_image.resize(sticker_size)
            
            # Apply sticker
            position = (
                sticker_config['position']['x'],
                sticker_config['position']['y']
            )
            
            image = self._paste_with_transparency(image, sticker_image, position)
            
            logger.info(f"Successfully added {rarity} rarity sticker")
            return image
            
        except Exception as e:
            ErrorHandler.handle_asset_load_error(f"rarity_sticker_{rarity}", e)
            return image
    
    async def _load_asset_image(self, url: str, asset_name: str) -> Image.Image:
        """
        Load an asset image from URL with proper error handling
        
        Args:
            url: URL of the asset image
            asset_name: Name of the asset for logging
            
        Returns:
            Loaded PIL Image
            
        Raises:
            AssetLoadError: If asset cannot be loaded
        """
        try:
            logger.info(f"Loading asset '{asset_name}' from: {url}")
            
            # Create request with User-Agent header
            request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            
            # Load and validate image
            with urlopen(request) as response:
                image = Image.open(response)
                image.load()  # Ensure image data is loaded
            
            logger.info(f"Successfully loaded asset '{asset_name}': {image.size} {image.mode}")
            return image
            
        except Exception as e:
            raise AssetLoadError(f"Failed to load asset '{asset_name}' from {url}: {e}")
    
    def _paste_with_transparency(self, base_image: Image.Image, overlay_image: Image.Image, position: tuple) -> Image.Image:
        """
        Paste overlay image onto base image with proper transparency handling
        
        Args:
            base_image: Base image to paste onto
            overlay_image: Overlay image to paste
            position: (x, y) position for pasting
            
        Returns:
            Base image with overlay applied
        """
        # Convert overlay to RGBA if not already
        if overlay_image.mode != 'RGBA':
            overlay_image = overlay_image.convert('RGBA')
        
        # Paste with transparency mask
        base_image.paste(overlay_image, position, overlay_image)
        
        return base_image
    
    def get_available_rarities(self) -> list:
        """
        Get list of available rarity levels
        
        Returns:
            List of rarity level names
        """
        return list(self.asset_config['rarity_stickers']['urls'].keys())
    
    def validate_rarity(self, rarity: str) -> str:
        """
        Validate rarity and return valid rarity or default
        
        Args:
            rarity: Rarity level to validate
            
        Returns:
            Valid rarity level
        """
        available_rarities = self.get_available_rarities()
        if rarity in available_rarities:
            return rarity
        else:
            logger.warning(f"Unknown rarity '{rarity}', using 'Default'")
            return 'Default'