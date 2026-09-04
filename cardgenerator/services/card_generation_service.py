"""
Card Generation Service

Handles all card generation business logic including:
- AI-powered item description generation  
- Image generation using FAL client
- Card text rendering using the new pipeline
- Integration with prompt management system

This service extracts the core generation logic from the monolithic router.
"""

import logging
import json
from typing import Dict, Any, List, Optional, Tuple
from PIL import Image
from pydantic import BaseModel, ValidationError

from cardgenerator.prompts.prompt_manager import prompt_manager
from cardgenerator.card_generator_new import render_text_on_card
from cardgenerator.utils.error_handler import CardGenerationError, ValidationError as CardValidationError
from generationengine import GenerationEngineError, ImageRequest, TextRequest
from shared.generation import get_generation_client
from shared.generated_images import publish_generated_image
from shared.inference_policy import inference_for

logger = logging.getLogger(__name__)

# Pydantic models for structured output
class ItemProperties(BaseModel):
    Name: str
    Type: str
    Rarity: str
    Value: str
    Properties: List[str]
    Damage: Tuple[str, str]  # Matches frontend format
    Weight: str
    Description: str
    Quote: str
    SD_Prompt: str  # Matches frontend 'SD Prompt'

class GeneratedImageResult(BaseModel):
    images: List[Dict[str, Any]]
    success: bool
    message: Optional[str] = None

