"""
Text processing and rendering for card generation
"""
import logging
from typing import Dict, Any, List, Tuple
from PIL import Image
from ..config.layout_config import CARD_LAYOUT
from ..utils.error_handler import TextRenderingError
import cardgenerator.render_card_text as rend

logger = logging.getLogger(__name__)

class TextElement:
    """Represents a text element to be rendered on the card"""
    
    def __init__(self, content: str, area_config: Dict[str, Any], font_path: str):
        self.content = content
        self.area_config = area_config
        self.font_path = font_path
        
    @property
    def position(self) -> Tuple[int, int]:
        """Get the position for this text element"""
        return (self.area_config['x'], self.area_config['y'])
    
    @property
    def dimensions(self) -> Tuple[int, int]:
        """Get the width and height for this text element"""
        return (self.area_config['width'], self.area_config['height'])
    
    @property
    def font_size(self) -> int:
        """Get the initial font size for this text element"""
        return self.area_config.get('font_size', 50)
    
    @property
    def is_multiline(self) -> bool:
        """Check if this text element supports multiple lines"""
        return self.area_config.get('multiline', False)
    
    @property
    def is_italic(self) -> bool:
        """Check if this text element should use italic font"""
        return self.area_config.get('style') == 'italic'
    
    @property
    def is_quote(self) -> bool:
        """Check if this text element is a quote (for special formatting)"""
        return self.area_config.get('style') == 'italic'

class TextProcessor:
    """Handles text processing and rendering for cards"""
    
    def __init__(self):
        self.layout = CARD_LAYOUT
        self.fonts = self.layout['fonts']
        logger.info("TextProcessor initialized with layout configuration")
    
    def prepare_text_elements(self, item_details: Dict[str, Any]) -> List[TextElement]:
        """
        Prepare text elements from item details based on layout configuration
        
        Args:
            item_details: Dictionary containing item information
            
        Returns:
            List of TextElement objects ready for rendering
        """
        elements = []
        text_areas = self.layout['text_areas']
        
        try:
            # Helper function to get field value with case-insensitive fallback
            def get_field_value(field_name: str) -> str:
                """Get field value with case-insensitive fallback"""
                # Try uppercase first (backend convention)
                if field_name.upper() in item_details:
                    return item_details[field_name.upper()]
                # Try lowercase (frontend convention)
                elif field_name.lower() in item_details:
                    return item_details[field_name.lower()]
                # Try title case
                elif field_name.title() in item_details:
                    return item_details[field_name.title()]
                else:
                    return ""
            
            # Title element
            if 'title' in text_areas:
                name_value = get_field_value('Name')
                if name_value:
                    font_path = self.fonts['regular']
                    elements.append(TextElement(
                        content=name_value,
                        area_config=text_areas['title'],
                        font_path=font_path
                    ))
            
            # Type element (combine Type, Weight, and Damage Formula if present)
            if 'type' in text_areas:
                type_text = get_field_value('Type')
                
                # Add weight if present
                weight_value = get_field_value('Weight')
                if weight_value:
                    type_text += f" {weight_value}"
                
                # Add damage formula if present
                damage_value = get_field_value('Damage Formula')
                if not damage_value:
                    # Try alternative field names
                    damage_value = get_field_value('Damage')
                if damage_value:
                    type_text += f" {damage_value}"
                
                if type_text:
                    font_path = self.fonts['regular']
                    elements.append(TextElement(
                        content=type_text,
                        area_config=text_areas['type'],
                        font_path=font_path
                    ))
            
            # Description element (combine Description and Properties)
            if 'description' in text_areas:
                description_text = get_field_value('Description')
                
                # Add properties if present
                properties = item_details.get('Properties') or item_details.get('properties')
                if properties and isinstance(properties, list):
                    properties_text = '\n'.join(properties)
                    if properties_text:
                        description_text += f"\n\n{properties_text}"
                
                if description_text:
                    font_path = self.fonts['regular']
                    elements.append(TextElement(
                        content=description_text,
                        area_config=text_areas['description'],
                        font_path=font_path
                    ))
            
            # Value element
            if 'value' in text_areas:
                value_text = get_field_value('Value')
                if value_text:
                    font_path = self.fonts['regular']
                    elements.append(TextElement(
                        content=value_text,
                        area_config=text_areas['value'],
                        font_path=font_path
                    ))
                    logger.info(f"✅ Value element added: '{value_text}' at position {text_areas['value']['x']}, {text_areas['value']['y']}")
                else:
                    logger.warning(f"⚠️ Value field is empty or not found in item_details")
            
            # Quote element (italic font)
            if 'quote' in text_areas:
                quote_text = get_field_value('Quote')
                if quote_text:
                    font_path = self.fonts['italic']
                    elements.append(TextElement(
                        content=quote_text,
                        area_config=text_areas['quote'],
                        font_path=font_path
                    ))
            
            logger.info(f"Prepared {len(elements)} text elements for rendering")
            return elements
            
        except KeyError as e:
            raise TextRenderingError(f"Missing required field in item_details: {e}")
        except Exception as e:
            raise TextRenderingError(f"Error preparing text elements: {e}")
    
    async def render_text(self, image: Image.Image, text_elements: List[TextElement]) -> Image.Image:
        """
        Render all text elements onto the image
        
        Args:
            image: PIL Image to render text onto
            text_elements: List of TextElement objects to render
            
        Returns:
            Image with text rendered
            
        Raises:
            TextRenderingError: If text rendering fails
        """
        try:
            logger.info(f"Rendering {len(text_elements)} text elements onto image")
            
            for element in text_elements:
                logger.debug(f"🎨 Rendering text element: '{element.content[:50]}...' at {element.position}")
                
                # Determine rendering parameters based on element type
                is_description = element.is_multiline
                is_quote = element.is_quote
                
                # Use the existing render_text_with_dynamic_spacing function
                image = rend.render_text_with_dynamic_spacing(
                    image=image,
                    text=element.content,
                    center_position=element.position,
                    max_width=element.dimensions[0],
                    area_height=element.dimensions[1],
                    font_path=element.font_path,
                    initial_font_size=element.font_size,
                    description=is_description,
                    quote=is_quote
                )
            
            logger.info("Successfully rendered all text elements")
            return image
            
        except Exception as e:
            raise TextRenderingError(f"Failed to render text on image: {e}")
    
    def get_text_area_config(self, area_name: str) -> Dict[str, Any]:
        """
        Get configuration for a specific text area
        
        Args:
            area_name: Name of the text area
            
        Returns:
            Configuration dictionary for the text area
        """
        return self.layout['text_areas'].get(area_name, {})