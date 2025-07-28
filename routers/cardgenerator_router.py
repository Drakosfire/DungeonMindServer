from fastapi import APIRouter, Depends, HTTPException, Request, File, UploadFile, Form, Query
import os
import io
import json
import fal_client
import requests
from PIL import Image
from pydantic import BaseModel, Field, ValidationError
import firestore.firestore_utils as firestore_utils
from google.cloud import firestore
import logging
from datetime import datetime
from cloudflare.handle_images import upload_image_to_cloudflare
from cloudflareR2.cloudflareR2_utils import upload_temp_file_and_get_url
from typing import List, Tuple, Optional, Dict, Any

from openai import OpenAI
from cardgenerator.prompts import prompt_instructions
from cardgenerator.card_generator import render_text_on_card
from .auth_router import get_current_user

# Cloudflare credentials
cloudflare_account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
cloudflare_api_token = os.environ.get('CLOUDFLARE_IMAGES_API_TOKEN')

# Define the request models
class DescriptionRequest(BaseModel):
    user_input: str

class GenerateImageRequest(BaseModel):
    sd_prompt: str

class SaveJsonRequest(BaseModel):
    filename: str
    jsonData: dict

class ImageUploadRequest(BaseModel):
    image_url: str

# Define Pydantic models for structured output
class ItemProperties(BaseModel):
    Name: str
    Type: str
    Rarity: str
    Value: str
    Properties: List[str]
    Damage: Tuple[str, str]  # Changed to match frontend format
    Weight: str
    Description: str
    Quote: str
    SD_Prompt: str  # Changed to match frontend 'SD Prompt'

# Define the request model for rendering card text
class RenderCardRequest(BaseModel):
    image_url: str
    item_details: dict
    
# Pydantic models for Firestore card sessions

class SelectedAssets(BaseModel):
    finalImage: Optional[str] = None
    border: Optional[str] = None
    seedImage: Optional[str] = None
    templateBlob: Optional[str] = None
    # Step 3: Border generation card images
    generatedCardImages: List[str] = []
    selectedGeneratedCardImage: Optional[str] = None
    # Step 5: Final card with text
    finalCardWithText: Optional[str] = None

class GeneratedContent(BaseModel):
    images: List[Dict[str, Any]] = []
    renderedCards: List[Dict[str, Any]] = []
    analyses: List[Dict[str, Any]] = []

class SessionMetadata(BaseModel):
    lastSaved: Optional[str] = None
    version: Optional[str] = None
    platform: Optional[str] = None

class CardSessionData(BaseModel):
    sessionId: str
    userId: Optional[str] = None  # Optional for anonymous users
    currentStep: str
    stepCompletion: Dict[str, bool] = {}
    itemDetails: Dict[str, Any] = {}
    selectedAssets: SelectedAssets = SelectedAssets()
    generatedContent: GeneratedContent = GeneratedContent()
    metadata: SessionMetadata = SessionMetadata()

class SaveCardSessionRequest(BaseModel):
    sessionData: CardSessionData
    cardName: Optional[str] = None  # null for auto-saves
    isAutoSave: bool = True

class LoadCardSessionRequest(BaseModel):
    sessionId: Optional[str] = None  # null loads most recent
    userId: Optional[str] = None     # for authenticated users

# Project Management Models
class ProjectMetadata(BaseModel):
    version: str = "1.0.0"
    tags: List[str] = []
    isTemplate: bool = False
    lastOpened: Optional[int] = None
    cardCount: int = 0

class CreateProjectRequest(BaseModel):
    name: str
    description: Optional[str] = None
    templateId: Optional[str] = None

class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    state: Optional[CardSessionData] = None
    metadata: Optional[ProjectMetadata] = None

class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    createdAt: int
    updatedAt: int
    userId: str
    state: CardSessionData
    metadata: ProjectMetadata

class ProjectSummaryResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    updatedAt: int
    cardCount: int
    previewImage: Optional[str] = None

class ProjectListResponse(BaseModel):
    projects: List[ProjectSummaryResponse]
    total: int

router = APIRouter()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
def preview_and_generate_image(sd_prompt, num_images, url):   
    prompt = f"blank card, no text, blank textbox at top for title, mid for details and bottom for description, detailed high quality thematic borders, {sd_prompt} in on a background of appropriate setting or location"

    handler = fal_client.submit(
            "fal-ai/flux-lora/image-to-image",
            arguments={
                "num_inference_steps": 35,
                "prompt": prompt,
                "num_images": num_images,
                "image_url": url,
                "strength": 0.85,
                "image_size": {
                    "width": 768,
                    "height": 1024
                }   
            }
        )

    result = handler.get()
    logger.info(f"Type of result: {type(result)}")
    logger.info(f"Content of result: {json.dumps(result, indent=2)}")
    
    # Extract the image URLs from the result
    image_urls = [img['url'] for img in result.get('images', [])]
    
    logger.info(f"Extracted image URLs: {image_urls}")
    
    if not image_urls:
        logger.warning("No images were generated.")
        return []
    return result

