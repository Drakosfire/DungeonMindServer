"""
Card Generation Router

Clean, focused router handling only card generation endpoints.
Integrates with the existing global session system for state management.

Extracted from monolithic cardgenerator_router.py as part of architectural refactoring.
"""

import logging
import os
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, File, UploadFile, Form, Depends
from pydantic import BaseModel

from cardgenerator.services.card_generation_service import card_generation_service
from cardgenerator.services.image_management_service import image_management_service
from cardgenerator.utils.error_handler import CardGenerationError, ImageProcessingError
from .auth_router import get_current_user

# Import global session dependencies
from session_management import get_session, session_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/card-generation", tags=["Card Generation"])

# Request models
class ItemGenerationRequest(BaseModel):
    userIdea: str

class RenderCardRequest(BaseModel):
    image_url: str
    item_details: Dict[str, Any]

@router.post('/generate-item')
async def generate_item_description(
    request: ItemGenerationRequest,
    session_data = Depends(get_session)
):
    """
    Generate item description from user input using AI
    
    Integrates with global session system for state persistence
    """
    try:
        session, session_id = session_data
        logger.info(f"Item generation request for session {session_id}: {request.userIdea[:50]}...")
        
        # Delegate to service layer
        result = await card_generation_service.generate_item_description(request.userIdea)
        
        # Update global session with the generated item
        if session:
            cardgen_update = {
                "lastGeneratedItem": result,
                "lastActivity": "item_generation",
                "currentStep": "image_selection"
            }
            await session_manager.update_tool_state(session_id, "cardgenerator", cardgen_update)
            logger.debug(f"Updated CardGenerator session state for {session_id}")
        
        logger.info("Item generation completed successfully")
        return result
        
    except CardGenerationError as e:
        logger.error(f"Card generation failed: {e}")
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
    Generate core images from text prompt (Step 2 workflow)
    
    Updates session with generated images for persistence
    """
    try:
        session, session_id = session_data
        
        # Validate inputs
        if not sdPrompt.strip():
            raise HTTPException(status_code=422, detail="SD prompt cannot be empty")
        if numImages < 1 or numImages > 10:
            raise HTTPException(status_code=422, detail="Number of images must be between 1 and 10")
        
        logger.info(f"Core image generation for session {session_id}: {numImages} images")
        
        # Delegate to service layer
        result = await card_generation_service.generate_core_images(sdPrompt, numImages)
        
        # Update global session with generated images
        if session:
            cardgen_update = {
                "generatedImages": result.images,
                "lastActivity": "core_image_generation", 
                "currentStep": "image_selection",
                "sdPrompt": sdPrompt
            }
            await session_manager.update_tool_state(session_id, "cardgenerator", cardgen_update)
            logger.debug(f"Updated session with {len(result.images)} generated images")
        
        # Return in expected format
        return {
            "images": result.images,
            "success": result.success,
            "message": result.message,
            "session_id": session_id
        }
        
    except CardGenerationError as e:
        logger.error(f"Core image generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
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
    Generate card images using template (Step 3 workflow)
    
    Combines image upload with card generation and session persistence
    """
    try:
        session, session_id = session_data
        
        # Validate inputs
        if not sdPrompt.strip():
            raise HTTPException(status_code=422, detail="SD prompt cannot be empty")
        if numImages < 1 or numImages > 10:
            raise HTTPException(status_code=422, detail="Number of images must be between 1 and 10")
        
        logger.info(f"Card image generation for session {session_id} with template: {template.filename}")
        
        # Step 1: Upload template
        upload_result = await image_management_service.upload_single_image(template)
        template_url = upload_result.url
        
        # Step 2: Generate card images
        result = await card_generation_service.generate_card_images(
            template_url, sdPrompt, numImages
        )
        
        # Update global session with card images and template
        if session:
            cardgen_update = {
                "cardImages": result.images,
                "templateUrl": template_url,
                "lastActivity": "card_image_generation",
                "currentStep": "card_selection",
                "sdPrompt": sdPrompt
            }
            await session_manager.update_tool_state(session_id, "cardgenerator", cardgen_update)
            logger.debug(f"Updated session with {len(result.images)} card images")
        
        logger.info(f"Successfully generated {len(result.images)} card images")
        return {
            "images": result.images,
            "template_url": template_url,
            "success": result.success,
            "message": result.message,
            "session_id": session_id
        }
        
    except ImageProcessingError as e:
        logger.error(f"Image processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Image processing error: {str(e)}")
    except CardGenerationError as e:
        logger.error(f"Card generation failed: {e}")
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
    Render text on card using the new modular pipeline
    
    Final step that creates the completed card and updates session
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
        
        # Save to temporary file
        temp_file_path = f"temp_card_{item_name}.png"
        image_object.save(temp_file_path)
        
        # Upload and clean up
        upload_result = await image_management_service.upload_temporary_file(temp_file_path)
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
            
            # Add to recently created objects for cross-tool access
            if hasattr(session, 'add_to_recently_viewed'):
                # TODO: Create DungeonMind object for the card and add to recently viewed
                pass
            
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