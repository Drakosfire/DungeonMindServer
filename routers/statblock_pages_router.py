"""Statblock pages API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
import logging

from session_management import get_authenticated_session
from database.dungeonmind_objects_db import dungeonmind_db, PermissionError
from models.dungeonmind_objects import (
    StatblockPageCreateRequest,
    StatblockPageUpdateRequest,
    StatblockPageResponse
)


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/statblock-pages", tags=["Statblock Pages"])


@router.post("/", response_model=StatblockPageResponse)
async def create_statblock_page(
    request: StatblockPageCreateRequest,
    session_data = Depends(get_authenticated_session)
):
    """Create a new statblock page bound to the authenticated user."""

    session, _ = session_data
    user_id = session.user_id

    try:
        # Default world/project from session if not provided
        metadata = request.metadata
        if not metadata.worldId:
            metadata.worldId = session.active_world_id
        if not metadata.projectId:
            metadata.projectId = session.active_project_id

        response = await dungeonmind_db.create_statblock_page(request, user_id)
        return response

    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to create statblock page: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{page_id}", response_model=StatblockPageResponse)
async def get_statblock_page(
    page_id: str,
    session_data = Depends(get_authenticated_session)
):
    """Retrieve an existing statblock page if the user has access."""

    session, _ = session_data
    user_id = session.user_id

    try:
        doc = await dungeonmind_db.get_statblock_page(page_id, user_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Statblock page not found")
        return doc

    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to fetch statblock page %s: %s", page_id, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/{page_id}", response_model=StatblockPageResponse)
async def update_statblock_page(
    page_id: str,
    request: StatblockPageUpdateRequest,
    session_data = Depends(get_authenticated_session)
):
    """Update an existing statblock page for the authenticated user."""

    session, _ = session_data
    user_id = session.user_id

    try:
        response = await dungeonmind_db.update_statblock_page(page_id, user_id, request)
        if not response:
            raise HTTPException(status_code=404, detail="Statblock page not found")
        return response

    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to update statblock page %s: %s", page_id, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