@router.post('/generate-card-images')
async def generate_card_images(
    template: UploadFile = File(...),
    sdPrompt: str = Form(...),
    numImages: int = Form(...)
):
    try:
        # 1. Upload template to Cloudflare
        template_url = await upload_image_to_cloudflare(template)
        
        # 2. Generate images using the template and SD prompt                        
        image_urls = preview_and_generate_image(sdPrompt, numImages, template_url)      
        
        return image_urls
    except Exception as e:
        logger.error("Error generating images: %s", str(e))
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post('/upload-image')
async def upload_image(file: UploadFile = File(...)):  # Note the File(...) specification
    url = await upload_image_to_cloudflare(file)
    print("url:", url)
    return {"url": url}


client = OpenAI()

# Define the JSON schema
ITEM_SCHEMA = {
    "name": "item",
    "schema": {
    "type": "object",
    "properties": {
        "Name": {
            "type": "string",
            "description": "The name of the magical item."
        },
        "Type": {
            "type": "string",
            "description": "The type or category of the magical item."
        },
        "Rarity": {
            "type": "string",
            "description": "The rarity classification of the item.",
            "enum": [
                "Common",
                "Uncommon",
                "Rare",
                "Very Rare",
                "Legendary"
            ]
        },
        "Value": {
            "type": "string",
            "description": "The monetary value of the item."
        },
        "Properties": {
            "type": "array",
            "description": "Unique properties or abilities of the magical item.",
            "items": {
                "type": "string"
            }
        },
        "Damage Formula": {
            "type": "string",
            "description": "The formula used to calculate the damage of the item."
        },
        "Damage Type": {
            "type": "string",
            "description": "The type of damage the item inflicts."
        },
        "Weight": {
            "type": "string",
            "description": "The weight of the item."
        },
        "Description": {
            "type": "string",
            "description": "A detailed description of the item, including its design and features."
        },
        "Quote": {
            "type": "string",
            "description": "A memorable quote associated with the item."
        },
        "SD Prompt": {
            "type": "string",
            "description": "A description used for visual or artistic representation of the item."
        }
    },
    "required": [
        "Name",
        "Type",
        "Rarity",
        "Value",
        "Properties",
        "Weight",
        "Description",
        "Quote",
        "SD Prompt"
    ],
        "additionalProperties": False
    }
}

