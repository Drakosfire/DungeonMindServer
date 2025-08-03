"""
New streamlined card generator using the refactored pipeline architecture
"""
import logging
from typing import Dict, Any
from PIL import Image
from cardgenerator.core.card_renderer import CardRenderer
from cardgenerator.prompts.prompt_manager import prompt_manager
from cardgenerator.utils.error_handler import CardRenderingError, ValidationError

logger = logging.getLogger(__name__)

class CardGeneratorV2:
    """
    Modern card generator using the new modular pipeline
    
    This replaces the monolithic card_generator.py with a clean, 
    maintainable architecture.
    """
    
    def __init__(self):
        self.card_renderer = CardRenderer()
        self.prompt_manager = prompt_manager
        logger.info("CardGeneratorV2 initialized with new pipeline")
    
    async def generate_item_details(self, item_name: str) -> Dict[str, Any]:
        """
        Generate item details using AI with new prompt management
        
        Args:
            item_name: Name of the item to generate
            
        Returns:
            Dictionary containing generated item details
            
        Raises:
            ValidationError: If generated details are invalid
        """
        try:
            logger.info(f"Generating item details for: {item_name}")
            
            # Render prompt using new prompt manager
            prompt = self.prompt_manager.render_prompt(
                template_name="item_generation",
                context={"item_name": item_name}
            )
            
            # TODO: Replace with actual AI service call
            # For now, return mock data that matches the new structure
            mock_response = self._generate_mock_response(item_name)
            
            # Validate response using prompt manager
            validated_details = self.prompt_manager.validate_response(
                template_name="item_generation",
                response=mock_response
            )
            
            logger.info(f"Successfully generated and validated details for: {item_name}")
            return validated_details
            
        except Exception as e:
            logger.error(f"Failed to generate item details for {item_name}: {e}")
            raise ValidationError(f"Item generation failed: {e}")
    
    async def render_text_on_card(self, image_url: str, item_details: Dict[str, Any]) -> Image.Image:
        """
        Render text on card using the new pipeline
        
        Args:
            image_url: URL of the base image
            item_details: Dictionary containing item information
            
        Returns:
            Final rendered card as PIL Image
            
        Raises:
            CardRenderingError: If card rendering fails
        """
        try:
            logger.info(f"Rendering card for item: {item_details.get('Name', 'Unknown')}")
            
            # Use the new card renderer pipeline
            final_card = await self.card_renderer.render_card(image_url, item_details)
            
            logger.info("Card rendering completed successfully")
            return final_card
            
        except Exception as e:
            logger.error(f"Card rendering failed: {e}")
            raise CardRenderingError(f"Failed to render card: {e}")
    
    async def generate_complete_card(self, item_name: str, image_url: str) -> Image.Image:
        """
        Complete card generation pipeline - from item name to final card
        
        Args:
            item_name: Name of the item to generate
            image_url: URL of the base image
            
        Returns:
            Final rendered card as PIL Image
        """
        try:
            logger.info(f"Starting complete card generation for: {item_name}")
            
            # Step 1: Generate item details
            item_details = await self.generate_item_details(item_name)
            
            # Step 2: Render card
            final_card = await self.render_text_on_card(image_url, item_details)
            
            logger.info(f"Complete card generation finished for: {item_name}")
            return final_card
            
        except Exception as e:
            logger.error(f"Complete card generation failed for {item_name}: {e}")
            raise CardRenderingError(f"Complete card generation failed: {e}")
    
    def _generate_mock_response(self, item_name: str) -> str:
        """
        Generate mock AI response for testing
        
        This will be replaced with actual AI service integration
        """
        import json
        
        mock_data = {
            "Name": item_name,
            "Type": "Weapon" if "sword" in item_name.lower() or "blade" in item_name.lower() else "Wondrous Item",
            "Rarity": "Rare",
            "Value": "250 gp",
            "Properties": ["Magical", "Durable"],
            "Weight": "2 lb",
            "Description": f"A finely crafted {item_name.lower()} imbued with magical properties that gleam in the light.",
            "Quote": "In the right hands, this becomes more than just an item—it becomes legend.",
            "SD Prompt": f"Fantasy concept art of a {item_name.lower()}, ornate magical design, intricate details, dramatic lighting, highly detailed, 8k resolution, masterpiece quality"
        }
        
        return json.dumps(mock_data)
    
    def get_supported_rarities(self) -> list:
        """Get list of supported rarity levels"""
        return self.card_renderer.get_supported_rarities()
    
    def get_card_dimensions(self) -> tuple:
        """Get expected card dimensions"""
        return self.card_renderer.get_card_dimensions()
    
    async def create_test_card(self) -> Image.Image:
        """Create a test card for validation"""
        return await self.card_renderer.create_test_card()

# Convenience function to maintain compatibility with existing code
async def render_text_on_card(image_url: str, item_details: Dict[str, Any]) -> Image.Image:
    """
    Compatibility function for existing code
    
    Args:
        image_url: URL of the base image
        item_details: Dictionary containing item information
        
    Returns:
        Final rendered card as PIL Image
    """
    generator = CardGeneratorV2()
    return await generator.render_text_on_card(image_url, item_details)