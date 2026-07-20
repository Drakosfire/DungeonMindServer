"""Legacy StatBlock Generator app routes.

This module preserves the LandingPage generator, project, session, validation,
and image routes. DungeonBuddy's authoritative statblock v1 contract lives in
``statblocks_v1``. Historical command-board v2 routes live in
``routers.statblock_v2_compatibility_router``.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import time

# Import authentication
from .auth_router import get_current_user, get_current_user_optional
from auth_service import User

# Import StatBlock components
from statblockgenerator.runtime import get_statblock_generator
from statblockgenerator.models.statblock_models import (
    CreatureGenerationRequest,
    StatBlockValidationRequest,
    ProjectCreateRequest,
    SessionSaveRequest,
    StatBlockDetails,
    StatBlockProject,
)

# Import Firestore utilities (following CardGenerator pattern)
import firestore.firestore_utils as firestore_utils
from firestore.firebase_config import db  # Properly initialized Firestore client
from google.cloud import firestore

# Import external service clients
import os
import fal_client
from openai import OpenAI
from cloudflare.handle_images import upload_image_to_cloudflare

# NOTE: Image generation now handled by /api/images/generate (image_management_router.py)

# Initialize OpenAI client (still used for text generation)
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/api/statblockgenerator", tags=["statblockgenerator"])

# Global StatBlock generator instance (shared with v2 compatibility routes)
statblock_generator = get_statblock_generator()

# Firestore collection names
STATBLOCK_SESSIONS_COLLECTION = "statblock_sessions"
STATBLOCK_PROJECTS_COLLECTION = "statblock_projects"
STATBLOCK_CREATURES_COLLECTION = "statblock_creatures"


@router.get("/health")
async def health_check():
    """
    Health check endpoint for StatBlockGenerator service.
    Returns service status and basic configuration info.
    """
    return {
        "status": "ok",
        "service": "statblockgenerator",
        "generator_ready": statblock_generator is not None,
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "fal_configured": bool(os.getenv("FAL_KEY"))
    }


@router.post("/generate-statblock")
async def generate_statblock(
    request: CreatureGenerationRequest,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Generate a complete D&D 5e creature statblock from description
    Does not require authentication - works for anonymous users
    """
    start_time = time.time()
    user_id = current_user.email if current_user else 'anonymous'
    
    try:
        logger.info(f"🕐 [Generation Start] User: {user_id} | Timestamp: {datetime.now().isoformat()}")
        logger.info(f"📝 [Generation Request] Description length: {len(request.description)} chars")
        
        success, result = await statblock_generator.generate_creature(request)
        
        elapsed = time.time() - start_time
        logger.info(f"✅ [Generation Success] User: {user_id} | Duration: {elapsed:.2f}s")
        
        if not success:
            logger.warning(f"⚠️ [Generation Failed] User: {user_id} | Duration: {elapsed:.2f}s | Error: {result.get('error', 'Unknown')}")
            raise HTTPException(status_code=400, detail=result.get("error", "Generation failed"))
        
        return {
            "success": True,
            "data": result,
            "timestamp": datetime.now().isoformat(),
            "generation_time_seconds": round(elapsed, 2)
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions without wrapping
        raise
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"❌ [Generation Error] User: {user_id} | Duration: {elapsed:.2f}s | Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/upload-image")
async def upload_image(
    request: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """
    Upload user's own creature image to Cloudflare R2
    Requires authentication for CDN storage and project association
    """
    try:
        image_data = request.get("imageData")
        filename = request.get("filename", f"statblock_upload_{datetime.now().timestamp()}")
        
        if not image_data:
            raise HTTPException(status_code=400, detail="Image data required")
        
        logger.info(f"Uploading creature image for user: {current_user.email}")
        
        # Upload to Cloudflare R2 (reuse existing upload function)
        # upload_image_to_cloudflare takes 1 arg (UploadFile) and returns URL string
        cloudflare_url = await upload_image_to_cloudflare(image_data)
        
        return {
            "success": True,
            "data": {
                "id": f"upload_{datetime.now().timestamp()}",
                "url": cloudflare_url,
                "prompt": "Uploaded image",
                "created_at": datetime.now().isoformat()
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Image upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload-images")
async def upload_images(
    images: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Upload multiple user images to Cloudflare R2
    
    **REQUIRES AUTHENTICATION** - Login required to upload images.
    Guests can still use AI image generation.
    
    Images are stored permanently and associated with user account.
    """
    try:
        user_email = current_user.email
        
        logger.info(f"Uploading {len(images)} image(s) for user: {user_email}")
        
        if len(images) == 0:
            raise HTTPException(status_code=400, detail="No images provided")
        
        if len(images) > 20:
            raise HTTPException(status_code=400, detail="Maximum 20 images per upload")
        
        uploaded_images = []
        
        for idx, image_file in enumerate(images):
            try:
                # Validate file type
                if not image_file.content_type or not image_file.content_type.startswith('image/'):
                    logger.warning(f"Skipping non-image file: {image_file.filename}")
                    continue
                
                # Validate file size (max 10MB) - Python 3.10 compatible
                content = await image_file.read()
                file_size = len(content)
                
                if file_size > 10 * 1024 * 1024:  # 10MB
                    logger.warning(f"Skipping oversized file: {image_file.filename} ({file_size} bytes)")
                    continue
                
                # Recreate UploadFile for upload_image_to_cloudflare
                from io import BytesIO
                image_file.file = BytesIO(content)
                await image_file.seek(0)
                
                # Upload to Cloudflare
                cloudflare_url = await upload_image_to_cloudflare(image_file)
                
                timestamp = datetime.now().timestamp()
                uploaded_images.append({
                    "id": f"upload_{timestamp}_{idx}_{user_email[:8]}",
                    "url": cloudflare_url,
                    "filename": image_file.filename,
                    "prompt": f"Uploaded: {image_file.filename}",
                    "timestamp": datetime.now().isoformat()
                })
                
                logger.info(f"✅ Uploaded image {idx+1}/{len(images)}: {image_file.filename}")
                
            except Exception as img_error:
                logger.error(f"Failed to upload image {idx+1} ({image_file.filename}): {str(img_error)}")
                # Continue with other images even if one fails
                continue
        
        if len(uploaded_images) == 0:
            raise HTTPException(status_code=400, detail="No valid images were uploaded")
        
        return {
            "success": True,
            "data": {
                "images": uploaded_images,
                "total_uploaded": len(uploaded_images),
                "message": "Images uploaded and saved to your account!"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch image upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/validate-statblock")
async def validate_statblock(
    request: StatBlockValidationRequest,
    current_user: Optional[User] = Depends(get_current_user)
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
    current_user: Optional[User] = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
):
    """
    Create a new StatBlock project
    """
    try:
        user_id = current_user.user_id
        project_id = f"sb_proj_{datetime.now().timestamp()}_{user_id[:8]}"
        
        project = StatBlockProject(
            project_id=project_id,
            name=request.name,
            description=request.description,
            user_id=user_id,
            tags=request.tags or []
        )
        
        # Save to Firestore
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
    current_user: User = Depends(get_current_user)
):
    """
    List user's StatBlock projects
    """
    try:
        user_id = current_user.user_id
        
        projects_ref = db.collection(STATBLOCK_PROJECTS_COLLECTION)
        query = projects_ref.where("createdBy", "==", user_id)
        
        projects = []
        for doc in query.stream():
            project_data = doc.to_dict()
            projects.append(project_data)
        
        # Sort by updatedAt on the server side (no index required)
        projects.sort(key=lambda p: p.get("updatedAt", ""), reverse=True)
        
        return {
            "success": True,
            "data": {"projects": projects},
            "count": len(projects)
        }
        
    except Exception as e:
        logger.error(f"Error listing projects: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list-all-images")
async def list_all_images(
    current_user: User = Depends(get_current_user)
):
    """
    Get all generated images across all user's projects
    Returns aggregated library of creature images for reuse
    """
    try:
        user_id = current_user.user_id
        
        projects_ref = db.collection(STATBLOCK_PROJECTS_COLLECTION)
        query = projects_ref.where("createdBy", "==", user_id)
        
        # Aggregate all images from all projects
        all_images = []
        seen_urls = set()  # Deduplicate by URL
        
        for doc in query.stream():
            project_data = doc.to_dict()
            project_id = project_data.get("id")
            project_name = project_data.get("name", "Untitled")
            
            # Extract images from generatedContent
            generated_content = project_data.get("state", {}).get("generatedContent", {})
            images = generated_content.get("images", [])
            
            for img in images:
                img_url = img.get("url")
                if img_url and img_url not in seen_urls:
                    seen_urls.add(img_url)
                    all_images.append({
                        "id": img.get("id"),
                        "url": img_url,
                        "prompt": img.get("prompt", ""),
                        "timestamp": img.get("timestamp", ""),
                        "projectId": project_id,
                        "projectName": project_name
                    })
        
        # Sort by timestamp (most recent first)
        all_images.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        logger.info(f"Retrieved {len(all_images)} images for user: {user_id}")
        
        return {
            "success": True,
            "data": {
                "images": all_images,
                "count": len(all_images)
            }
        }
        
    except Exception as e:
        logger.error(f"Error listing all images: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/project/{project_id}")
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific StatBlock project
    """
    try:
        user_id = current_user.user_id
        
        doc_ref = db.collection(STATBLOCK_PROJECTS_COLLECTION).document(project_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Project not found")
        
        project_data = doc.to_dict()
        
        # Verify ownership
        if project_data.get("createdBy") != user_id:
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

@router.delete("/project/{project_id}/image/{image_id}")
async def delete_image_from_project(
    project_id: str,
    image_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Remove an image from a specific project's generatedContent
    Does not delete the image from CDN or other projects
    """
    try:
        user_id = current_user.user_id
        
        doc_ref = db.collection(STATBLOCK_PROJECTS_COLLECTION).document(project_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Project not found")
        
        project_data = doc.to_dict()
        
        # Verify ownership
        if project_data.get("createdBy") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Remove image from generatedContent.images
        state = project_data.get("state", {})
        generated_content = state.get("generatedContent", {})
        images = generated_content.get("images", [])
        
        # Filter out the image to delete
        updated_images = [img for img in images if img.get("id") != image_id]
        
        if len(updated_images) == len(images):
            raise HTTPException(status_code=404, detail="Image not found in project")
        
        # Update Firestore
        generated_content["images"] = updated_images
        state["generatedContent"] = generated_content
        project_data["state"] = state
        project_data["updatedAt"] = datetime.now().isoformat()
        
        doc_ref.set(project_data)
        
        logger.info(f"Removed image {image_id} from project {project_id}")
        
        return {
            "success": True,
            "message": "Image removed from project",
            "remainingImages": len(updated_images)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting image from project: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete-image")
async def delete_image(
    image_url: str,
    current_user: User = Depends(get_current_user)
):
    """
    Permanently delete an image from Cloudflare storage
    This removes the image from all projects (permanent deletion)
    Requires authentication for security
    """
    try:
        logger.info(f"Deleting image from library for user: {current_user.email}")
        
        # Extract Cloudflare image ID from URL
        # Cloudflare URLs typically look like: https://imagedelivery.net/{account_hash}/{image_id}/{variant}
        import re
        
        # Try to extract image ID from Cloudflare URL
        match = re.search(r'/([a-zA-Z0-9-]+)/[^/]+$', image_url)
        if not match:
            logger.warning(f"Could not extract image ID from URL: {image_url}")
            # Return success anyway (image may already be deleted or URL malformed)
            return {
                "success": True,
                "message": "Image URL processed"
            }
        
        image_id = match.group(1)
        
        # Delete from Cloudflare Images
        cloudflare_account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
        cloudflare_api_token = os.environ.get('CLOUDFLARE_IMAGES_API_TOKEN')
        
        if not cloudflare_account_id or not cloudflare_api_token:
            logger.error("Cloudflare credentials not configured")
            raise HTTPException(status_code=500, detail="Image storage not configured")
        
        delete_url = f"https://api.cloudflare.com/client/v4/accounts/{cloudflare_account_id}/images/v1/{image_id}"
        headers = {"Authorization": f"Bearer {cloudflare_api_token}"}
        
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            cf_response = await client.delete(delete_url, headers=headers)
            cf_result = cf_response.json()
            
            if cf_result.get("success"):
                logger.info(f"✅ Successfully deleted image {image_id} from Cloudflare")
            else:
                logger.warning(f"Cloudflare deletion returned: {cf_result}")
                # Don't fail if Cloudflare returns error (image may already be deleted)
        
        return {
            "success": True,
            "message": "Image deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting image: {str(e)}")
        # Return success to prevent UI blocking (optimistic deletion)
        return {
            "success": True,
            "message": "Image deletion processed"
        }

@router.delete("/project/{project_id}")
async def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Delete a StatBlock project
    """
    try:
        user_id = current_user.user_id
        
        doc_ref = db.collection(STATBLOCK_PROJECTS_COLLECTION).document(project_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Project not found")
        
        project_data = doc.to_dict()
        
        # Verify ownership
        if project_data.get("createdBy") != user_id:
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
    current_user: User = Depends(get_current_user)
):
    """
    Save or update a StatBlock project with auto-normalization
    Phase 3: Auto-save endpoint with ID normalization
    """
    try:
        user_id = current_user.user_id
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
    current_user: Optional[User] = Depends(get_current_user)
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
            session_data.user_id = current_user.user_id
        
        # Save to Firestore
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
    current_user: Optional[User] = Depends(get_current_user)
):
    """
    Load StatBlock generator session state
    """
    try:
        doc_ref = db.collection(STATBLOCK_SESSIONS_COLLECTION).document(session_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session_data = doc.to_dict()
        
        # Verify access (owner or anonymous)
        if current_user and session_data.get("user_id") != current_user.user_id:
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

