"""
FastAPI router for Player Character Generator API endpoints

Phase 4: Save/Load Characters
- POST /save-project: Create or update character project
- GET /list-projects: List user's character projects
- GET /project/{id}: Load a specific project
- DELETE /project/{id}: Delete a project
"""

from fastapi import APIRouter, Depends, HTTPException
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid

# Import authentication
from .auth_router import get_current_user
from auth_service import User

# Import Firestore
from firestore.firebase_config import db

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/api/playercharactergenerator", tags=["playercharactergenerator"])

# Firestore collection name
PCG_PROJECTS_COLLECTION = "playercharacter_projects"


def normalize_character_ids(character: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure all list items in character data have stable IDs
    Backend ID generation for consistent key handling
    """
    def ensure_id(item: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure an item has an ID"""
        if not item.get("id"):
            item["id"] = str(uuid.uuid4())
        return item

    # Get D&D 5e data if present
    dnd5e_data = character.get("dnd5eData", {})
    if not dnd5e_data:
        return character

    # Normalize spells
    if "spells" in dnd5e_data and isinstance(dnd5e_data["spells"], list):
        dnd5e_data["spells"] = [ensure_id(spell) for spell in dnd5e_data["spells"]]

    # Normalize equipment
    if "equipment" in dnd5e_data and isinstance(dnd5e_data["equipment"], list):
        dnd5e_data["equipment"] = [ensure_id(item) for item in dnd5e_data["equipment"]]

    # Normalize features
    if "features" in dnd5e_data and isinstance(dnd5e_data["features"], list):
        dnd5e_data["features"] = [ensure_id(feat) for feat in dnd5e_data["features"]]

    # Normalize classes (multiclass support)
    if "classes" in dnd5e_data and isinstance(dnd5e_data["classes"], list):
        dnd5e_data["classes"] = [ensure_id(cls) for cls in dnd5e_data["classes"]]

    character["dnd5eData"] = dnd5e_data
    return character


@router.post("/save-project")
async def save_project(
    request: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """
    Save or update a Player Character project

    Request body:
    - projectId: Optional[str] - If provided, updates existing project
    - character: Dict - The full character data
    - userId: str - User ID (verified against auth)
    - wizardStep: int - Current wizard step for restoration

    Returns:
    - projectId: str
    - createdAt: str
    - updatedAt: str
    """
    try:
        user_id = current_user.user_id
        project_id = request.get("projectId")
        character = request.get("character")

        if not character:
            raise HTTPException(status_code=400, detail="Character data required")

        # Generate project ID if not provided (new project)
        if not project_id:
            project_id = f"pcg_proj_{datetime.now().timestamp()}_{user_id[:8]}"
            logger.info(f"Creating new PlayerCharacter project: {project_id}")
        else:
            logger.info(f"Updating PlayerCharacter project: {project_id}")

        # Normalize character (ensure all list items have IDs)
        normalized_character = normalize_character_ids(character)

        # Extract character metadata for quick display
        dnd5e_data = normalized_character.get("dnd5eData", {})
        race_name = dnd5e_data.get("race", {}).get("name") if isinstance(dnd5e_data.get("race"), dict) else None
        classes = dnd5e_data.get("classes", [])
        class_name = classes[0].get("name") if classes and isinstance(classes[0], dict) else None
        level = normalized_character.get("level", 1)

        # Prepare project data
        now = datetime.now()
        project_data = {
            "id": project_id,
            "name": normalized_character.get("name", "Unnamed Character"),
            "description": normalized_character.get("description", ""),
            "createdBy": user_id,
            "updatedAt": now.isoformat(),
            "lastModified": now.isoformat(),
            "state": {
                "character": normalized_character,
                "wizardStep": request.get("wizardStep", 0),
                "autoSaveEnabled": True,
                "lastSaved": now.isoformat()
            },
            "metadata": {
                "version": "1.0.0",
                "platform": "web",
                "race": race_name,
                "class": class_name,
                "level": level
            }
        }

        # Check if project exists (for update vs create)
        doc_ref = db.collection(PCG_PROJECTS_COLLECTION).document(project_id)
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

        logger.info(f"Saved PlayerCharacter project: {project_id} for user: {user_id}")

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


@router.get("/list-projects")
async def list_projects(
    current_user: User = Depends(get_current_user)
):
    """
    List user's Player Character projects

    Returns list of project summaries with:
    - id, name, description
    - race, className, level (for quick display)
    - createdAt, updatedAt
    """
    try:
        user_id = current_user.user_id

        projects_ref = db.collection(PCG_PROJECTS_COLLECTION)
        query = projects_ref.where("createdBy", "==", user_id)

        projects = []
        for doc in query.stream():
            project_data = doc.to_dict()
            projects.append(project_data)

        # Sort by updatedAt (most recent first)
        projects.sort(key=lambda p: p.get("updatedAt", ""), reverse=True)

        logger.info(f"Listed {len(projects)} PlayerCharacter projects for user: {user_id}")

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
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific Player Character project

    Returns full project data including character state
    """
    try:
        user_id = current_user.user_id

        doc_ref = db.collection(PCG_PROJECTS_COLLECTION).document(project_id)
        doc = doc_ref.get()

        if not doc.exists:
            raise HTTPException(status_code=404, detail="Project not found")

        project_data = doc.to_dict()

        # Verify ownership
        if project_data.get("createdBy") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        logger.info(f"Loaded PlayerCharacter project: {project_id} for user: {user_id}")

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
    current_user: User = Depends(get_current_user)
):
    """
    Delete a Player Character project
    """
    try:
        user_id = current_user.user_id

        doc_ref = db.collection(PCG_PROJECTS_COLLECTION).document(project_id)
        doc = doc_ref.get()

        if not doc.exists:
            raise HTTPException(status_code=404, detail="Project not found")

        project_data = doc.to_dict()

        # Verify ownership
        if project_data.get("createdBy") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Delete project
        doc_ref.delete()

        logger.info(f"Deleted PlayerCharacter project: {project_id}")

        return {
            "success": True,
            "message": "Project deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting project: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Health check endpoint
@router.get("/health")
async def health_check():
    """
    Health check for Player Character Generator
    """
    return {
        "status": "healthy",
        "service": "Player Character Generator",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }
