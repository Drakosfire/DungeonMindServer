# LEGACY COMPATIBILITY LAYER
# This file now redirects to the new modular pipeline for compatibility
# The new pipeline is in card_generator_new.py with improved architecture

import asyncio
import logging
from typing import Dict, Any
from PIL import Image

logger = logging.getLogger(__name__)

# Import the new pipeline
try:
    from .card_generator_new import render_text_on_card as async_render_text_on_card
    NEW_PIPELINE_AVAILABLE = True
    logger.info("✅ New modular pipeline available, using improved architecture")
except ImportError as e:
    NEW_PIPELINE_AVAILABLE = False
    logger.warning(f"⚠️ New pipeline not available, falling back to legacy: {e}")

import cardgenerator.render_card_text as rend
from PIL import Image, ImageFilter
import ast
import requests
from io import BytesIO
from urllib.request import urlopen
import urllib.request
from urllib.parse import urlparse
import os


def open_image_from_url(url):
    try:
        print(f"Opening image from URL: {url}")
        response = requests.get(url)
        response.raise_for_status()

        # Skip MIME type check for Gradio-generated URLs
        if url.startswith("http://127.0.0.1:7860/gradio_api/file="):
            print("Gradio internal URL detected; skipping MIME type check.")
        elif 'image' not in response.headers.get('content-type', ''):
            raise ValueError("URL does not point to an image")

        image_data = BytesIO(response.content)
        image = Image.open(image_data)
        return image
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        raise
    except ValueError as e:
        print(f"Invalid image URL: {e}")
        raise
    except Image.UnidentifiedImageError as e:
        print(f"Cannot identify image file: {e}")
        raise


# Import Inventory 
#shop_inventory = inv.inventory
#purchased_item_key = shop_inventory['Shortsword']
#border_path = './card_templates/Shining Sunset Border.png'
base_path = "https://media.githubusercontent.com/media/Drakosfire/CardGenerator/main/card_parts/"
value_overlay_path = f"{base_path}Value_box_transparent.png"
test_item = {'Name': 'Pustulent Raspberry', 'Type': 'Fruit', 'Value': '1 cp', 'Properties': ['Unusual Appearance', 'Rare Taste'], 'Weight': '0.2 lb', 'Description': 'This small fruit has a pustulent appearance, with bumps and irregular shapes covering its surface. Its vibrant colors and strange texture make it an oddity among other fruits.', 'Quote': 'A fruit that defies expectations, as sweet and sour as life itself.', 'SD Prompt': 'A small fruit with vibrant colors and irregular shapes, bumps covering its surface.'}
sticker_path_dictionary = {'Default': "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/451a66ad-5116-4649-137b-aed784e5c700/public",
                            'Common': "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/8b579f17-7f92-4a0a-e891-e8990be9e400/public",
                            'Uncommon': "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/65889c14-dc2b-4b6a-9cbf-7d7704fba100/public",
                            'Rare': "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/dedf72a3-00b8-43cf-e95f-7b13b899d100/public",
                            'Very Rare':"https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/3b452c8b-e945-448a-f461-48b99c266c00/public",
                            'Legendary':"https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/2c60b814-ab4c-46ac-e479-d3a860413700/public"}


# Function that takes in an image url and a dictionary and uses the values to print onto a card.
def paste_image_and_resize(base_image, sticker_path, x_position, y_position, img_width, img_height, purchased_item_key=None):
    # Check for if item has a Rarity string that is in the dictionary of sticker paths
    if purchased_item_key:
        if sticker_path.get(purchased_item_key):
            sticker_path = sticker_path[purchased_item_key]
        else:
            sticker_path = sticker_path['Default']
    
    # Create a request with a User-Agent header
    request = urllib.request.Request(sticker_path, headers={'User-Agent': 'Mozilla/5.0'})
    
    # Load the image to paste
    image_to_paste = Image.open(urlopen(request))

    # Convert image to RGBA if not already
    if image_to_paste.mode != 'RGBA':
        image_to_paste = image_to_paste.convert('RGBA')

    # Define the new size (scale) for the image you're pasting
    new_size = (img_width, img_height)

    # Resize the image to the new size
    image_to_paste_resized = image_to_paste.resize(new_size)

    # Specify the top-left corner where the resized image will be pasted
    paste_position = (x_position, y_position)

    # Paste the resized image onto the base image
    base_image.paste(image_to_paste_resized, paste_position, image_to_paste_resized)

