"""
Demo Router for Generation Drawer Engine Testing

Provides real endpoints for testing the GenerationDrawerEngine demo page.
These endpoints use in-memory storage and mock data for quick iteration.

Endpoints:
- GET  /api/demo/health         - Health check
- POST /api/demo/upload         - Upload image (stores in memory)
- GET  /api/demo/library        - Get paginated library images
- DELETE /api/demo/delete/{id}  - Delete an image
- POST /api/demo/generate-text  - Generate mock statblock text
- POST /api/demo/generate-image - Generate mock images

Note: All data is stored in memory and lost on server restart.
This is intentional for demo/testing purposes.
"""

import logging
import uuid
import time
import base64
from datetime import datetime
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, File, UploadFile, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/demo", tags=["Demo/Testing"])

# ============================================================================
# In-Memory Storage
# ============================================================================

# Simulated image library (in-memory, resets on restart)
_demo_library: Dict[str, dict] = {}

# Demo placeholder images (using placeholder.com for reliable URLs)
DEMO_PLACEHOLDER_IMAGES = [
    {
        "id": "demo-1",
        "url": "https://placehold.co/512x512/7c3aed/ffffff?text=Dragon",
        "prompt": "A fearsome red dragon",
        "createdAt": "2025-12-20T10:00:00Z",
        "service": "demo-statblock",
        "sessionId": "demo-session"
    },
    {
        "id": "demo-2", 
        "url": "https://placehold.co/512x512/059669/ffffff?text=Goblin",
        "prompt": "A sneaky goblin rogue",
        "createdAt": "2025-12-21T11:00:00Z",
        "service": "demo-statblock",
        "sessionId": "demo-session"
    },
    {
        "id": "demo-3",
        "url": "https://placehold.co/512x512/dc2626/ffffff?text=Lich",
        "prompt": "An ancient lich king",
        "createdAt": "2025-12-22T12:00:00Z",
        "service": "demo-statblock",
        "sessionId": "demo-session"
    },
    {
        "id": "demo-4",
        "url": "https://placehold.co/512x512/2563eb/ffffff?text=Elemental",
        "prompt": "A water elemental",
        "createdAt": "2025-12-23T13:00:00Z",
        "service": "demo-statblock",
        "sessionId": "demo-session"
    }
]

# Initialize library with demo images
for img in DEMO_PLACEHOLDER_IMAGES:
    _demo_library[img["id"]] = img.copy()


# ============================================================================
# Request/Response Models
# ============================================================================

class DemoGenerateTextRequest(BaseModel):
    """Request for demo text generation"""
    description: str
    include_legendary: bool = False
    include_lair: bool = False
    include_spellcasting: bool = False


class DemoGenerateImageRequest(BaseModel):
    """Request for demo image generation"""
    prompt: Optional[str] = None
    description: Optional[str] = None  # Alias for prompt (frontend sends this)
    count: int = 1
    sessionId: Optional[str] = None
    
    @property
    def effective_prompt(self) -> str:
        """Get the prompt, preferring explicit prompt over description"""
        return self.prompt or self.description or "A fantasy creature"


class DemoLibraryResponse(BaseModel):
    """Response for library listing"""
    images: List[dict]
    total: int
    page: int
    pageSize: int
    totalPages: int


# ============================================================================
# Health Check
# ============================================================================

@router.get("/health")
async def demo_health_check():
    """
    Health check for demo endpoints.
    Returns service status and library stats.
    """
    return {
        "status": "ok",
        "service": "demo",
        "libraryCount": len(_demo_library),
        "endpoints": [
            "POST /api/demo/upload",
            "GET /api/demo/library",
            "DELETE /api/demo/delete/{id}",
            "POST /api/demo/generate",
            "POST /api/demo/generate-image",
            "POST /api/demo/reset"
        ]
    }


# ============================================================================
# Image Upload
# ============================================================================