class CardGenerationService:
    """
    Service for handling all card generation operations
    
    Provides clean interface for:
    - Item description generation via AI
    - Image generation for cards
    - Text rendering on card images
    """
    
    def __init__(self):
        self.prompt_manager = prompt_manager
        logger.info("CardGenerationService initialized")
    
    async def generate_item_description(self, user_idea: str) -> Dict[str, Any]:
        """
        Generate item description from user input using AI
        
        Args:
            user_idea: User's description of the item to generate
            
        Returns:
            Dictionary containing generated item details
            
        Raises:
            CardGenerationError: If generation fails
            CardValidationError: If generated content is invalid
        """
        try:
            logger.info(f"Generating item description for: {user_idea}")
            
            # Use the new prompt management system
            prompt = self.prompt_manager.render_prompt(
                template_name="item_generation",
                context={"item_name": user_idea}
            )
            
            # Define the JSON schema for structured output
            item_schema = {
                "name": "item",
                "schema": {
                    "type": "object",
                    "properties": {
                        "Name": {"type": "string", "description": "The name of the magical item."},
                        "Type": {"type": "string", "description": "The type or category of the magical item."},
                        "Rarity": {
                            "type": "string",
                            "description": "The rarity classification of the item.",
                            "enum": ["Common", "Uncommon", "Rare", "Very Rare", "Legendary"]
                        },
                        "Value": {"type": "string", "description": "The monetary value of the item."},
                        "Properties": {
                            "type": "array",
                            "description": "Unique properties or abilities of the magical item.",
                            "items": {"type": "string"}
                        },
                        "Damage Formula": {"type": "string", "description": "The formula used to calculate the damage of the item."},
                        "Damage Type": {"type": "string", "description": "The type of damage the item inflicts."},
                        "Weight": {"type": "string", "description": "The weight of the item."},
                        "Description": {"type": "string", "description": "A detailed description of the item, including its design and features."},
                        "Quote": {"type": "string", "description": "A memorable quote associated with the item."},
                        "SD Prompt": {"type": "string", "description": "A description used for visual or artistic representation of the item."}
                    },
                    "required": ["Name", "Type", "Rarity", "Value", "Properties", "Weight", "Description", "Quote", "SD Prompt"],
                    "additionalProperties": False
                }
            }
            
            action = inference_for("card_item_generation")
            result = await get_generation_client().generate_structured(
                TextRequest(
                    user_prompt=prompt,
                    profile=action.profile,
                    model=action.model,
                    json_schema=item_schema["schema"],
                    schema_name=item_schema["name"],
                )
            )
            parsed_data = result.parsed
            if parsed_data is None and result.text:
                parsed_data = json.loads(result.text)
            if not parsed_data:
                raise CardValidationError("Generated data missing required 'Name' field")
            
            # Handle OpenAI wrapping response in extra structure
            if "properties" in parsed_data and isinstance(parsed_data["properties"], dict):
                parsed_data = parsed_data["properties"]
            
            # Validate required fields
            if "Name" not in parsed_data:
                raise CardValidationError("Generated data missing required 'Name' field")
            
            # Format for frontend (matches existing API)
            formatted_response = {parsed_data["Name"]: parsed_data}
            
            logger.info(f"Successfully generated item: {parsed_data['Name']}")
            return formatted_response
            
        except CardValidationError:
            raise
        except GenerationEngineError as error:
            logger.error("Item generation failed: %s", error.failure.message)
            raise CardGenerationError(f"Failed to generate item: {error.failure.message}") from error
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            raise CardGenerationError(f"Invalid AI response format: {str(e)}")
        except Exception as e:
            logger.error(f"Item generation failed: {e}")
            raise CardGenerationError(f"Failed to generate item: {str(e)}")
    
    async def generate_core_images(self, sd_prompt: str, num_images: int = 4) -> GeneratedImageResult:
        """
        Generate core images directly from text prompt (Step 2 workflow)
        
        Uses GenerationEngine generate_image and DungeonMindServer Cloudflare publish.
        
        Args:
            sd_prompt: Stable Diffusion prompt for image generation
            num_images: Number of images to generate
            
        Returns:
            GeneratedImageResult with image URLs and metadata
            
        Raises:
            CardGenerationError: If image generation fails
        """
        try:
            logger.info(f"🎨 [GenerationEngine] Generating {num_images} core images with prompt: {sd_prompt[:100]}...")
            action = inference_for("card_core_image_generation")
            ge_request = ImageRequest(
                prompt=sd_prompt,
                profile=action.profile,
                model=action.model,
                num_images=num_images,
                width=1024,
                height=1024,
            )
            response = await get_generation_client().generate_image(ge_request)
            images = []
            for img_result in response.images:
                uploaded = await publish_generated_image(img_result)
                images.append({"url": uploaded.url})
            logger.info("✅ [GenerationEngine] Generated %s images successfully", len(images))
            return GeneratedImageResult(
                images=images,
                success=True,
                message=f"Generated {len(images)} images"
            )
        except GenerationEngineError as error:
            logger.error("❌ [GenerationEngine] Core image generation failed: %s", error.failure.message)
            raise CardGenerationError(f"Failed to generate images: {error.failure.message}") from error
        except Exception as e:
            logger.error(f"❌ [GenerationEngine] Core image generation failed: {e}")
            raise CardGenerationError(f"Failed to generate images: {str(e)}")
    
    async def generate_card_images(self, template_url: str, sd_prompt: str, num_images: int) -> GeneratedImageResult:
        """
        Generate card images using template and SD prompt (Step 3 workflow)
        
        Uses GenerationEngine generate_image with image-to-image parameters.
        
        Args:
            template_url: URL of the template image
            sd_prompt: Stable Diffusion prompt
            num_images: Number of images to generate
            
        Returns:
            GeneratedImageResult with generated card images
            
        Raises:
            CardGenerationError: If generation fails
        """
        try:
            logger.info(f"🎨 [GenerationEngine] Generating {num_images} card images from template using image-to-image")
            
            # Enhanced prompt for card generation
            enhanced_prompt = (
                f"blank card, no text, blank textbox at top for title, "
                f"mid for details and bottom for description, detailed high quality "
                f"thematic borders, {sd_prompt} in on a background of appropriate setting or location"
            )
            
            action = inference_for("card_i2i_generation")
            ge_request = ImageRequest(
                prompt=enhanced_prompt,
                profile=action.profile,
                model=action.model,
                num_images=num_images,
                width=768,
                height=1024,
                source_image_url=template_url,
                strength=0.85,
            )
            response = await get_generation_client().generate_image(ge_request)
            images = []
            for img_result in response.images:
                uploaded = await publish_generated_image(img_result)
                images.append({"url": uploaded.url})
            logger.info("✅ [GenerationEngine] Generated %s card images successfully", len(images))
            return GeneratedImageResult(
                images=images,
                success=True,
                message=f"Generated {len(images)} card images"
            )
        except GenerationEngineError as error:
            logger.error("❌ [GenerationEngine] Card image generation failed: %s", error.failure.message)
            raise CardGenerationError(f"Failed to generate card images: {error.failure.message}") from error
        except Exception as e:
            logger.error(f"❌ [GenerationEngine] Card image generation failed: {e}")
            raise CardGenerationError(f"Failed to generate card images: {str(e)}")
    
    async def render_text_on_card(self, image_url: str, item_details: Dict[str, Any]) -> Image.Image:
        """
        Render text on card using the new modular pipeline
        
        Args:
            image_url: URL of the base card image
            item_details: Dictionary containing item information
            
        Returns:
            PIL Image with rendered text
            
            
        Raises:
            CardGenerationError: If rendering fails
        """
        try:
            logger.info(f"Rendering text on card for item: {item_details.get('Name', 'Unknown')}")
            
            # Use the new async render function from the pipeline
            image_object = await render_text_on_card(image_url, item_details)
            
            logger.info(f"Successfully rendered text for: {item_details.get('Name', 'Unknown')}")
            return image_object
            
        except Exception as e:
            logger.error(f"Card text rendering failed: {e}")
            raise CardGenerationError(f"Failed to render card text: {str(e)}")

# Export the service instance
card_generation_service = CardGenerationService()