"""
FastAPI router for Player Character Generator API endpoints

Phase 4: Save/Load Characters
- POST /save-project: Create or update character project
- GET /list-projects: List user's character projects
- GET /project/{id}: Load a specific project
- DELETE /project/{id}: Delete a project

Phase 5: AI Generation
- POST /generate-preferences: Generate AI preferences for character creation
"""

from fastapi import APIRouter, Depends, HTTPException
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid
import time

# Import authentication
from .auth_router import get_current_user, get_current_user_optional
from auth_service import User

# Import Firestore
from firestore.firebase_config import db

# Import PCG Generator
from playercharactergenerator.pcg_generator import PlayerCharacterGenerator
from playercharactergenerator.models.pcg_models import (
    PreferenceGenerationRequest,
    GenerationInput,
    ValidateRequest,
    ValidationResult,
    ComputeRequest,
    ComputeResult,
)
from playercharactergenerator.rule_engine import PCGRuleEngine
from playercharactergenerator.rule_engine.compute import compute_derived_stats
from playercharactergenerator.rule_engine.validators import validate_translated_choices
from playercharactergenerator.rule_engine.translator import translate_preferences
from playercharactergenerator.character_builder import build_character_object

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/api/playercharactergenerator", tags=["playercharactergenerator"])

# Global PCG generator instance
pcg_generator = PlayerCharacterGenerator()
pcg_rule_engine = PCGRuleEngine()

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


# ============================================================================
# AI GENERATION ENDPOINTS
# ============================================================================

