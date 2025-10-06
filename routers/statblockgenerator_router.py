"""
FastAPI router for StatBlock Generator API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Request
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import json

# Import authentication
from .auth_router import get_current_user, get_current_user_optional
from auth_service import User

# Import StatBlock components
from statblockgenerator.statblock_generator import StatBlockGenerator
from statblockgenerator.models.statblock_models import (
    CreatureGenerationRequest,
    ImageGenerationRequest,
    ModelGenerationRequest,
    StatBlockValidationRequest,
    ProjectCreateRequest,
    SessionSaveRequest,
    StatBlockDetails,
    StatBlockProject,
    StatBlockGeneratorState
)

# Import Firestore utilities (following CardGenerator pattern)
import firestore.firestore_utils as firestore_utils
from google.cloud import firestore

# Import external service clients
import os
import fal_client
from cloudflare.handle_images import upload_image_to_cloudflare

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/api/statblockgenerator", tags=["statblockgenerator"])

# Global StatBlock generator instance
statblock_generator = StatBlockGenerator()

# Firestore collection names
STATBLOCK_SESSIONS_COLLECTION = "statblock_sessions"
STATBLOCK_PROJECTS_COLLECTION = "statblock_projects"
STATBLOCK_CREATURES_COLLECTION = "statblock_creatures"

@router.post("/generate-statblock")
async def generate_statblock(
    request: CreatureGenerationRequest,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Generate a complete D&D 5e creature statblock from description
    Does not require authentication - works for anonymous users
    """
    try:
        logger.info(f"Generating statblock for user: {current_user.email if current_user else 'anonymous'}")
        
        success, result = await statblock_generator.generate_creature(request)
        
        if not success:
            raise HTTPException(status_code=400, detail=result.get("error", "Generation failed"))
        
        return {
            "success": True,
            "data": result,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in generate_statblock: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate-image")
async def generate_image(
    request: ImageGenerationRequest,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Generate creature artwork using Fal.ai
    Does not require authentication - works for anonymous users
    """
    try:
        logger.info(f"Generating creature image for prompt: {request.sd_prompt[:50]}...")
        
        # Use Fal.ai for image generation (following CardGenerator pattern)
        fal_result = fal_client.subscribe(
            "fal-ai/flux/schnell",
            arguments={
                "prompt": request.sd_prompt,
                "image_size": "landscape_4_3",
                "num_inference_steps": 4,
                "num_images": request.num_images,
                "enable_safety_checker": True
            }
        )
        
        if not fal_result or "images" not in fal_result:
            raise HTTPException(status_code=400, detail="Image generation failed")
        
        # Process generated images
        generated_images = []
        for idx, image_data in enumerate(fal_result["images"]):
            image_url = image_data.get("url")
            if image_url:
                # Upload to Cloudflare for persistence (following CardGenerator pattern)
                try:
                    cf_result = upload_image_to_cloudflare(image_url, f"statblock_creature_{datetime.now().timestamp()}_{idx}")
                    if cf_result["success"]:
                        generated_images.append({
                            "id": f"img_{datetime.now().timestamp()}_{idx}",
                            "url": cf_result["cloudflare_url"],
                            "original_url": image_url,
                            "prompt": request.sd_prompt,
                            "created_at": datetime.now().isoformat()
                        })
                except Exception as upload_error:
                    logger.warning(f"Failed to upload image to Cloudflare: {upload_error}")
                    # Fall back to original URL
                    generated_images.append({
                        "id": f"img_{datetime.now().timestamp()}_{idx}",
                        "url": image_url,
                        "prompt": request.sd_prompt,
                        "created_at": datetime.now().isoformat()
                    })
        
        return {
            "success": True,
            "data": {
                "images": generated_images,
                "generation_info": {
                    "prompt": request.sd_prompt,
                    "model": "fal-ai/flux/schnell",
                    "num_images": len(generated_images)
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error generating creature image: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/validate-statblock")
async def validate_statblock(
    request: StatBlockValidationRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user)
):
    """
    Validate a D&D 5e statblock for accuracy and balance
    """
    try:
        logger.info(f"Validating statblock: {request.statblock.name}")
        
        success, result = await statblock_generator.validate_statblock(request)
        
        if not success:
            raise HTTPException(status_code=400, detail=result.get("error", "Validation failed"))
        
        return {
            "success": True,
            "data": result,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error validating statblock: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/calculate-cr")
async def calculate_challenge_rating(
    statblock: StatBlockDetails,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user)
):
    """
    Calculate appropriate challenge rating for a creature
    """
    try:
        logger.info(f"Calculating CR for: {statblock.name}")
        
        success, result = await statblock_generator.calculate_challenge_rating(statblock)
        
        if not success:
            raise HTTPException(status_code=400, detail=result.get("error", "CR calculation failed"))
        
        return {
            "success": True,
            "data": result,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error calculating CR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Project Management Endpoints (following CardGenerator patterns)

@router.post("/create-project")
async def create_project(
    request: ProjectCreateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Create a new StatBlock project
    """
    try:
        user_id = current_user["uid"]
        project_id = f"sb_proj_{datetime.now().timestamp()}_{user_id[:8]}"
        
        project = StatBlockProject(
            project_id=project_id,
            name=request.name,
            description=request.description,
            user_id=user_id,
            tags=request.tags or []
        )
        
        # Save to Firestore
        db = firestore.Client()
        doc_ref = db.collection(STATBLOCK_PROJECTS_COLLECTION).document(project_id)
        doc_ref.set(project.dict())
        
        logger.info(f"Created StatBlock project: {project_id}")
        
        return {
            "success": True,
            "data": {"project": project.dict()},
            "message": "Project created successfully"
        }
        
    except Exception as e:
        logger.error(f"Error creating project: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list-projects")
async def list_projects(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    List user's StatBlock projects
    """
    try:
        user_id = current_user["uid"]
        
        db = firestore.Client()
        projects_ref = db.collection(STATBLOCK_PROJECTS_COLLECTION)
        query = projects_ref.where("user_id", "==", user_id).order_by("last_modified", direction=firestore.Query.DESCENDING)
        
        projects = []
        for doc in query.stream():
            project_data = doc.to_dict()
            projects.append(project_data)
        
        return {
            "success": True,
            "data": {"projects": projects},
            "count": len(projects)
        }
        
    except Exception as e:
        logger.error(f"Error listing projects: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/project/{project_id}")
async def get_project(
    project_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get a specific StatBlock project
    """
    try:
        user_id = current_user["uid"]
        
        db = firestore.Client()
        doc_ref = db.collection(STATBLOCK_PROJECTS_COLLECTION).document(project_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Project not found")
        
        project_data = doc.to_dict()
        
        # Verify ownership
        if project_data.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        return {
            "success": True,
            "data": {"project": project_data}
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting project: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/project/{project_id}")
async def delete_project(
    project_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Delete a StatBlock project
    """
    try:
        user_id = current_user["uid"]
        
        db = firestore.Client()
        doc_ref = db.collection(STATBLOCK_PROJECTS_COLLECTION).document(project_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Project not found")
        
        project_data = doc.to_dict()
        
        # Verify ownership
        if project_data.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Delete project
        doc_ref.delete()
        
        logger.info(f"Deleted StatBlock project: {project_id}")
        
        return {
            "success": True,
            "message": "Project deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting project: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/save-project")
async def save_project(
    request: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Save or update a StatBlock project with auto-normalization
    Phase 3: Auto-save endpoint with ID normalization
    """
    try:
        user_id = current_user["uid"]
        project_id = request.get("projectId")
        statblock = request.get("statblock")
        
        if not statblock:
            raise HTTPException(status_code=400, detail="Statblock data required")
        
        # Generate project ID if not provided (new project)
        if not project_id:
            project_id = f"sb_proj_{datetime.now().timestamp()}_{user_id[:8]}"
            logger.info(f"Creating new StatBlock project: {project_id}")
        else:
            logger.info(f"Updating StatBlock project: {project_id}")
        
        # Phase 3 Task 7: Normalize statblock (ensure all list items have IDs)
        normalized_statblock = normalize_statblock_ids(statblock)
        
        # Prepare project data
        now = datetime.now()
        project_data = {
            "id": project_id,
            "name": normalized_statblock.get("name", "Untitled Creature"),
            "description": normalized_statblock.get("description", ""),
            "createdBy": user_id,
            "updatedAt": now.isoformat(),
            "lastModified": now.isoformat(),
            "state": {
                "creatureDetails": normalized_statblock,
                "currentStepId": request.get("currentStepId", "creature-description"),
                "stepCompletion": request.get("stepCompletion", {}),
                "selectedAssets": request.get("selectedAssets", {}),
                "generatedContent": request.get("generatedContent", {}),
                "autoSaveEnabled": True,
                "lastSaved": now.isoformat()
            },
            "metadata": {
                "version": "1.0.0",
                "platform": "web",
                "challengeRating": normalized_statblock.get("challengeRating"),
                "creatureType": normalized_statblock.get("type")
            }
        }
        
        # Check if project exists (for update vs create)
        db = firestore.Client()
        doc_ref = db.collection(STATBLOCK_PROJECTS_COLLECTION).document(project_id)
        doc = doc_ref.get()
        
        if doc.exists:
            # Verify ownership before update
            existing_data = doc.to_dict()
            if existing_data.get("createdBy") != user_id:
                raise HTTPException(status_code=403, detail="Access denied")
            
            # Preserve creation time for updates
            project_data["createdAt"] = existing_data.get("createdAt", now.isoformat())
        else:
            # New project
            project_data["createdAt"] = now.isoformat()
        
        # Save to Firestore
        doc_ref.set(project_data)
        
        logger.info(f"Saved StatBlock project: {project_id} for user: {user_id}")
        
        return {
            "success": True,
            "projectId": project_id,
            "createdAt": project_data["createdAt"],
            "updatedAt": project_data["updatedAt"],
            "message": "Project saved successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving project: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def normalize_statblock_ids(statblock: Dict[str, Any]) -> Dict[str, Any]:
    """
    Phase 3 Task 7: Ensure all list items have stable IDs
    Backend ID generation with frontend fallback support
    """
    import uuid
    
    def ensure_id(item: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure an item has an ID"""
        if not item.get("id"):
            item["id"] = str(uuid.uuid4())
        return item
    
    # Normalize actions
    if "actions" in statblock and isinstance(statblock["actions"], list):
        statblock["actions"] = [ensure_id(action) for action in statblock["actions"]]
    
    # Normalize bonus actions
    if "bonusActions" in statblock and isinstance(statblock["bonusActions"], list):
        statblock["bonusActions"] = [ensure_id(action) for action in statblock["bonusActions"]]
    
    # Normalize reactions
    if "reactions" in statblock and isinstance(statblock["reactions"], list):
        statblock["reactions"] = [ensure_id(reaction) for reaction in statblock["reactions"]]
    
    # Normalize special abilities
    if "specialAbilities" in statblock and isinstance(statblock["specialAbilities"], list):
        statblock["specialAbilities"] = [ensure_id(ability) for ability in statblock["specialAbilities"]]
    
    # Normalize spells
    if "spells" in statblock and isinstance(statblock["spells"], dict):
        if "cantrips" in statblock["spells"] and isinstance(statblock["spells"]["cantrips"], list):
            statblock["spells"]["cantrips"] = [ensure_id(spell) for spell in statblock["spells"]["cantrips"]]
        if "knownSpells" in statblock["spells"] and isinstance(statblock["spells"]["knownSpells"], list):
            statblock["spells"]["knownSpells"] = [ensure_id(spell) for spell in statblock["spells"]["knownSpells"]]
    
    # Normalize legendary actions
    if "legendaryActions" in statblock and isinstance(statblock["legendaryActions"], dict):
        if "actions" in statblock["legendaryActions"] and isinstance(statblock["legendaryActions"]["actions"], list):
            statblock["legendaryActions"]["actions"] = [ensure_id(action) for action in statblock["legendaryActions"]["actions"]]
    
    # Normalize lair actions
    if "lairActions" in statblock and isinstance(statblock["lairActions"], dict):
        if "actions" in statblock["lairActions"] and isinstance(statblock["lairActions"]["actions"], list):
            statblock["lairActions"]["actions"] = [ensure_id(action) for action in statblock["lairActions"]["actions"]]
    
    return statblock

# Session Management Endpoints

@router.post("/save-session")
async def save_session(
    request: SessionSaveRequest,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user)
):
    """
    Save StatBlock generator session state
    """
    try:
        session_data = request.session_data
        
        # Update timestamps
        session_data.last_modified = datetime.now()
        if not session_data.created_at:
            session_data.created_at = datetime.now()
        
        # Set user ID if authenticated
        if current_user:
            session_data.user_id = current_user["uid"]
        
        # Save to Firestore
        db = firestore.Client()
        doc_ref = db.collection(STATBLOCK_SESSIONS_COLLECTION).document(session_data.session_id)
        doc_ref.set(session_data.dict())
        
        # If this is a manual save with creature name, also save creature separately
        if not request.is_auto_save and request.creature_name and session_data.creature_details:
            creature_id = f"sb_creature_{datetime.now().timestamp()}"
            creature_data = session_data.creature_details.dict()
            creature_data["id"] = creature_id
            creature_data["name"] = request.creature_name
            creature_data["project_id"] = session_data.project_id
            creature_data["user_id"] = session_data.user_id
            
            creature_ref = db.collection(STATBLOCK_CREATURES_COLLECTION).document(creature_id)
            creature_ref.set(creature_data)
        
        logger.info(f"Saved StatBlock session: {session_data.session_id}")
        
        return {
            "success": True,
            "data": {
                "session_id": session_data.session_id,
                "last_saved": session_data.last_modified.isoformat()
            },
            "message": "Session saved successfully"
        }
        
    except Exception as e:
        logger.error(f"Error saving session: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/load-session/{session_id}")
async def load_session(
    session_id: str,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user)
):
    """
    Load StatBlock generator session state
    """
    try:
        db = firestore.Client()
        doc_ref = db.collection(STATBLOCK_SESSIONS_COLLECTION).document(session_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session_data = doc.to_dict()
        
        # Verify access (owner or anonymous)
        if current_user and session_data.get("user_id") != current_user["uid"]:
            raise HTTPException(status_code=403, detail="Access denied")
        
        return {
            "success": True,
            "data": {"session": session_data}
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading session: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Health check endpoint
@router.get("/health")
async def health_check():
    """
    Health check for StatBlock Generator
    """
    return {
        "status": "healthy",
        "service": "StatBlock Generator",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }
