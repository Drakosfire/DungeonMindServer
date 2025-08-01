"""
CardGenerator Compatibility Router

Provides backward compatibility for old monolithic router endpoints.
Redirects to new focused routers to prevent breaking existing frontend code.

This is a temporary bridge during the migration period.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Form, File, UploadFile
from fastapi.responses import RedirectResponse
from typing import Dict, Any

from .auth_router import get_current_user
from session_management import get_session

# Import the new routers for delegation
from .cardgenerator_project_router import (
    list_projects, create_project, get_project, 
    update_project, delete_project, duplicate_project
)
from .card_generation_router import (
    generate_item_description, generate_core_images, 
    generate_card_images, render_card_text
)
from .image_management_router import upload_single_image, delete_image
from .asset_router import get_example_images, get_border_options

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cardgenerator", tags=["CardGenerator Compatibility"])

# ============================================================================
# PROJECT MANAGEMENT COMPATIBILITY ENDPOINTS
# ============================================================================

@router.get('/list-projects')
async def list_projects_compat(
    includeTemplates: bool = False,
    current_user=Depends(get_current_user)
):
    """
    COMPATIBILITY: Redirect old list-projects to new projects/list
    """
    logger.info("🔄 Compatibility redirect: /list-projects -> /projects/list")
    return await list_projects(includeTemplates, current_user)

@router.post('/create-project')
async def create_project_compat(
    request: Dict[str, Any],
    current_user=Depends(get_current_user),
    session_data=Depends(get_session)
):
    """
    COMPATIBILITY: Redirect old create-project to new projects/create
    """
    logger.info("🔄 Compatibility redirect: /create-project -> /projects/create")
    # Convert dict to proper request model
    from .cardgenerator_project_router import CreateProjectRequest
    project_request = CreateProjectRequest(**request)
    return await create_project(project_request, current_user, session_data)

@router.get('/project/{project_id}')
async def get_project_compat(
    project_id: str,
    current_user=Depends(get_current_user),
    session_data=Depends(get_session)
):
    """
    COMPATIBILITY: Redirect old project/{id} to new projects/{id}
    """
    logger.info(f"🔄 Compatibility redirect: /project/{project_id} -> /projects/{project_id}")
    return await get_project(project_id, current_user, session_data)

@router.put('/project/{project_id}')
async def update_project_compat(
    project_id: str,
    request: Dict[str, Any],
    current_user=Depends(get_current_user),
    session_data=Depends(get_session)
):
    """
    COMPATIBILITY: Redirect old project update to new projects update
    """
    logger.info(f"🔄 Compatibility redirect: PUT /project/{project_id} -> /projects/{project_id}")
    from .cardgenerator_project_router import UpdateProjectRequest
    update_request = UpdateProjectRequest(**request)
    return await update_project(project_id, update_request, current_user, session_data)

@router.delete('/project/{project_id}')
async def delete_project_compat(
    project_id: str,
    current_user=Depends(get_current_user),
    session_data=Depends(get_session)
):
    """
    COMPATIBILITY: Redirect old project delete to new projects delete
    """
    logger.info(f"🔄 Compatibility redirect: DELETE /project/{project_id} -> /projects/{project_id}")
    return await delete_project(project_id, current_user, session_data)

@router.post('/project/{project_id}/duplicate')
async def duplicate_project_compat(
    project_id: str,
    new_name: str,
    current_user=Depends(get_current_user),
    session_data=Depends(get_session)
):
    """
    COMPATIBILITY: Redirect old project duplicate to new projects duplicate
    """
    logger.info(f"🔄 Compatibility redirect: /project/{project_id}/duplicate -> /projects/{project_id}/duplicate")
    return await duplicate_project(project_id, new_name, current_user, session_data)

# ============================================================================
# GENERATION COMPATIBILITY ENDPOINTS  
# ============================================================================

@router.post('/generate-item-dict')
async def generate_item_dict_compat(
    request: Dict[str, Any],
    session_data=Depends(get_session)
):
    """
    COMPATIBILITY: Redirect old generate-item-dict to new generate-item
    """
    logger.info("🔄 Compatibility redirect: /generate-item-dict -> /card-generation/generate-item")
    from .card_generation_router import ItemGenerationRequest
    # Convert from old format {userIdea: "..."} to new format
    user_idea = request.get('userIdea') or request.get('user_input', '')
    item_request = ItemGenerationRequest(userIdea=user_idea)
    return await generate_item_description(item_request, session_data)

@router.post('/generate-core-images')
async def generate_core_images_compat(
    sdPrompt: str = Form(...),
    numImages: int = Form(default=4),
    session_data=Depends(get_session)
):
    """
    COMPATIBILITY: Redirect old generate-core-images to new endpoint
    """
    logger.info("🔄 Compatibility redirect: /generate-core-images -> /card-generation/generate-core-images")
    return await generate_core_images(sdPrompt, numImages, session_data)

@router.post('/generate-card-images')
async def generate_card_images_compat(
    template: UploadFile = File(...),
    sdPrompt: str = Form(...),
    numImages: int = Form(default=4),
    session_data=Depends(get_session)
):
    """
    COMPATIBILITY: Redirect old generate-card-images to new endpoint
    """
    logger.info("🔄 Compatibility redirect: /generate-card-images -> /card-generation/generate-card-images")
    return await generate_card_images(template, sdPrompt, numImages, session_data)

@router.post('/render-card-text')
async def render_card_text_compat(
    request: Dict[str, Any],
    session_data=Depends(get_session)
):
    """
    COMPATIBILITY: Redirect old render-card-text to new render-text
    """
    logger.info("🔄 Compatibility redirect: /render-card-text -> /card-generation/render-text")
    from .card_generation_router import RenderCardRequest
    render_request = RenderCardRequest(**request)
    return await render_card_text(render_request, session_data)

# ============================================================================
# IMAGE MANAGEMENT COMPATIBILITY
# ============================================================================

@router.post('/upload-image')
async def upload_image_compat(file: UploadFile = File(...)):
    """
    COMPATIBILITY: Redirect old upload-image to new endpoint
    """
    logger.info("🔄 Compatibility redirect: /upload-image -> /images/upload")
    return await upload_single_image(file)

# ============================================================================
# ASSET COMPATIBILITY
# ============================================================================

@router.get('/example-images')
async def example_images_compat(category: str = None):
    """
    COMPATIBILITY: Redirect old example-images to new assets/examples
    """
    logger.info("🔄 Compatibility redirect: /example-images -> /assets/examples")
    return await get_example_images(category)

@router.get('/border-options')
async def border_options_compat(style: str = None):
    """
    COMPATIBILITY: Redirect old border-options to new assets/borders
    """
    logger.info("🔄 Compatibility redirect: /border-options -> /assets/borders")
    return await get_border_options(style)

# ============================================================================
# MIGRATION HELPER ENDPOINT
# ============================================================================

@router.get('/migration-guide')
async def get_migration_guide():
    """
    Provide migration guidance for frontend developers
    """
    return {
        "status": "CardGenerator API has been refactored",
        "version": "2.0",
        "migration_required": True,
        "endpoint_mapping": {
            "/api/cardgenerator/list-projects": "/api/cardgenerator/projects/list",
            "/api/cardgenerator/create-project": "/api/cardgenerator/projects/create", 
            "/api/cardgenerator/project/{id}": "/api/cardgenerator/projects/{id}",
            "/api/cardgenerator/generate-item-dict": "/api/card-generation/generate-item",
            "/api/cardgenerator/generate-core-images": "/api/card-generation/generate-core-images",
            "/api/cardgenerator/generate-card-images": "/api/card-generation/generate-card-images",
            "/api/cardgenerator/render-card-text": "/api/card-generation/render-text",
            "/api/cardgenerator/upload-image": "/api/images/upload",
            "/api/cardgenerator/example-images": "/api/assets/examples",
            "/api/cardgenerator/border-options": "/api/assets/borders"
        },
        "benefits": [
            "Clean separation of concerns",
            "Better maintainability", 
            "Improved error handling",
            "Session integration",
            "Faster development"
        ],
        "deprecation_notice": "Compatibility endpoints will be removed in v3.0"
    }