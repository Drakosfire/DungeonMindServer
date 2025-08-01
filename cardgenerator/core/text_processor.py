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
            # Title element
            if 'title' in text_areas and 'Name' in item_details:
                font_path = self.fonts['regular']
                elements.append(TextElement(
                    content=item_details['Name'],
                    area_config=text_areas['title'],
                    font_path=font_path
                ))
            
            # Type element (combine Type, Weight, and Damage Formula if present)
            if 'type' in text_areas and 'Type' in item_details:
                type_text = item_details['Type']
                
                # Add weight if present
                if item_details.get('Weight'):
                    type_text += f" {item_details['Weight']}"
                
                # Add damage formula if present
                if item_details.get('Damage Formula'):
                    type_text += f" {item_details['Damage Formula']}"
                
                font_path = self.fonts['regular']
                elements.append(TextElement(
                    content=type_text,
                    area_config=text_areas['type'],
                    font_path=font_path
                ))
            
            # Description element (combine Description and Properties)
            if 'description' in text_areas and 'Description' in item_details:
                description_text = item_details['Description']
                
                # Add properties if present
                if item_details.get('Properties') and isinstance(item_details['Properties'], list):
                    properties_text = '\n'.join(item_details['Properties'])
                    if properties_text:
                        description_text += f"\n\n{properties_text}"
                
                font_path = self.fonts['regular']
                elements.append(TextElement(
                    content=description_text,
                    area_config=text_areas['description'],
                    font_path=font_path
                ))
            
            # Value element
            if 'value' in text_areas and 'Value' in item_details:
                font_path = self.fonts['regular']
                elements.append(TextElement(
                    content=item_details['Value'],
                    area_config=text_areas['value'],
                    font_path=font_path
                ))
            
            # Quote element (italic font)
            if 'quote' in text_areas and 'Quote' in item_details:
                font_path = self.fonts['italic']
                elements.append(TextElement(
                    content=item_details['Quote'],
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
                logger.debug(f"Rendering text: '{element.content[:50]}...' at {element.position}")
                
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