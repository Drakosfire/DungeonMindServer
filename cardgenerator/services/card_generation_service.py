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
import fal_client
from typing import Dict, Any, List, Optional, Tuple
from openai import OpenAI
from PIL import Image
from pydantic import BaseModel, ValidationError

from cardgenerator.prompts.prompt_manager import prompt_manager
from cardgenerator.card_generator_new import render_text_on_card
from cardgenerator.utils.error_handler import CardGenerationError, ValidationError as CardValidationError

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
        self.openai_client = OpenAI()
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
            
            # Make the API call
            response = self.openai_client.beta.chat.completions.parse(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_schema", "json_schema": item_schema}
            )
            
            # Extract and validate the structured data
            parsed_data = response.choices[0].message.parsed if response.choices else None
            if not parsed_data:
                # Fallback to content if parsed is missing
                parsed_data = response.choices[0].message.content
                if isinstance(parsed_data, str):
                    parsed_data = json.loads(parsed_data)
            
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
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            raise CardGenerationError(f"Invalid AI response format: {str(e)}")
        except Exception as e:
            logger.error(f"Item generation failed: {e}")
            raise CardGenerationError(f"Failed to generate item: {str(e)}")
    
    async def generate_core_images(self, sd_prompt: str, num_images: int = 4) -> GeneratedImageResult:
        """
        Generate core images directly from text prompt (Step 2 workflow)
        
        Args:
            sd_prompt: Stable Diffusion prompt for image generation
            num_images: Number of images to generate
            
        Returns:
            GeneratedImageResult with image URLs and metadata
            
        Raises:
            CardGenerationError: If image generation fails
        """
        try:
            logger.info(f"Generating {num_images} core images with prompt: {sd_prompt[:100]}...")
            
            handler = fal_client.submit(
                "fal-ai/imagen4/preview/fast", 
                arguments={
                    "prompt": sd_prompt,
                    "num_inference_steps": 28,
                    "guidance_scale": 3.5,
                    "num_images": num_images,
                    "image_size": {"width": 1024, "height": 1024}
                }
            )
            
            result = handler.get()
            logger.info(f"Generated {len(result.get('images', []))} images successfully")
            
            return GeneratedImageResult(
                images=result.get('images', []),
                success=True,
                message=f"Generated {len(result.get('images', []))} images"
            )
            
        except Exception as e:
            logger.error(f"Core image generation failed: {e}")
            raise CardGenerationError(f"Failed to generate images: {str(e)}")
    
    async def generate_card_images(self, template_url: str, sd_prompt: str, num_images: int) -> GeneratedImageResult:
        """
        Generate card images using template and SD prompt (Step 3 workflow)
        
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
            logger.info(f"Generating {num_images} card images from template")
            
            # Enhanced prompt for card generation
            enhanced_prompt = (
                f"blank card, no text, blank textbox at top for title, "
                f"mid for details and bottom for description, detailed high quality "
                f"thematic borders, {sd_prompt} in on a background of appropriate setting or location"
            )
            
            handler = fal_client.submit(
                "fal-ai/flux-lora/image-to-image",
                arguments={
                    "num_inference_steps": 35,
                    "prompt": enhanced_prompt,
                    "num_images": num_images,
                    "image_url": template_url,
                    "strength": 0.85,
                    "image_size": {"width": 768, "height": 1024}
                }
            )
            
            result = handler.get()
            logger.info(f"Generated {len(result.get('images', []))} card images successfully")
            
            return GeneratedImageResult(
                images=result.get('images', []),
                success=True,
                message=f"Generated {len(result.get('images', []))} card images"
            )
            
        except Exception as e:
            logger.error(f"Card image generation failed: {e}")
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