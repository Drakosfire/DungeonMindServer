"""
Card Generation Router

Handles all card generation endpoints including text generation, image generation,
and final card assembly with memory-only image streaming.
"""

import logging
import io
from datetime import datetime
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from session_management import get_session, session_manager
from cardgenerator.services.card_generation_service import card_generation_service
from cardgenerator.services.image_management_service import image_management_service
from cardgenerator.utils.error_handler import CardGenerationError, ImageProcessingError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cardgenerator", tags=["CardGenerator"])


class ItemGenerationRequest(BaseModel):
    """Request model for item generation"""
    userIdea: str


class RenderCardRequest(BaseModel):
    """Request model for card text rendering"""
    image_url: str
    item_details: Dict[str, Any]


@router.post('/generate-item')
async def generate_item_description(
    request: ItemGenerationRequest,
    session_data = Depends(get_session)
):
    """
    Generate item description using AI
    
    Step 1: Text generation for the card
    """
    try:
        session, session_id = session_data
        
        if not request.userIdea:
            raise HTTPException(status_code=422, detail="User idea is required")
        
        logger.info(f"Generating item description for: {request.userIdea} (session: {session_id})")
        
        # Generate item description using AI
        item_details = await card_generation_service.generate_item_description(request.userIdea)
        
        # Update session with generated item
        if session:
            cardgen_update = {
                "lastGeneratedItem": item_details,
                "lastActivity": "item_generation",
                "currentStep": "text_generation",
                "updatedAt": datetime.now()
            }
            await session_manager.update_tool_state(session_id, "cardgenerator", cardgen_update)
            
            logger.debug(f"Updated session with generated item for session {session_id}")
        
        logger.info(f"Successfully generated item description for: {request.userIdea}")
        return {
            "success": True,
            "item_details": item_details,
            "session_id": session_id
        }
        
    except CardGenerationError as e:
        logger.error(f"Item generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in item generation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post('/generate-core-images')
async def generate_core_images(
    sdPrompt: str = Form(...),
    numImages: int = Form(default=4),
    session_data = Depends(get_session)
):
    """
    Generate core images using Stable Diffusion
    
    Step 2: Image generation for the card
    """
    try:
        session, session_id = session_data
        
        if not sdPrompt:
            raise HTTPException(status_code=422, detail="Stable Diffusion prompt is required")
        
        logger.info(f"Generating {numImages} core images for prompt: {sdPrompt} (session: {session_id})")
        
        # Generate images using Stable Diffusion
        image_result = await card_generation_service.generate_core_images(sdPrompt, numImages)
        
        # Update session with generated images
        if session:
            cardgen_update = {
                "generatedImages": image_result.images,
                "lastActivity": "image_generation",
                "currentStep": "image_generation",
                "updatedAt": datetime.now()
            }
            await session_manager.update_tool_state(session_id, "cardgenerator", cardgen_update)
            
            logger.debug(f"Updated session with generated images for session {session_id}")
        
        logger.info(f"Successfully generated {len(image_result.images)} core images")
        return {
            "success": True,
            "images": image_result.images,
            "session_id": session_id
        }
        
    except CardGenerationError as e:
        logger.error(f"Core image generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in core image generation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post('/generate-card-images')
async def generate_card_images(
    template: UploadFile = File(...),
    sdPrompt: str = Form(...),
    numImages: int = Form(default=4),
    session_data = Depends(get_session)
):
    """
    Generate card images with borders and templates
    
    Step 3: Card image generation with styling
    """
    try:
        session, session_id = session_data
        
        if not template:
            raise HTTPException(status_code=422, detail="Template file is required")
        if not sdPrompt:
            raise HTTPException(status_code=422, detail="Stable Diffusion prompt is required")
        
        logger.info(f"Generating {numImages} card images with template for prompt: {sdPrompt} (session: {session_id})")
        
        # Upload template file first to get URL
        from cardgenerator.services.image_management_service import image_management_service
        template_upload_result = await image_management_service.upload_single_image(template)
        template_url = template_upload_result.url
        
        # Generate card images with template URL
        card_image_result = await card_generation_service.generate_card_images(template_url, sdPrompt, numImages)
        
        # Update session with card images
        if session:
            cardgen_update = {
                "cardImages": card_image_result.images,
                "lastActivity": "card_image_generation",
                "currentStep": "card_image_generation",
                "updatedAt": datetime.now()
            }
            await session_manager.update_tool_state(session_id, "cardgenerator", cardgen_update)
            
            logger.debug(f"Updated session with card images for session {session_id}")
        
        logger.info(f"Successfully generated {len(card_image_result.images)} card images")
        return {
            "success": True,
            "images": card_image_result.images,
            "session_id": session_id
        }
        
    except CardGenerationError as e:
        logger.error(f"Card image generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in card image generation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post('/render-text')
async def render_card_text(
    request: RenderCardRequest,
    session_data = Depends(get_session)
):
    """
    Render text on card and return the image directly from memory
    
    Final step that creates the completed card and streams it to the user
    """
    try:
        session, session_id = session_data
        
        # Validate inputs
        if not request.image_url:
            raise HTTPException(status_code=422, detail="Image URL is required")
        if not request.item_details:
            raise HTTPException(status_code=422, detail="Item details are required")
        
        item_name = request.item_details.get('Name', 'Unknown')
        logger.info(f"Rendering text for card: {item_name} (session: {session_id})")
        
        # Delegate to service layer
        image_object = await card_generation_service.render_text_on_card(
            request.image_url, request.item_details
        )
        
        # Convert image to bytes in memory
        img_buffer = io.BytesIO()
        image_object.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        # Create streaming response
        def generate_image():
            yield img_buffer.getvalue()
        
        # Update global session with completed card info (but not the actual image)
        if session:
            cardgen_update = {
                "itemDetails": request.item_details,
                "lastActivity": "card_completion",
                "currentStep": "completed",
                "completedAt": datetime.now(),
                "cardGenerated": True,
                "cardName": item_name
            }
            await session_manager.update_tool_state(session_id, "cardgenerator", cardgen_update)
            
            logger.debug(f"Updated session with completed card for {item_name}")
        
        logger.info(f"Successfully rendered card for: {item_name}")
        
        # Return streaming response with the image
        return StreamingResponse(
            generate_image(),
            media_type="image/png",
            headers={
                "Content-Disposition": f"attachment; filename=card_{item_name}.png",
                "X-Card-Name": item_name,
                "X-Session-ID": session_id
            }
        )
        
    except CardGenerationError as e:
        logger.error(f"Card rendering failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except ImageProcessingError as e:
        logger.error(f"Image processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Image processing error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in card text rendering: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post('/render-text-with-url')
async def render_card_text_with_url(
    request: RenderCardRequest,
    session_data = Depends(get_session)
):
    """
    Render text on card and upload to cloud storage, returning the URL
    
    Alternative endpoint that uploads the completed card to cloud storage
    """
    try:
        session, session_id = session_data
        
        # Validate inputs
        if not request.image_url:
            raise HTTPException(status_code=422, detail="Image URL is required")
        if not request.item_details:
            raise HTTPException(status_code=422, detail="Item details are required")
        
        item_name = request.item_details.get('Name', 'Unknown')
        logger.info(f"Rendering text for card with URL: {item_name} (session: {session_id})")
        
        # Delegate to service layer
        image_object = await card_generation_service.render_text_on_card(
            request.image_url, request.item_details
        )
        
        # Upload image object directly to cloud storage
        upload_result = await image_management_service.upload_with_memory_fallback(
            image_object, f"card_{item_name}.png"
        )
        final_card_url = upload_result.url
        
        # Update global session with completed card
        if session:
            cardgen_update = {
                "finalCardUrl": final_card_url,
                "itemDetails": request.item_details,
                "lastActivity": "card_completion",
                "currentStep": "completed",
                "completedAt": datetime.now()
            }
            await session_manager.update_tool_state(session_id, "cardgenerator", cardgen_update)
            
            logger.debug(f"Updated session with completed card for {item_name}")
        
        logger.info(f"Successfully rendered and uploaded card for: {item_name}")
        return {
            "url": final_card_url,
            "session_id": session_id,
            "item_name": item_name
        }
        
    except CardGenerationError as e:
        logger.error(f"Card rendering failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except ImageProcessingError as e:
        logger.error(f"Image processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Image processing error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in card text rendering: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get('/session-state')
async def get_cardgenerator_session_state(session_data = Depends(get_session)):
    """
    Get current CardGenerator state from global session
    
    Provides access to persisted generation progress
    """
    try:
        session, session_id = session_data
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get CardGenerator state from global session
        cardgen_state = getattr(session, 'tool_states', {}).get('cardgenerator', {})
        
        return {
            "success": True,
            "session_id": session_id,
            "cardgenerator_state": cardgen_state,
            "current_step": cardgen_state.get('currentStep', 'text_generation'),
            "last_activity": cardgen_state.get('lastActivity'),
            "has_generated_item": bool(cardgen_state.get('lastGeneratedItem')),
            "has_generated_images": bool(cardgen_state.get('generatedImages')),
            "has_card_images": bool(cardgen_state.get('cardImages')),
            "is_completed": cardgen_state.get('currentStep') == 'completed'
        }
        
    except Exception as e:
        logger.error(f"Failed to get CardGenerator session state: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")