@router.post('/generate-item-dict')
async def generate_item_dict(user_idea: dict):
    try:
        # Construct the prompt from user input
        prompt = f"{user_idea['userIdea']}"
        
        # Make the API call
        response = client.beta.chat.completions.parse(
            model="gpt-4o",  # Ensure the model is supported
            messages=[
                {
                    "role": "system",
                    "content": f"{prompt_instructions}"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            response_format={
                "type": "json_schema",
                "json_schema": ITEM_SCHEMA,  # Ensure ITEM_SCHEMA is correctly defined
            }
        )
        
        # Log the full response for debugging
        logging.debug(f"Full response: {response}")
        
        # Safely extract and parse the structured data
        parsed_data = response.choices[0].message.parsed if response.choices else None
        if not parsed_data:
            print("Parsed data is missing from the response trying content.")
            parsed_data = response.choices[0].message.content
            print(parsed_data)
            

        # Test if parsed data is a string and jsonify it
        if isinstance(parsed_data, str):
            parsed_data = json.loads(parsed_data)
        
        # Handle OpenAI wrapping response in extra structure
        if "properties" in parsed_data and isinstance(parsed_data["properties"], dict):
            parsed_data = parsed_data["properties"]
        
        # Ensure the parsed data contains the required fields
        if "Name" not in parsed_data:
            raise ValueError("Parsed data does not contain the 'Name' field.")
        
        # Format the structured response for the frontend
        formatted_response = {parsed_data["Name"]: parsed_data}
        
        # Return the structured item data
        return formatted_response

    except Exception as e:
        # Log detailed error for debugging
        logging.error(f"Error generating item dictionary: {str(e)}", exc_info=True)
        
        # Raise an HTTP exception with details
        raise HTTPException(status_code=500, detail=f"Failed to generate item: {str(e)}")
    
@router.post('/render-card-text')
async def render_card_text(request: RenderCardRequest):
    # Open the recieved PIL image object
    image_object = render_text_on_card(request.image_url, request.item_details) 
    print("type of image_object:", type(image_object))
    # Save the image to a temporary file
    temp_file_path = f"temp_card_{request.item_details['Name']}.png"
    image_object.save(temp_file_path)
    # Check for temp file
    if not os.path.exists(temp_file_path):
        raise HTTPException(status_code=500, detail="Failed to save image to temporary file")
    # Upload the image to Cloudflare and await the response
    url = await upload_temp_file_and_get_url(temp_file_path)
    # Delete the temporary file
    os.remove(temp_file_path)

    # Format the structured response for the frontend
    formatted_response = {"url": url}

    return formatted_response

# New endpoint for direct text-to-image generation (Step 2)
@router.post('/generate-core-images')
async def generate_core_images(
    sdPrompt: str = Form(...),
    numImages: int = Form(default=4)
):
    """
    Generate core images directly from text prompt without requiring a template.
    This is used in Step 2 of the new workflow.
    """
    try:
       
        handler = fal_client.submit(
            "fal-ai/imagen4/preview/fast", 
            arguments={
                "prompt": sdPrompt,
                "num_inference_steps": 28,
                "guidance_scale": 3.5,
                "num_images": numImages,
                "image_size": {
                    "width": 1024,
                    "height": 1024
                }
            }
        )
        
        result = handler.get()
        logger.info(f"Generated core images result: {json.dumps(result, indent=2)}")
        
        return result
        
    except Exception as e:
        logger.error("Error generating core images: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to generate images: {str(e)}")

# Endpoint to get example/sample images for Step 2
@router.get('/example-images')
async def get_example_images():
    """
    Return a curated list of example images for Step 2.
    These serve as starting points or inspiration for users.
    """
    # Real example images from your Cloudflare repository
    example_image_urls = [
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/a2f5fcea-1b16-4dc7-1874-3688bf66f900/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/6f37d2ce-74aa-4d4f-c8fd-d2145f6bc700/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/8829b2aa-834b-48c2-c4bb-7f4907ced200/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/f10cbb4f-a00b-480f-38ca-1e3d816c5700/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/29dfd4d3-176e-41d4-d69d-36f3d98e6600/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/d8bf9bf2-6a6a-4451-5ff6-01bd7e36e200/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/ae6cb0e0-d91f-428c-7632-c3f1dea26b00/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/aeb68105-04fe-42ec-df9d-e232b29d0400/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/3df60f6d-9bc9-40de-a028-169d64319400/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/47f79b37-f43a-419f-99d6-5f8f60ba4100/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/6184f9fd-2374-48ec-0bc8-3da2559d8300/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/567b2937-956f-4d74-7321-55f7640b3e00/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/a6d03d18-4202-4e69-4a2d-7c948caa9000/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/7b479f54-94e3-40b5-c214-5de7d56f4a00/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/56ce102c-6186-46ad-594a-5861d69e6500/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/907fde65-9de0-4f77-e370-f80b37818800/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/211b4598-e29a-4947-0b30-6355ca45ea00/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/271b4e40-1a5f-49fc-eeb3-bfe26be80700/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/1d0d09c9-56ae-4323-b8b7-57e60b697d00/public"
    ]
    
    # Create example image objects with metadata
    example_items = [
        {"name": "Mystical Sword", "category": "Weapon", "description": "An enchanted blade radiating magical energy"},
        {"name": "Crystal Orb", "category": "Mystical", "description": "A glowing sphere of arcane power"},
        {"name": "Ancient Tome", "category": "Scroll", "description": "A weathered spellbook filled with secrets"},
        {"name": "Healing Elixir", "category": "Potion", "description": "A shimmering red potion of restoration"},
        {"name": "Dragon Scale", "category": "Material", "description": "A protective scale from an ancient wyrm"},
        {"name": "Runic Dagger", "category": "Weapon", "description": "A ceremonial blade inscribed with runes"},
        {"name": "Magic Amulet", "category": "Accessory", "description": "A pendant crackling with magical energy"},
        {"name": "Wizard Staff", "category": "Weapon", "description": "An ornate staff topped with a crystal"},
        {"name": "Golden Chalice", "category": "Treasure", "description": "An ornate cup of immense value"},
        {"name": "Fire Gem", "category": "Material", "description": "A gem containing elemental fire"},
        {"name": "Battle Axe", "category": "Weapon", "description": "A mighty weapon forged for combat"},
        {"name": "Spell Scroll", "category": "Scroll", "description": "Ancient parchment containing powerful magic"},
        {"name": "Shield of Valor", "category": "Armor", "description": "A protective barrier imbued with courage"},
        {"name": "Mystic Ring", "category": "Accessory", "description": "A band of power worn by ancient mages"},
        {"name": "Enchanted Bow", "category": "Weapon", "description": "A ranged weapon blessed by the forest"},
        {"name": "Crown of Kings", "category": "Treasure", "description": "Royal headwear of legendary rulers"},
        {"name": "Void Crystal", "category": "Material", "description": "A dark gem from beyond the veil"},
        {"name": "War Hammer", "category": "Weapon", "description": "A crushing weapon of divine might"},
        {"name": "Cloak of Shadows", "category": "Armor", "description": "Fabric that bends light and shadow"}
    ]
    
    example_images = []
    
    # Combine URLs with metadata
    for i, url in enumerate(example_image_urls[:len(example_items)]):
        if i < len(example_items):
            example_images.append({
                "url": url,
                "name": example_items[i]["name"],
                "category": example_items[i]["category"],
                "description": example_items[i]["description"]
            })
    
    return {"examples": example_images}

# Endpoint to get border options for Step 3
@router.get('/border-options')
async def get_border_options():
    """
    Return a curated list of border options for Step 3.
    These are the available border styles for card frames.
    """
    # Real border images from your Cloudflare repository
    border_urls = [
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/90293844-4eec-438f-2ea1-c89d9cb84700/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/54d94248-e737-452c-bffd-2d425f803000/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/d0872a5e-91a0-41f8-f819-3d1a0931c900/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/8c113608-2389-4588-2090-d0192c539b00/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/e6253513-b33d-4d9c-1631-38cc46199d00/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/879e240e-4491-42de-8729-5f8899841e00/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/56e91eca-d530-483f-4b62-277486097200/public",
        "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/5fdfd8cd-51c3-4dde-2d3f-f1b463f05200/public"
    ]
    
    # Border style metadata
    border_styles = [
        {"name": "Onyx Shadow", "style": "Dark", "description": "Deep black borders with shadowed edges"},
        {"name": "Flaming Copper", "style": "Fire", "description": "Warm copper tones with flame motifs"},
        {"name": "Sandstone Classic", "style": "Earth", "description": "Natural stone texture with carved details"},
        {"name": "Emerald Intricate", "style": "Nature", "description": "Green borders with leaf and vine patterns"},
        {"name": "Sapphire Ink", "style": "Water", "description": "Blue borders with flowing water designs"},
        {"name": "Crystal Teal", "style": "Ice", "description": "Cool crystalline patterns in teal"},
        {"name": "Royal Gold", "style": "Luxury", "description": "Ornate golden borders fit for royalty"},
        {"name": "Mystic Silver", "style": "Arcane", "description": "Silver borders with magical rune accents"}
    ]
    
    border_options = []
    
    # Combine URLs with metadata
    for i, url in enumerate(border_urls[:len(border_styles)]):
        if i < len(border_styles):
            border_options.append({
                "id": f"border_{i+1}",
                "url": url,
                "name": border_styles[i]["name"],
                "style": border_styles[i]["style"],
                "description": border_styles[i]["description"]
            })
    
    return {"borders": border_options}

# New endpoint to upload generated images to Cloudflare for permanent storage
@router.post('/upload-generated-images')
async def upload_generated_images(image_urls: List[str]):
    """
    Upload a list of temporary image URLs to Cloudflare for permanent storage.
    Returns the permanent Cloudflare URLs.
    """
    try:
        permanent_urls = []
        
        for url in image_urls:
            try:
                # Upload each image URL to Cloudflare
                permanent_url = await upload_image_to_cloudflare(url)
                permanent_urls.append({
                    "original_url": url,
                    "permanent_url": permanent_url,
                    "id": f"uploaded-{len(permanent_urls)}"
                })
                logger.info(f"Uploaded image to Cloudflare: {url} -> {permanent_url}")
            except Exception as e:
                logger.error(f"Failed to upload image {url}: {str(e)}")
                # Continue with other images even if one fails
                permanent_urls.append({
                    "original_url": url,
                    "permanent_url": url,  # Fallback to original URL
                    "id": f"uploaded-{len(permanent_urls)}",
                    "error": str(e)
                })
        
        return {"uploaded_images": permanent_urls}
        
    except Exception as e:
        logger.error("Error uploading images to Cloudflare: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to upload images: {str(e)}")

# Firestore Card Session Management
@router.post('/save-card-session')
async def save_card_session(request: SaveCardSessionRequest):
    """
    Save card generator session to Firestore.
    Supports both auto-saves and manual saves with names.
    """
    try:
        # Enhanced logging for debugging
        logger.info("="*60)
        logger.info("SAVE CARD SESSION REQUEST RECEIVED")
        logger.info("="*60)
        
        # Log raw request data
        request_dict = request.dict()
        logger.info(f"Request structure: {json.dumps(request_dict, indent=2, default=str)}")
        
        # Log specific validation-relevant fields
        session_data = request.sessionData.dict()
        logger.info(f"Session ID: {session_data.get('sessionId')}")
        logger.info(f"User ID: {session_data.get('userId')}")
        logger.info(f"Current Step: {session_data.get('currentStep')}")
        logger.info(f"Card Name: {request.cardName}")
        logger.info(f"Is Auto Save: {request.isAutoSave}")
        logger.info(f"Has Item Details: {bool(session_data.get('itemDetails'))}")
        logger.info(f"Has Selected Assets: {bool(session_data.get('selectedAssets'))}")
        logger.info(f"Has Generated Content: {bool(session_data.get('generatedContent'))}")
        
        session_id = session_data['sessionId']
        
        # Add metadata
        session_data['created_at'] = firestore.SERVER_TIMESTAMP
        session_data['updated_at'] = firestore.SERVER_TIMESTAMP
        session_data['cardName'] = request.cardName
        session_data['isAutoSave'] = request.isAutoSave
        
        # Use sessionId as document ID for easy retrieval
        firestore_utils.add_document('card_sessions', session_id, session_data)
        
        logger.info(f"Successfully saved card session: {session_id} (auto_save: {request.isAutoSave})")
        logger.info("="*60)
        
        return {
            "success": True,
            "sessionId": session_id,
            "message": "Session saved successfully"
        }
        
    except ValidationError as ve:
        logger.error("="*60)
        logger.error("VALIDATION ERROR IN SAVE CARD SESSION")
        logger.error("="*60)
        logger.error(f"Validation error details: {ve}")
        logger.error(f"Validation error type: {type(ve)}")
        logger.error("="*60)
        raise HTTPException(status_code=422, detail=f"Validation error: {str(ve)}")
    except Exception as e:
        logger.error("="*60)
        logger.error("GENERAL ERROR IN SAVE CARD SESSION")
        logger.error("="*60)
        logger.error(f"Error saving card session: {str(e)}")
        logger.error(f"Error type: {type(e)}")
        logger.error("="*60)
        raise HTTPException(status_code=500, detail=f"Failed to save session: {str(e)}")

@router.get('/load-card-session')
async def load_card_session(sessionId: str = None, userId: str = None):
    """
    Load card generator session from Firestore.
    If sessionId provided, loads that specific session.
    If userId provided without sessionId, loads most recent session for user.
    """
    try:
        if sessionId:
            # Load specific session
            session_data = firestore_utils.get_document('card_sessions', sessionId)
            if session_data:
                logger.info(f"Loaded card session: {sessionId}")
                return {
                    "success": True,
                    "sessionData": session_data,
                    "found": True
                }
            else:
                return {
                    "success": True,
                    "sessionData": None,
                    "found": False,
                    "message": "Session not found"
                }
        
        elif userId:
            # Load most recent session for user
            sessions = firestore_utils.query_collection('card_sessions', 'userId', '==', userId)
            if sessions:
                # Sort by updated_at and get most recent
                most_recent = max(sessions, key=lambda x: list(x.values())[0].get('updated_at', 0))
                session_data = list(most_recent.values())[0]
                session_id = list(most_recent.keys())[0]
                
                logger.info(f"Loaded most recent session for user {userId}: {session_id}")
                return {
                    "success": True,
                    "sessionData": session_data,
                    "found": True
                }
            else:
                return {
                    "success": True,
                    "sessionData": None,
                    "found": False,
                    "message": "No sessions found for user"
                }
        
        else:
            raise HTTPException(status_code=400, detail="Either sessionId or userId must be provided")
            
    except Exception as e:
        logger.error("Error loading card session: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to load session: {str(e)}")

@router.get('/list-user-sessions')
async def list_user_sessions(userId: str, includeAutoSaves: bool = False):
    """
    List all card sessions for a user.
    By default excludes auto-saves and shows only named saves.
    """
    try:
        # Query all sessions for user
        all_sessions = firestore_utils.query_collection('card_sessions', 'userId', '==', userId)
        
        auto_saves = []
        named_saves = []
        
        for session_dict in all_sessions:
            session_id = list(session_dict.keys())[0]
            session_data = list(session_dict.values())[0]
            
            session_info = {
                "sessionId": session_id,
                "cardName": session_data.get('cardName'),
                "currentStep": session_data.get('currentStep'),
                "updatedAt": session_data.get('updated_at'),
                "isAutoSave": session_data.get('isAutoSave', True)
            }
            
            if session_data.get('isAutoSave', True):
                auto_saves.append(session_info)
            else:
                named_saves.append(session_info)
        
        # Sort by updated_at (most recent first)
        auto_saves.sort(key=lambda x: x.get('updatedAt', 0), reverse=True)
        named_saves.sort(key=lambda x: x.get('updatedAt', 0), reverse=True)
        
        result = {
            "success": True,
            "namedSaves": named_saves,
            "totalNamed": len(named_saves)
        }
        
        if includeAutoSaves:
            result["autoSaves"] = auto_saves[:5]  # Only return 5 most recent auto-saves
            result["totalAutoSaves"] = len(auto_saves)
        
        logger.info(f"Listed sessions for user {userId}: {len(named_saves)} named, {len(auto_saves)} auto-saves")
        return result
        
    except Exception as e:
        logger.error("Error listing user sessions: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list sessions: {str(e)}")

@router.delete('/delete-card-session')
async def delete_card_session(sessionId: str, userId: str = None):
    """
    Delete a card session from Firestore.
    Optional userId for additional security check.
    """
    try:
        # Optional: Verify ownership before deletion
        if userId:
            session_data = firestore_utils.get_document('card_sessions', sessionId)
            if session_data and session_data.get('userId') != userId:
                raise HTTPException(status_code=403, detail="Not authorized to delete this session")
        
        firestore_utils.delete_document('card_sessions', sessionId)
        
        logger.info(f"Deleted card session: {sessionId}")
        return {
            "success": True,
            "message": "Session deleted successfully"
        }
        
    except Exception as e:
        logger.error("Error deleting card session: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete session: {str(e)}")

# Test endpoint for validating card session schema
@router.post('/validate-card-session')
async def validate_card_session(request: SaveCardSessionRequest):
    """
    Test endpoint to validate the card session schema without saving.
    Useful for debugging frontend-backend communication.
    """
    try:
        # Log the incoming request for debugging
        logger.info(f"Validation request received: {request.dict()}")
        
        # If we get here, the schema is valid
        return {
            "success": True,
            "message": "Schema validation successful",
            "receivedData": {
                "sessionId": request.sessionData.sessionId,
                "currentStep": request.sessionData.currentStep,
                "cardName": request.cardName,
                "isAutoSave": request.isAutoSave,
                "hasItemDetails": bool(request.sessionData.itemDetails),
                "hasSelectedAssets": bool(request.sessionData.selectedAssets),
                "hasGeneratedContent": bool(request.sessionData.generatedContent)
            }
        }
        
    except Exception as e:
        logger.error("Schema validation error: %s", str(e))
        raise HTTPException(status_code=422, detail=f"Schema validation failed: {str(e)}")

@router.delete('/delete-image')
async def delete_image(image_url: str = Query(..., description="URL of the image to delete")):
    """
    Delete an image from Cloudflare Images or R2 storage.
    """
    try:
        from cloudflareR2.r2_config import get_r2_client
        import re
        
        logger.info(f"Attempting to delete image: {image_url}")
        
        # Extract object key from URL
        # Handle different URL formats:
        # - https://imagedelivery.net/account/image_id/public
        # - https://bucket.r2.cloudflarestorage.com/object_key
        # - https://domain.com/cdn-cgi/image/.../object_key
        
        object_key = None
        
        # Try to extract from Cloudflare Images URL
        if 'imagedelivery.net' in image_url:
            # Extract image ID from Cloudflare Images URL
            match = re.search(r'imagedelivery\.net/[^/]+/([^/]+)/', image_url)
            if match:
                image_id = match.group(1)
                logger.info(f"Extracted Cloudflare Images ID: {image_id}")
                # For Cloudflare Images, we need to use their API to delete
                # This would require additional API setup, so for now we'll just log
                logger.warning(f"Cloudflare Images deletion not implemented for image ID: {image_id}")
                return {
                    "success": True,
                    "message": "Image deletion logged (Cloudflare Images deletion not yet implemented)"
                }
        
        # Try to extract from R2 URL
        elif 'r2.cloudflarestorage.com' in image_url or 'cdn-cgi/image' in image_url:
            # Extract object key from R2 URL
            match = re.search(r'/([^/]+/[^/]+)$', image_url)
            if match:
                object_key = match.group(1)
                logger.info(f"Extracted R2 object key: {object_key}")
            else:
                # Try alternative pattern for CDN URLs
                match = re.search(r'/([^/]+/[^/]+/[^/]+)$', image_url)
                if match:
                    object_key = match.group(1)
                    logger.info(f"Extracted R2 object key (alternative): {object_key}")
        
        if object_key:
            # Delete from R2
            r2_client = get_r2_client()
            bucket_name = 'temp-images'  # Default bucket for temporary images
            
            try:
                r2_client.delete_object(Bucket=bucket_name, Key=object_key)
                logger.info(f"Successfully deleted R2 object: {object_key}")
                return {
                    "success": True,
                    "message": f"Image deleted successfully from R2: {object_key}"
                }
            except Exception as r2_error:
                logger.error(f"Failed to delete R2 object {object_key}: {str(r2_error)}")
                return {
                    "success": False,
                    "message": f"Failed to delete from R2: {str(r2_error)}"
                }
        else:
            logger.warning(f"Could not extract object key from URL: {image_url}")
            return {
                "success": False,
                "message": "Could not determine image location for deletion"
            }
        
    except Exception as e:
        logger.error("Error deleting image: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete image: {str(e)}")

# Project Management Endpoints

@router.post('/create-project', response_model=ProjectResponse)
async def create_project(request: CreateProjectRequest, current_user=Depends(get_current_user)):
    """Create a new card project with initial state"""
    try:
        import uuid
        from datetime import datetime
        
        user_id = current_user.sub
        project_id = str(uuid.uuid4())
        current_time = int(datetime.now().timestamp() * 1000)
        
        # Create initial project state
        initial_state = CardSessionData(
            sessionId=str(uuid.uuid4()),
            userId=user_id,
            currentStep="text-generation",
            stepCompletion={},
            itemDetails={},
            selectedAssets=SelectedAssets(),
            generatedContent=GeneratedContent(),
            metadata=SessionMetadata(
                lastSaved=str(current_time),
                version="1.0.0",
                platform="web"
            )
        )
        
        # Create project metadata
        project_metadata = ProjectMetadata(
            version="1.0.0",
            tags=[],
            isTemplate=False,
            lastOpened=current_time,
            cardCount=0
        )
        
        # Prepare project document
        project_doc = {
            "id": project_id,
            "user_id": user_id,
            "name": request.name,
            "description": request.description,
            "created_at": current_time,
            "updated_at": current_time,
            "state": initial_state.dict(),
            "metadata": project_metadata.dict(),
            "is_template": False,
            "tags": []
        }
        
        # Save to Firestore
        firestore_utils.add_document('card_projects', project_id, project_doc)
        
        logger.info(f"Created new project: {project_id} for user: {user_id}")
        
        return ProjectResponse(
            id=project_id,
            name=request.name,
            description=request.description,
            createdAt=current_time,
            updatedAt=current_time,
            userId=user_id,
            state=initial_state,
            metadata=project_metadata
        )
        
    except Exception as e:
        logger.error("Error creating project: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create project: {str(e)}")

@router.get('/list-projects', response_model=ProjectListResponse)
async def list_projects(includeTemplates: bool = False, current_user=Depends(get_current_user)):
    """Get all projects for a user"""
    try:
        user_id = current_user.sub
        
        # Query user's projects
        projects = firestore_utils.query_collection('card_projects', 'user_id', '==', user_id)
        
        project_summaries = []
        for project_dict in projects:
            project_id = list(project_dict.keys())[0]
            project_data = list(project_dict.values())[0]
            
            # Skip templates if not requested
            if not includeTemplates and project_data.get('is_template', False):
                continue
                
            summary = ProjectSummaryResponse(
                id=project_id,
                name=project_data.get('name', 'Untitled Project'),
                description=project_data.get('description'),
                updatedAt=project_data.get('updated_at', 0),
                cardCount=project_data.get('metadata', {}).get('cardCount', 0),
                previewImage=project_data.get('preview_image')
            )
            project_summaries.append(summary)
        
        # Sort by updated date (most recent first)
        project_summaries.sort(key=lambda x: x.updatedAt, reverse=True)
        
        logger.info(f"Listed {len(project_summaries)} projects for user: {user_id}")
        logger.info(f"Projects found: {[(p.name, datetime.fromtimestamp(p.updatedAt/1000).strftime('%Y-%m-%d %H:%M:%S')) for p in project_summaries]}")
        
        return ProjectListResponse(
            projects=project_summaries,
            total=len(project_summaries)
        )
        
    except Exception as e:
        logger.error("Error listing projects: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list projects: {str(e)}")

@router.get('/project/{project_id}', response_model=ProjectResponse)
async def get_project(project_id: str, current_user=Depends(get_current_user)):
    """Get full project data by ID"""
    try:
        from datetime import datetime
        
        user_id = current_user.sub
        
        # Get project from Firestore
        project_data = firestore_utils.get_document('card_projects', project_id)
        
        if not project_data:
            raise HTTPException(status_code=404, detail="Project not found")
            
        # Verify ownership
        if project_data.get('user_id') != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to access this project")
        
        # Update last opened timestamp
        current_time = int(datetime.now().timestamp() * 1000)
        project_data['metadata']['lastOpened'] = current_time
        project_data['updated_at'] = current_time
        
        firestore_utils.update_document('card_projects', project_id, {
            'metadata.lastOpened': current_time,
            'updated_at': current_time
        })
        
        # Convert to response model
        response = ProjectResponse(
            id=project_id,
            name=project_data.get('name', 'Untitled Project'),
            description=project_data.get('description'),
            createdAt=project_data.get('created_at', 0),
            updatedAt=project_data.get('updated_at', 0),
            userId=project_data.get('user_id', ''),
            state=CardSessionData(**project_data.get('state', {})),
            metadata=ProjectMetadata(**project_data.get('metadata', {}))
        )
        
        logger.info(f"Retrieved project: {project_id} for user: {user_id}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting project: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get project: {str(e)}")

@router.put('/project/{project_id}')
async def update_project(project_id: str, request: UpdateProjectRequest, current_user=Depends(get_current_user)):
    """Update project metadata and state"""
    try:
        from datetime import datetime
        
        user_id = current_user.sub
        
        # Debug logging
        logger.info(f"Update request for project {project_id}: name='{request.name}', has_state={request.state is not None}")
        
        # Verify project exists and user owns it
        project_data = firestore_utils.get_document('card_projects', project_id)
        
        if not project_data:
            raise HTTPException(status_code=404, detail="Project not found")
            
        if project_data.get('user_id') != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to update this project")
        
        # Prepare update data
        current_time = int(datetime.now().timestamp() * 1000)
        update_data = {
            'updated_at': current_time
        }
        
        if request.name is not None:
            update_data['name'] = request.name
            
        if request.description is not None:
            update_data['description'] = request.description
            
        if request.state is not None:
            update_data['state'] = request.state.dict()
            
        if request.metadata is not None:
            update_data['metadata'] = request.metadata.dict()
        
        # Update in Firestore
        firestore_utils.update_document('card_projects', project_id, update_data)
        
        logger.info(f"Updated project: {project_id} for user: {user_id} with data: {update_data}")
        
        return {
            "success": True,
            "message": "Project updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating project: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update project: {str(e)}")

@router.delete('/project/{project_id}')
async def delete_project(project_id: str, current_user=Depends(get_current_user)):
    """Delete project and associated resources"""
    try:
        user_id = current_user.sub
        
        # Verify project exists and user owns it
        project_data = firestore_utils.get_document('card_projects', project_id)
        
        if not project_data:
            raise HTTPException(status_code=404, detail="Project not found")
            
        if project_data.get('user_id') != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this project")
        
        # Delete associated card sessions
        sessions = firestore_utils.query_collection('card_sessions', 'project_id', '==', project_id)
        for session_dict in sessions:
            session_id = list(session_dict.keys())[0]
            firestore_utils.delete_document('card_sessions', session_id)
        
        # Delete the project
        firestore_utils.delete_document('card_projects', project_id)
        
        logger.info(f"Deleted project: {project_id} for user: {user_id}")
        
        return {
            "success": True,
            "message": "Project deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting project: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {str(e)}")

@router.post('/project/{project_id}/duplicate', response_model=ProjectResponse)
async def duplicate_project(project_id: str, new_name: str, current_user=Depends(get_current_user)):
    """Create a copy of an existing project"""
    try:
        import uuid
        from datetime import datetime
        
        user_id = current_user.sub
        
        # Get original project
        original_project = firestore_utils.get_document('card_projects', project_id)
        
        if not original_project:
            raise HTTPException(status_code=404, detail="Project not found")
            
        if original_project.get('user_id') != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to duplicate this project")
        
        # Create new project ID and timestamps
        new_project_id = str(uuid.uuid4())
        current_time = int(datetime.now().timestamp() * 1000)
        
        # Create duplicate project data
        duplicate_project = {
            "id": new_project_id,
            "user_id": user_id,
            "name": new_name,
            "description": f"Copy of {original_project.get('name', 'Untitled Project')}",
            "created_at": current_time,
            "updated_at": current_time,
            "state": original_project.get('state', {}),
            "metadata": {
                **original_project.get('metadata', {}),
                "lastOpened": current_time,
                "cardCount": 0  # Reset card count for new project
            },
            "is_template": False,
            "tags": original_project.get('tags', [])
        }
        
        # Generate new session ID for the duplicated state
        if 'state' in duplicate_project and 'sessionId' in duplicate_project['state']:
            duplicate_project['state']['sessionId'] = str(uuid.uuid4())
        
        # Save duplicate to Firestore
        firestore_utils.add_document('card_projects', new_project_id, duplicate_project)
        
        logger.info(f"Duplicated project: {project_id} to {new_project_id} for user: {user_id}")
        
        return ProjectResponse(
            id=new_project_id,
            name=new_name,
            description=duplicate_project['description'],
            createdAt=current_time,
            updatedAt=current_time,
            userId=user_id,
            state=CardSessionData(**duplicate_project['state']),
            metadata=ProjectMetadata(**duplicate_project['metadata'])
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error duplicating project: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to duplicate project: {str(e)}")