@router.post("/upload")
async def demo_upload_image(file: UploadFile = File(...)):
    """
    Upload an image to the demo library.
    
    Stores image data in memory (base64 encoded for simplicity).
    In a real implementation, this would upload to cloud storage.
    """
    try:
        logger.info(f"📤 [Demo] Upload request: {file.filename}")
        
        # Validate file type
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(
                status_code=422, 
                detail=f"Invalid file type: {file.content_type}. Must be an image."
            )
        
        # Read file content
        content = await file.read()
        
        # Check size (5MB limit)
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(
                status_code=422,
                detail="File too large. Maximum size is 5MB."
            )
        
        # Generate image ID
        image_id = f"upload-{uuid.uuid4().hex[:8]}"
        
        # Create data URL for the image (allows display without file server)
        base64_content = base64.b64encode(content).decode("utf-8")
        data_url = f"data:{file.content_type};base64,{base64_content}"
        
        # Create image record
        image_record = {
            "id": image_id,
            "url": data_url,
            "prompt": f"Uploaded: {file.filename}",
            "createdAt": datetime.now().isoformat(),
            "service": "demo-upload",
            "sessionId": "demo-session",
            "filename": file.filename,
            "contentType": file.content_type,
            "size": len(content)
        }
        
        # Store in library
        _demo_library[image_id] = image_record
        
        logger.info(f"✅ [Demo] Upload successful: {image_id} ({len(content)} bytes)")
        
        return {
            "success": True,
            "image": image_record,
            "message": f"Image uploaded successfully: {file.filename}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [Demo] Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Image Library
# ============================================================================

@router.get("/library")
async def demo_get_library(
    page: int = Query(1, ge=1, description="Page number"),
    pageSize: int = Query(20, ge=1, le=100, description="Items per page"),
    sessionId: Optional[str] = Query(None, description="Filter by session ID"),
    service: Optional[str] = Query(None, description="Filter by service")
):
    """
    Get paginated list of images from the demo library.
    
    Supports filtering by sessionId and service.
    """
    try:
        # Get all images
        all_images = list(_demo_library.values())
        
        # Apply filters
        if sessionId:
            all_images = [img for img in all_images if img.get("sessionId") == sessionId]
        if service:
            all_images = [img for img in all_images if img.get("service") == service]
        
        # Sort by createdAt (newest first)
        all_images.sort(key=lambda x: x.get("createdAt", ""), reverse=True)
        
        # Paginate
        total = len(all_images)
        total_pages = (total + pageSize - 1) // pageSize
        start = (page - 1) * pageSize
        end = start + pageSize
        page_images = all_images[start:end]
        
        logger.info(f"📚 [Demo] Library request: page={page}, total={total}")
        
        return {
            "images": page_images,
            "total": total,
            "page": page,
            "pageSize": pageSize,
            "totalPages": total_pages
        }
        
    except Exception as e:
        logger.error(f"❌ [Demo] Library fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Image Delete
# ============================================================================

@router.delete("/delete/{image_id}")
async def demo_delete_image(image_id: str):
    """
    Delete an image from the demo library.
    """
    try:
        logger.info(f"🗑️ [Demo] Delete request: {image_id}")
        
        if image_id not in _demo_library:
            raise HTTPException(status_code=404, detail=f"Image not found: {image_id}")
        
        # Remove from library
        deleted = _demo_library.pop(image_id)
        
        logger.info(f"✅ [Demo] Deleted: {image_id}")
        
        return {
            "success": True,
            "message": f"Image deleted: {image_id}",
            "deleted": deleted
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [Demo] Delete failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Text Generation (Mock)
# ============================================================================

@router.post("/generate")
async def demo_generate_text(request: DemoGenerateTextRequest):
    """
    Generate a mock statblock from description.
    
    Returns demo data after a simulated delay.
    This is for testing the generation drawer UI without using real AI credits.
    """
    try:
        logger.info(f"📝 [Demo] Text generation request: {request.description[:50]}...")
        
        # Simulate generation time (1-2 seconds)
        time.sleep(1.5)
        
        # Generate mock statblock based on description
        mock_statblock = _generate_mock_statblock(request)
        
        logger.info(f"✅ [Demo] Text generation complete")
        
        return {
            "success": True,
            "statblock": mock_statblock,
            "imagePrompt": f"Fantasy illustration of {mock_statblock['name']}, {request.description[:100]}",
            "images": [],
            "generationTime": 1.5
        }
        
    except Exception as e:
        logger.error(f"❌ [Demo] Text generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _generate_mock_statblock(request: DemoGenerateTextRequest) -> dict:
    """Generate a mock statblock based on the request description."""
    
    # Extract a name from the description (first few words or generic)
    description_words = request.description.split()[:3]
    name = " ".join(description_words).title() if description_words else "Demo Creature"
    
    # Base statblock
    statblock = {
        "name": name,
        "size": "Medium",
        "type": "beast",
        "alignment": "unaligned",
        "armorClass": 13,
        "hitPoints": 45,
        "hitDice": "6d8+18",
        "speed": {"walk": 30, "fly": 0, "swim": 0},
        "abilityScores": {
            "strength": 16,
            "dexterity": 14,
            "constitution": 16,
            "intelligence": 6,
            "wisdom": 12,
            "charisma": 8
        },
        "savingThrows": ["Str +5", "Con +5"],
        "skills": ["Perception +3", "Stealth +4"],
        "damageResistances": [],
        "damageImmunities": [],
        "conditionImmunities": [],
        "senses": ["darkvision 60 ft.", "passive Perception 13"],
        "languages": ["understands Common but can't speak"],
        "challengeRating": "2",
        "proficiencyBonus": "+2",
        "traits": [
            {
                "name": "Keen Senses",
                "description": "The creature has advantage on Wisdom (Perception) checks that rely on sight, hearing, or smell."
            }
        ],
        "actions": [
            {
                "name": "Multiattack",
                "description": "The creature makes two attacks: one with its bite and one with its claws."
            },
            {
                "name": "Bite",
                "description": "Melee Weapon Attack: +5 to hit, reach 5 ft., one target. Hit: 8 (1d10 + 3) piercing damage."
            },
            {
                "name": "Claws",
                "description": "Melee Weapon Attack: +5 to hit, reach 5 ft., one target. Hit: 6 (1d6 + 3) slashing damage."
            }
        ],
        "reactions": [],
        "legendaryActions": [],
        "lairActions": [],
        "spellcasting": None
    }
    
    # Add legendary actions if requested
    if request.include_legendary:
        statblock["legendaryActions"] = [
            {
                "name": "Detect",
                "description": "The creature makes a Wisdom (Perception) check.",
                "cost": 1
            },
            {
                "name": "Tail Attack",
                "description": "The creature makes a tail attack.",
                "cost": 1
            },
            {
                "name": "Wing Attack (Costs 2 Actions)",
                "description": "The creature beats its wings. Each creature within 10 feet must succeed on a DC 15 Dexterity saving throw or take 10 (2d6 + 3) bludgeoning damage.",
                "cost": 2
            }
        ]
        statblock["challengeRating"] = "8"
    
    # Add lair actions if requested
    if request.include_lair:
        statblock["lairActions"] = [
            {
                "name": "Tremor",
                "description": "The ground shakes. Each creature on the ground within 60 feet must succeed on a DC 15 Dexterity saving throw or be knocked prone."
            },
            {
                "name": "Darkness",
                "description": "Magical darkness spreads from a point within 60 feet, filling a 15-foot-radius sphere until initiative count 20 on the next round."
            }
        ]
    
    # Add spellcasting if requested
    if request.include_spellcasting:
        statblock["spellcasting"] = {
            "ability": "Intelligence",
            "saveDC": 14,
            "attackBonus": 6,
            "level": 7,
            "spells": {
                "cantrips": ["fire bolt", "mage hand", "prestidigitation"],
                "1st": {"slots": 4, "spells": ["magic missile", "shield", "detect magic"]},
                "2nd": {"slots": 3, "spells": ["misty step", "scorching ray"]},
                "3rd": {"slots": 3, "spells": ["fireball", "counterspell"]},
                "4th": {"slots": 1, "spells": ["greater invisibility"]}
            }
        }
        statblock["challengeRating"] = "5"
    
    return statblock


# ============================================================================
# Image Generation (Mock)
# ============================================================================

@router.post("/generate-image")
async def demo_generate_image(request: DemoGenerateImageRequest):
    """
    Generate mock images from a prompt.
    
    Returns placeholder images after a simulated delay.
    This is for testing the generation drawer UI without using real AI credits.
    """
    try:
        prompt = request.effective_prompt
        logger.info(f"🎨 [Demo] Image generation request: {prompt[:50]}...")
        
        # Simulate generation time (2-3 seconds)
        time.sleep(2.5)
        
        # Generate mock images
        generated_images = []
        session_id = request.sessionId or f"session-{uuid.uuid4().hex[:8]}"
        
        for i in range(request.count):
            image_id = f"gen-{uuid.uuid4().hex[:8]}"
            
            # Create a placeholder with the prompt text
            prompt_text = prompt[:20].replace(" ", "+")
            colors = ["7c3aed", "059669", "dc2626", "2563eb", "d97706"]
            color = colors[i % len(colors)]
            
            image_record = {
                "id": image_id,
                "url": f"https://placehold.co/512x512/{color}/ffffff?text={prompt_text}",
                "prompt": prompt,
                "createdAt": datetime.now().isoformat(),
                "service": "demo-generation",
                "sessionId": session_id
            }
            
            # Add to library
            _demo_library[image_id] = image_record
            generated_images.append(image_record)
        
        logger.info(f"✅ [Demo] Generated {len(generated_images)} images")
        
        return {
            "success": True,
            "images": generated_images,
            "count": len(generated_images),
            "generationTime": 2.5
        }
        
    except Exception as e:
        logger.error(f"❌ [Demo] Image generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Reset Demo Data
# ============================================================================

@router.post("/reset")
async def demo_reset():
    """
    Reset the demo library to initial state.
    
    Clears all uploaded/generated images and restores demo placeholders.
    """
    try:
        logger.info("🔄 [Demo] Resetting library...")
        
        _demo_library.clear()
        
        # Restore demo images
        for img in DEMO_PLACEHOLDER_IMAGES:
            _demo_library[img["id"]] = img.copy()
        
        logger.info(f"✅ [Demo] Library reset. {len(_demo_library)} demo images restored.")
        
        return {
            "success": True,
            "message": "Demo library reset",
            "imageCount": len(_demo_library)
        }
        
    except Exception as e:
        logger.error(f"❌ [Demo] Reset failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

