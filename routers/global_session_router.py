"""
Global Session State API Router
Provides endpoints for managing global session state across all DungeonMind tools
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
import logging
from session_management import (
    session_manager, get_session, get_authenticated_session,
    EnhancedGlobalSession
)
from models.session_models import (
    CreateSessionRequest, UpdateSessionRequest, RestoreSessionRequest,
    SessionResponse, SessionStatus, CardGeneratorUpdateRequest,
    GlobalSessionPreferences
)
from models.dungeonmind_objects import ObjectType
from database.dungeonmind_objects_db import dungeonmind_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/session", tags=["Global Session"])


@router.post("/create", response_model=SessionResponse)
async def create_session(
    request: CreateSessionRequest,
    http_request: Request,
    response: Response
):
    """Create a new global session"""
    try:
        session_id = session_manager.create_session(
            user_id=request.user_id,
            platform=request.platform,
            request=http_request
        )
        
        session = session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=500, detail="Failed to create session")
        
        # Set session cookie
        response.set_cookie(
            key="dungeonmind_session_id",
            value=session_id,
            max_age=24 * 60 * 60,  # 24 hours
            httponly=True,
            secure=True,
            samesite="lax"
        )
        
        # Apply initial preferences if provided
        if request.preferences:
            session.preferences = request.preferences
        
        status = session_manager.get_session_status(session)
        
        logger.info(f"Created new session {session_id} for user {request.user_id}")
        
        return SessionResponse(
            success=True,
            session_id=session_id,
            status=status,
            message="Session created successfully"
        )
        
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/restore", response_model=SessionResponse)
async def restore_session(
    request: RestoreSessionRequest,
    http_request: Request,
    response: Response
):
    """Restore an existing session or create new one if restoration fails"""
    try:
        session_id = request.session_id
        
        # Try to get from cookie if not provided
        if not session_id:
            session_id = http_request.cookies.get("dungeonmind_session_id")
        
        session = None
        if session_id:
            session = session_manager.get_session(session_id)
        
        # If session doesn't exist or is expired, create new one if allowed
        if not session and request.fallback_to_new:
            session_id = session_manager.create_session(request=http_request)
            session = session_manager.get_session(session_id)
            
            # Update cookie
            response.set_cookie(
                key="dungeonmind_session_id",
                value=session_id,
                max_age=24 * 60 * 60,
                httponly=True,
                secure=True,
                samesite="lax"
            )
            
            message = "Created new session (restoration failed)"
        elif session:
            message = "Session restored successfully"
        else:
            raise HTTPException(status_code=404, detail="Session not found")
        
        status = session_manager.get_session_status(session)
        
        return SessionResponse(
            success=True,
            session_id=session_id,
            status=status,
            message=message
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to restore session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=SessionResponse)
async def get_session_status_endpoint(
    session_data = Depends(get_session)
):
    """Get current session status"""
    try:
        session, session_id = session_data
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        status = session_manager.get_session_status(session)
        
        return SessionResponse(
            success=True,
            session_id=session_id,
            status=status,
            message="Session status retrieved"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/tools/{tool_name}", response_model=SessionResponse)
async def update_tool_state(
    tool_name: str,
    updates: Dict[str, Any],
    session_data = Depends(get_session)
):
    """Update state for a specific tool"""
    try:
        session, session_id = session_data
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Validate tool name
        valid_tools = ['cardgenerator', 'storegenerator', 'ruleslawyer', 'statblockgenerator']
        if tool_name not in valid_tools:
            raise HTTPException(status_code=400, detail=f"Invalid tool name. Must be one of: {valid_tools}")
        
        # Update tool state
        success = await session_manager.update_tool_state(session_id, tool_name, updates)
        
        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to update {tool_name} state")
        
        # Get updated status
        updated_session = session_manager.get_session(session_id)
        status = session_manager.get_session_status(updated_session)
        
        logger.debug(f"Updated {tool_name} state for session {session_id}")
        
        return SessionResponse(
            success=True,
            session_id=session_id,
            status=status,
            message=f"{tool_name} state updated successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update {tool_name} state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cardgenerator/update", response_model=SessionResponse)
async def update_cardgenerator_state(
    request: CardGeneratorUpdateRequest,
    session_data = Depends(get_session)
):
    """Specialized endpoint for updating CardGenerator state"""
    try:
        session, session_id = session_data
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Convert request to updates dictionary
        updates = request.dict(exclude_unset=True)
        
        # Update CardGenerator state
        success = await session_manager.update_cardgenerator_state(session_id, updates)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update CardGenerator state")
        
        # Get updated status
        updated_session = session_manager.get_session(session_id)
        status = session_manager.get_session_status(updated_session)
        
        logger.debug(f"Updated CardGenerator state for session {session_id}")
        
        return SessionResponse(
            success=True,
            session_id=session_id,
            status=status,
            message="CardGenerator state updated successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update CardGenerator state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent-objects")
async def get_recent_objects(
    object_type: Optional[ObjectType] = None,
    limit: int = 20,
    session_data = Depends(get_authenticated_session)
):
    """Get recently viewed objects for the current user"""
    try:
        session, session_id = session_data
        
        if not session.user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Get recent object IDs from session
        recent_ids = session.recently_viewed[:limit]
        
        if not recent_ids:
            return {"objects": [], "total": 0}
        
        # Fetch objects from database
        objects = []
        for obj_id in recent_ids:
            try:
                obj = await dungeonmind_db.get_object(obj_id, session.user_id)
                if obj and (not object_type or obj.type == object_type):
                    objects.append(obj.dict())
            except Exception as e:
                logger.warning(f"Failed to fetch recent object {obj_id}: {e}")
                continue
        
        return {
            "objects": objects,
            "total": len(objects),
            "session_id": session_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get recent objects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clipboard/add/{object_id}")
async def add_to_clipboard(
    object_id: str,
    session_data = Depends(get_authenticated_session)
):
    """Add an object to the cross-tool clipboard"""
    try:
        session, session_id = session_data
        
        # Verify user can access the object
        obj = await dungeonmind_db.get_object(object_id, session.user_id)
        if not obj:
            raise HTTPException(status_code=404, detail="Object not found or access denied")
        
        # Add to clipboard
        session.add_to_clipboard(object_id)
        
        return {
            "success": True,
            "message": f"Added {obj.name} to clipboard",
            "clipboard_count": len(session.clipboard)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add object to clipboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clipboard/{object_id}")
async def remove_from_clipboard(
    object_id: str,
    session_data = Depends(get_session)
):
    """Remove an object from the clipboard"""
    try:
        session, session_id = session_data
        
        session.remove_from_clipboard(object_id)
        
        return {
            "success": True,
            "message": "Removed from clipboard",
            "clipboard_count": len(session.clipboard)
        }
        
    except Exception as e:
        logger.error(f"Failed to remove object from clipboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clipboard")
async def get_clipboard(
    session_data = Depends(get_authenticated_session)
):
    """Get objects in the cross-tool clipboard"""
    try:
        session, session_id = session_data
        
        # Fetch clipboard objects
        clipboard_objects = []
        for obj_id in session.clipboard:
            try:
                obj = await dungeonmind_db.get_object(obj_id, session.user_id)
                if obj:
                    clipboard_objects.append(obj.dict())
            except Exception as e:
                logger.warning(f"Failed to fetch clipboard object {obj_id}: {e}")
                continue
        
        return {
            "objects": clipboard_objects,
            "total": len(clipboard_objects),
            "session_id": session_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get clipboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/world/{world_id}")
async def switch_world(
    world_id: str,
    session_data = Depends(get_session)
):
    """Switch the active world context"""
    try:
        session, session_id = session_data
        
        # TODO: Validate world access when world management is implemented
        
        session.switch_world(world_id)
        
        return {
            "success": True,
            "message": f"Switched to world {world_id}",
            "active_world_id": session.active_world_id
        }
        
    except Exception as e:
        logger.error(f"Failed to switch world: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/project/{project_id}")
async def switch_project(
    project_id: str,
    session_data = Depends(get_session)
):
    """Switch the active project context"""
    try:
        session, session_id = session_data
        
        # TODO: Validate project access when project management is implemented
        
        session.switch_project(project_id)
        
        return {
            "success": True,
            "message": f"Switched to project {project_id}",
            "active_project_id": session.active_project_id
        }
        
    except Exception as e:
        logger.error(f"Failed to switch project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/preferences")
async def update_preferences(
    preferences: GlobalSessionPreferences,
    session_data = Depends(get_session)
):
    """Update global session preferences"""
    try:
        session, session_id = session_data
        
        session.preferences = preferences
        
        return {
            "success": True,
            "message": "Preferences updated successfully",
            "preferences": session.preferences.dict()
        }
        
    except Exception as e:
        logger.error(f"Failed to update preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    response: Response,
    session_data = Depends(get_session)
):
    """Delete a session"""
    try:
        current_session, current_session_id = session_data
        
        # Only allow deletion of current session or admin users
        if session_id != current_session_id:
            raise HTTPException(status_code=403, detail="Can only delete your own session")
        
        success = session_manager.delete_session(session_id)
        
        if success:
            # Clear session cookie
            response.delete_cookie(
                key="dungeonmind_session_id",
                path="/",
                domain=None
            )
            
            return {"success": True, "message": "Session deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Session not found")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_session_stats():
    """Get global session statistics (admin endpoint)"""
    try:
        stats = session_manager.get_session_stats()
        
        return {
            "success": True,
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"Failed to get session stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Cleanup endpoint for removing expired sessions
@router.post("/cleanup")
async def cleanup_expired_sessions():
    """Cleanup expired sessions (admin/maintenance endpoint)"""
    try:
        initial_count = len(session_manager.sessions)
        session_manager.cleanup_old_sessions()
        final_count = len(session_manager.sessions)
        
        cleaned_up = initial_count - final_count
        
        return {
            "success": True,
            "message": f"Cleaned up {cleaned_up} expired sessions",
            "sessions_before": initial_count,
            "sessions_after": final_count
        }
        
    except Exception as e:
        logger.error(f"Failed to cleanup sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 