@router.post("/constraints")
async def get_constraints(request: GenerationInput):
    """
    Build deterministic GenerationConstraints for the given character foundation (levels 1–3).

    This is the backend "Rule Engine" entrypoint for the PCG pipeline.
    """
    try:
        constraints = pcg_rule_engine.get_constraints(request)
        return {
            "success": True,
            "data": {
                "constraints": constraints.model_dump(by_alias=True),
            },
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/validate", response_model=ValidationResult)
async def validate_translated(request: ValidateRequest):
    """
    Validate translated mechanical choices (from the frontend translator) against backend constraints.

    This makes harness results meaningful even when frontend validation logic is incomplete.
    """
    try:
        constraints = request.constraints or pcg_rule_engine.get_constraints(request.input)
        success, issues, sections = validate_translated_choices(
            input_data=request.input,
            constraints=constraints,
            choices=request.choices,
        )
        return ValidationResult(success=success, issues=issues, sections=sections)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/compute", response_model=ComputeResult)
async def compute_character(request: ComputeRequest):
    """
    Compute deterministic derived stats (E3) for translated mechanical choices.

    This endpoint is intended to become the authoritative backend "mathy bits" compute.
    For now, it:
    - computes constraints if missing
    - validates translated choices (E2 validators)
    - computes derived stats (mods/prof/HP/AC/etc.)
    """
    try:
        constraints = request.constraints or pcg_rule_engine.get_constraints(request.input)

        # Validate first (authoritative legality check)
        valid, issues, validation_sections = validate_translated_choices(
            input_data=request.input,
            constraints=constraints,
            choices=request.choices,
        )
        if not valid:
            return ComputeResult(
                success=False,
                issues=issues,
                derivedStats=None,
                sections={"validation": validation_sections},
            )

        ok, compute_issues, derived, compute_sections = compute_derived_stats(
            input_data=request.input,
            constraints=constraints,
            choices=request.choices,
        )
        merged_sections: Dict[str, Any] = {"validation": validation_sections}
        merged_sections.update(compute_sections)

        if not ok or not derived:
            return ComputeResult(
                success=False,
                issues=compute_issues,
                derivedStats=None,
                sections=merged_sections,
            )

        return ComputeResult(success=True, issues=[], derivedStats=derived, sections=merged_sections)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/generate-preferences")
async def generate_preferences(
    request: PreferenceGenerationRequest,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Generate AI preferences for character creation
    
    This endpoint generates creative preferences (ability priorities, skill themes,
    character flavor) based on user-provided character concept and constraints.
    
    Does not require authentication - works for anonymous users.
    
    Request body:
    - input: GenerationInput (classId, raceId, level, backgroundId, concept)
    - constraints: Optional[GenerationConstraints] - if not provided, backend computes via PCGRuleEngine
    
    Returns:
    - preferences: AiPreferences
    - rawResponse: str (for debugging)
    - generationInfo: Dict (tokens, model, etc.)
    """
    start_time = time.time()
    user_id = current_user.email if current_user else 'anonymous'
    
    try:
        logger.info(f"🎲 [PCG Generation Start] User: {user_id} | Timestamp: {datetime.now().isoformat()}")
        logger.info(f"📝 [PCG Generation] Class: {request.input.class_id} | Concept: {request.input.concept[:50]}...")
        
        success, result = await pcg_generator.generate_preferences(request)
        
        elapsed = time.time() - start_time
        
        if not success:
            logger.warning(f"⚠️ [PCG Generation Failed] User: {user_id} | Duration: {elapsed:.2f}s | Error: {result.get('error', 'Unknown')}")
            raise HTTPException(status_code=400, detail=result.get("error", "Generation failed"))
        
        logger.info(f"✅ [PCG Generation Success] User: {user_id} | Duration: {elapsed:.2f}s | Character: {result['preferences']['character']['name']}")
        
        return {
            "success": True,
            "data": result,
            "timestamp": datetime.now().isoformat(),
            "generationTimeSeconds": round(elapsed, 2)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"❌ [PCG Generation Error] User: {user_id} | Duration: {elapsed:.2f}s | Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate")
async def generate_character(
    request: GenerationInput,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Generate a complete D&D 5e character from concept.

    Pipeline:
    1. Constraints (rule engine)
    2. AI Preferences
    3. Translate preferences -> ValidationChoices (backend translator)
    4. Validate translated choices (E2)
    5. Compute derived stats (E3)
    6. Build frontend-compatible Character wrapper payload
    """
    start_time = time.time()
    user_id = current_user.email if current_user else "anonymous"

    try:
        logger.info(
            "🎲 [PCG Generate Start] User: %s | Class: %s | Race: %s | Level: %s",
            user_id,
            request.class_id,
            request.race_id,
            request.level,
        )

        # 1) Constraints
        constraints = pcg_rule_engine.get_constraints(request)

        # 2) AI preferences
        pref_request = PreferenceGenerationRequest(input=request, constraints=constraints)
        pref_ok, pref_result = await pcg_generator.generate_preferences(pref_request)
        if not pref_ok:
            raise HTTPException(status_code=400, detail=pref_result.get("error", "AI generation failed"))

        preferences = pref_result.get("preferences")
        if not preferences:
            raise HTTPException(status_code=400, detail="AI generation returned no preferences")

        # Pydantic normalization
        from playercharactergenerator.models.pcg_models import AiPreferences  # local import avoids circulars in some envs

        pref_model = AiPreferences(**preferences)

        # 3) Translate
        translate_ok, choices, translate_issues = translate_preferences(
            preferences=pref_model,
            constraints=constraints,
            level=int(request.level),
        )
        if not translate_ok:
            raise HTTPException(status_code=400, detail={"error": "Translation failed", "issues": translate_issues})

        # 4) Validate
        valid, validate_issues, validate_sections = validate_translated_choices(
            input_data=request,
            constraints=constraints,
            choices=choices,
        )
        if not valid:
            raise HTTPException(
                status_code=400,
                detail={"error": "Validation failed", "issues": validate_issues, "sections": validate_sections},
            )

        # 5) Compute
        compute_ok, compute_issues, derived, compute_sections = compute_derived_stats(
            input_data=request,
            constraints=constraints,
            choices=choices,
        )
        if not compute_ok or not derived:
            raise HTTPException(
                status_code=400,
                detail={"error": "Compute failed", "issues": compute_issues, "sections": compute_sections},
            )

        # 6) Build character payload (frontend-compatible)
        character = build_character_object(
            input_data=request,
            constraints=constraints,
            preferences=pref_model,
            choices=choices,
            derived_stats=derived,
        )
        character = normalize_character_ids(character)

        elapsed = time.time() - start_time
        try:
            dnd = (character or {}).get("dnd5eData") or {}
            logger.info(
                "🧾 [PCG Generate Payload] %s | weapons=%s equipment=%s features=%s spells=%s cantrips=%s armor=%s shield=%s eqPkg=%s featureChoices=%s",
                character.get("name", "(unnamed)"),
                len(dnd.get("weapons") or []),
                len(dnd.get("equipment") or []),
                len(dnd.get("features") or []),
                len(((dnd.get("spellcasting") or {}).get("spellsKnown")) or []),
                len(((dnd.get("spellcasting") or {}).get("cantrips")) or []),
                (dnd.get("armor") or {}).get("id") if isinstance(dnd.get("armor"), dict) else None,
                bool(dnd.get("shield")),
                getattr(choices, "equipment_package_id", None),
                getattr(choices, "feature_choices", None),
            )
        except Exception:
            # Never fail generation due to logging/shape issues.
            pass

        logger.info(
            "✅ [PCG Generate Success] User: %s | Duration: %.2fs | Character: %s",
            user_id,
            elapsed,
            character.get("name", "(unnamed)"),
        )

        return {
            "success": True,
            "data": {
                "character": character,
                "preferences": pref_model.model_dump(by_alias=True),
                "choices": choices.model_dump(by_alias=True),
                "derivedStats": derived.model_dump(by_alias=True),
                "constraints": constraints.model_dump(by_alias=True),
                "issues": translate_issues,
                "sections": {
                    "validation": validate_sections,
                    "compute": compute_sections,
                },
                "generationInfo": {
                    **(pref_result.get("generationInfo", {}) or {}),
                    "generationTimeSeconds": round(elapsed, 2),
                },
            },
            "timestamp": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("❌ [PCG Generate Error] User: %s | Duration: %.2fs | Error: %s", user_id, elapsed, str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-preferences-batch")
async def generate_preferences_batch(
    requests: List[PreferenceGenerationRequest],
    current_user: User = Depends(get_current_user)
):
    """
    Generate AI preferences for multiple characters (batch mode)
    
    Requires authentication. Used for testing/experimentation.
    
    Request body:
    - List of PreferenceGenerationRequest objects
    
    Returns:
    - results: List of generation results
    - summary: Aggregated statistics
    """
    start_time = time.time()
    user_id = current_user.email
    
    logger.info(f"🎲 [PCG Batch Start] User: {user_id} | Count: {len(requests)}")
    
    results = []
    success_count = 0
    
    for i, req in enumerate(requests):
        try:
            success, result = await pcg_generator.generate_preferences(req)
            results.append({
                "index": i,
                "success": success,
                "data": result if success else None,
                "error": result.get("error") if not success else None,
            })
            if success:
                success_count += 1
        except Exception as e:
            results.append({
                "index": i,
                "success": False,
                "error": str(e),
            })
    
    elapsed = time.time() - start_time
    
    logger.info(f"✅ [PCG Batch Complete] User: {user_id} | Duration: {elapsed:.2f}s | Success: {success_count}/{len(requests)}")
    
    return {
        "success": True,
        "results": results,
        "summary": {
            "total": len(requests),
            "successful": success_count,
            "failed": len(requests) - success_count,
            "successRate": round(success_count / len(requests) * 100, 1) if requests else 0,
            "totalTimeSeconds": round(elapsed, 2),
            "avgTimePerRequest": round(elapsed / len(requests), 2) if requests else 0,
        },
        "timestamp": datetime.now().isoformat(),
    }


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health")
async def health_check():
    """
    Health check for Player Character Generator
    """
    pcg_health = await pcg_generator.health_check()
    
    return {
        "status": pcg_health.get("status", "healthy"),
        "service": "Player Character Generator",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "generator": pcg_health,
    }