def render_text_on_card_legacy(image_path, item_details):
    """LEGACY FUNCTION - Use the new pipeline instead"""
    logger.warning("🚨 Using legacy render_text_on_card function. Consider migrating to new pipeline.")
    
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
    
    # Download the image from the url
    image = open_image_from_url(image_path)
    
    # Ensure the image is exactly 768x1024 to match our hardcoded text coordinates
    EXPECTED_WIDTH = 768
    EXPECTED_HEIGHT = 1024
    
    if image.size != (EXPECTED_WIDTH, EXPECTED_HEIGHT):
        print(f"Resizing image from {image.size} to ({EXPECTED_WIDTH}, {EXPECTED_HEIGHT}) for text positioning")
        image = image.resize((EXPECTED_WIDTH, EXPECTED_HEIGHT), Image.Resampling.LANCZOS)
    
    # Card Properties 
    properties = item_details.get('Properties') or item_details.get('properties') or []
    print(type(properties))
    
    item_properties = '\n'.join(properties) if properties else ""
    
    font_path = "cardgenerator/fonts/Balgruf.ttf"
    italics_font_path = "cardgenerator/fonts/BalgrufItalic.ttf"
    initial_font_size = 50

    # Title Properties (coordinates designed for 768x1024)
    title_center_position = (395, 55)
    title_area_width = 600 # Maximum width of the text box
    title_area_height = 60  # Maximum height of the text box

    # Type box properties
    type_center_position = (384, 545)
    type_area_width = 600 
    type_area_height = 45 
    type_text = get_field_value('Type')
    weight_value = get_field_value('Weight')
    if weight_value: 
        type_text = type_text + ' '+ weight_value

    damage_value = get_field_value('Damage Formula')
    if not damage_value:
        damage_value = get_field_value('Damage')
    if damage_value: 
        type_text = type_text + ' '+ damage_value

    # Description box properties
    description_position = (105, 630)
    description_area_width = 590
    description_area_height = 215

    # Value box properties (This is good, do not change unless underlying textbox layout is changing)
    value_position = (660,905)
    value_area_width = 125
    value_area_height = 50

    # Quote test properties
    quote_position = (110,885)
    quote_area_width = 470
    quote_area_height = 60                     

    # Apply background overlays first (value overlay)
    paste_image_and_resize(image, value_overlay_path,x_position= 0,y_position=0, img_width= 768, img_height= 1024)
    
    # Apply text rendering with correct coordinates
    image = rend.render_text_with_dynamic_spacing(image, get_field_value('Name'), title_center_position, title_area_width, title_area_height,font_path,initial_font_size)
    image = rend.render_text_with_dynamic_spacing(image, type_text, type_center_position, type_area_width, type_area_height,font_path,initial_font_size)
    image = rend.render_text_with_dynamic_spacing(image, get_field_value('Description') + '\n\n' + item_properties, description_position, description_area_width, description_area_height,font_path,initial_font_size, description = True)
    image = rend.render_text_with_dynamic_spacing(image, get_field_value('Value'), value_position, value_area_width, value_area_height,font_path,initial_font_size)
    image = rend.render_text_with_dynamic_spacing(image, get_field_value('Quote'), quote_position, quote_area_width, quote_area_height,italics_font_path,initial_font_size, quote = True)
    
    # Apply foreground overlays last (rarity sticker)
    paste_image_and_resize(image, sticker_path_dictionary,x_position= 0,y_position=909, img_width= 115, img_height= 115, purchased_item_key= get_field_value('Rarity'))

    # Add blur, gives it a less artificial look, put into list and return the list since gallery requires lists
    image = image.filter(ImageFilter.GaussianBlur(.5))
       
    return image

# Main function with smart routing to new pipeline
def render_text_on_card(image_path: str, item_details: Dict[str, Any]) -> Image.Image:
    """
    Smart compatibility function that routes to new pipeline when available
    
    This function maintains backward compatibility while preferring the new
    modular pipeline when available.
    """
    if NEW_PIPELINE_AVAILABLE:
        try:
            # Use new async pipeline in sync context
            logger.info("🚀 Using new modular pipeline for card rendering")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(async_render_text_on_card(image_path, item_details))
                logger.info("✅ New pipeline rendering successful")
                return result
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"❌ New pipeline failed, falling back to legacy: {e}")
            # Fall through to legacy function
    
    # Use legacy function as fallback
    logger.info("🔄 Using legacy pipeline for card rendering")
    return render_text_on_card_legacy(image_path, item_details)
    





