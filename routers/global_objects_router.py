"""
Global Object Management API Router
Provides endpoints for managing DungeonMind objects across all tools
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
import logging
from session_management import get_authenticated_session
from database.dungeonmind_objects_db import dungeonmind_db, PermissionError
from models.dungeonmind_objects import (
    DungeonMindObject, ObjectType, Visibility,
    CreateObjectRequest, UpdateObjectRequest, ObjectSearchRequest,
    ItemCardData
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/objects", tags=["Global Objects"])


@router.post("/", response_model=dict)
async def create_object(
    request: CreateObjectRequest,
    session_data = Depends(get_authenticated_session)
):
    """Create a new DungeonMind object"""
    try:
        session, session_id = session_data
        user_id = session.user_id
        
        # Set world and project from session if not specified
        if not request.worldId and session.active_world_id:
            request.worldId = session.active_world_id
        if not request.projectId and session.active_project_id:
            request.projectId = session.active_project_id
        
        # Create the object
        obj = await dungeonmind_db.create_object_from_request(request, user_id)
        
        # Add to session's recently viewed
        session.add_to_recently_viewed(obj.id)
        
        logger.info(f"Created object {obj.id} of type {obj.type} for user {user_id}")
        
        return {
            "success": True,
            "object_id": obj.id,
            "object": obj.dict(),
            "message": f"Created {obj.type} '{obj.name}' successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to create object: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{object_id}", response_model=dict)
async def get_object(
    object_id: str,
    session_data = Depends(get_authenticated_session)
):
    """Get a specific object by ID"""
    try:
        session, session_id = session_data
        user_id = session.user_id
        
        obj = await dungeonmind_db.get_object(object_id, user_id)
        
        if not obj:
            raise HTTPException(status_code=404, detail="Object not found")
        
        # Add to session's recently viewed
        session.add_to_recently_viewed(object_id)
        
        return {
            "success": True,
            "object": obj.dict()
        }
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get object {object_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{object_id}", response_model=dict)
async def update_object(
    object_id: str,
    updates: UpdateObjectRequest,
    session_data = Depends(get_authenticated_session)
):
    """Update an existing object"""
    try:
        session, session_id = session_data
        user_id = session.user_id
        
        success = await dungeonmind_db.update_object(object_id, updates, user_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Object not found or update failed")
        
        # Get updated object
        updated_obj = await dungeonmind_db.get_object(object_id, user_id)
        
        return {
            "success": True,
            "object": updated_obj.dict() if updated_obj else None,
            "message": "Object updated successfully"
        }
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update object {object_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{object_id}", response_model=dict)
async def delete_object(
    object_id: str,
    session_data = Depends(get_authenticated_session)
):
    """Delete an object"""
    try:
        session, session_id = session_data
        user_id = session.user_id
        
        success = await dungeonmind_db.delete_object(object_id, user_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Object not found or deletion failed")
        
        # Remove from session's recently viewed and clipboard
        if object_id in session.recently_viewed:
            session.recently_viewed.remove(object_id)
        if object_id in session.clipboard:
            session.clipboard.remove(object_id)
        if object_id in session.pinned_objects:
            session.pinned_objects.remove(object_id)
        
        return {
            "success": True,
            "message": "Object deleted successfully"
        }
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete object {object_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=dict)
async def list_objects(
    object_type: Optional[ObjectType] = Query(None, description="Filter by object type"),
    world_id: Optional[str] = Query(None, description="Filter by world ID"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of objects to return"),
    offset: int = Query(0, ge=0, description="Number of objects to skip"),
    session_data = Depends(get_authenticated_session)
):
    """List objects accessible to the current user"""
    try:
        session, session_id = session_data
        user_id = session.user_id
        
        # Use active world/project from session if not specified
        effective_world_id = world_id or session.active_world_id
        effective_project_id = project_id or session.active_project_id
        
        objects = await dungeonmind_db.get_user_objects(
            user_id=user_id,
            object_type=object_type,
            world_id=effective_world_id,
            project_id=effective_project_id,
            limit=limit,
            offset=offset
        )
        
        return {
            "success": True,
            "objects": [obj.dict() for obj in objects],
            "total": len(objects),
            "filters": {
                "object_type": object_type,
                "world_id": effective_world_id,
                "project_id": effective_project_id,
                "limit": limit,
                "offset": offset
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to list objects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", response_model=dict)
async def search_objects(
    search_request: ObjectSearchRequest,
    session_data = Depends(get_authenticated_session)
):
    """Search for objects with text and filters"""
    try:
        session, session_id = session_data
        user_id = session.user_id
        
        # Use active world/project from session if not specified
        if not search_request.worldId and session.active_world_id:
            search_request.worldId = session.active_world_id
        if not search_request.projectId and session.active_project_id:
            search_request.projectId = session.active_project_id
        
        objects = await dungeonmind_db.search_objects(search_request, user_id)
        
        return {
            "success": True,
            "objects": [obj.dict() for obj in objects],
            "total": len(objects),
            "query": search_request.query,
            "filters": search_request.dict()
        }
        
    except Exception as e:
        logger.error(f"Failed to search objects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# CardGenerator-specific endpoints
@router.post("/items", response_model=dict)
async def create_item_card(
    item_data: ItemCardData,
    name: str,
    description: str,
    tags: List[str] = [],
    visibility: Visibility = Visibility.PRIVATE,
    session_data = Depends(get_authenticated_session)
):
    """Create a new item card object (CardGenerator-specific convenience endpoint)"""
    try:
        session, session_id = session_data
        user_id = session.user_id
        
        # Create request for item object
        request = CreateObjectRequest(
            type=ObjectType.ITEM,
            name=name,
            description=description,
            tags=tags,
            worldId=session.active_world_id,
            projectId=session.active_project_id,
            visibility=visibility,
            itemData=item_data
        )
        
        # Create the object
        obj = await dungeonmind_db.create_object_from_request(request, user_id)
        
        # Update session with active item
        if session.cardgenerator:
            session.cardgenerator.active_item_id = obj.id
            if obj.id not in session.cardgenerator.recent_items:
                session.cardgenerator.recent_items.insert(0, obj.id)
                session.cardgenerator.recent_items = session.cardgenerator.recent_items[:10]
        
        # Add to session's recently viewed
        session.add_to_recently_viewed(obj.id)
        
        logger.info(f"Created item card {obj.id} for user {user_id}")
        
        return {
            "success": True,
            "object_id": obj.id,
            "item": obj.dict(),
            "message": f"Created item '{obj.name}' successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to create item card: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/items/{item_id}", response_model=dict)
async def get_item_card(
    item_id: str,
    session_data = Depends(get_authenticated_session)
):
    """Get a specific item card (CardGenerator-specific convenience endpoint)"""
    try:
        session, session_id = session_data
        user_id = session.user_id
        
        obj = await dungeonmind_db.get_object(item_id, user_id)
        
        if not obj:
            raise HTTPException(status_code=404, detail="Item not found")
        
        if obj.type != ObjectType.ITEM:
            raise HTTPException(status_code=400, detail="Object is not an item")
        
        # Update CardGenerator session state
        if session.cardgenerator:
            session.cardgenerator.active_item_id = item_id
        
        # Add to session's recently viewed
        session.add_to_recently_viewed(item_id)
        
        return {
            "success": True,
            "item": obj.dict(),
            "item_data": obj.itemData.dict() if obj.itemData else None
        }
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get item card {item_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/items/{item_id}", response_model=dict)
async def update_item_card(
    item_id: str,
    item_data: Optional[ItemCardData] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    visibility: Optional[Visibility] = None,
    session_data = Depends(get_authenticated_session)
):
    """Update an item card (CardGenerator-specific convenience endpoint)"""
    try:
        session, session_id = session_data
        user_id = session.user_id
        
        # Build update request
        updates = UpdateObjectRequest()
        if name:
            updates.name = name
        if description:
            updates.description = description
        if tags is not None:
            updates.tags = tags
        if visibility:
            updates.visibility = visibility
        if item_data:
            updates.itemData = item_data
        
        success = await dungeonmind_db.update_object(item_id, updates, user_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Item not found or update failed")
        
        # Get updated object
        updated_obj = await dungeonmind_db.get_object(item_id, user_id)
        
        # Ensure it's an item
        if updated_obj and updated_obj.type != ObjectType.ITEM:
            raise HTTPException(status_code=400, detail="Object is not an item")
        
        return {
            "success": True,
            "item": updated_obj.dict() if updated_obj else None,
            "item_data": updated_obj.itemData.dict() if updated_obj and updated_obj.itemData else None,
            "message": "Item updated successfully"
        }
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update item card {item_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/items", response_model=dict)
async def list_item_cards(
    world_id: Optional[str] = Query(None, description="Filter by world ID"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    session_data = Depends(get_authenticated_session)
):
    """List item cards accessible to the current user"""
    try:
        session, session_id = session_data
        user_id = session.user_id
        
        # Use active world/project from session if not specified
        effective_world_id = world_id or session.active_world_id
        effective_project_id = project_id or session.active_project_id
        
        objects = await dungeonmind_db.get_user_objects(
            user_id=user_id,
            object_type=ObjectType.ITEM,
            world_id=effective_world_id,
            project_id=effective_project_id,
            limit=limit,
            offset=offset
        )
        
        # Extract item data for convenience
        items = []
        for obj in objects:
            item_dict = obj.dict()
            if obj.itemData:
                item_dict['item_data'] = obj.itemData.dict()
            items.append(item_dict)
        
        return {
            "success": True,
            "items": items,
            "total": len(items),
            "filters": {
                "world_id": effective_world_id,
                "project_id": effective_project_id,
                "limit": limit,
                "offset": offset
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to list item cards: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Object relationship endpoints
@router.get("/{object_id}/related", response_model=dict)
async def get_related_objects(
    object_id: str,
    limit: int = Query(10, ge=1, le=50, description="Maximum number of related objects"),
    session_data = Depends(get_authenticated_session)
):
    """Get objects related to the specified object (same project, world, or tags)"""
    try:
        session, session_id = session_data
        user_id = session.user_id
        
        # Get the source object
        source_obj = await dungeonmind_db.get_object(object_id, user_id)
        if not source_obj:
            raise HTTPException(status_code=404, detail="Object not found")
        
        # Find related objects
        related_objects = []
        
        # Objects in same project
        if source_obj.projectId:
            project_objects = await dungeonmind_db.get_user_objects(
                user_id=user_id,
                project_id=source_obj.projectId,
                limit=limit
            )
            related_objects.extend([obj for obj in project_objects if obj.id != object_id])
        
        # Objects in same world (if not already from project)
        if source_obj.worldId and len(related_objects) < limit:
            world_objects = await dungeonmind_db.get_user_objects(
                user_id=user_id,
                world_id=source_obj.worldId,
                limit=limit - len(related_objects)
            )
            for obj in world_objects:
                if obj.id != object_id and obj.id not in [r.id for r in related_objects]:
                    related_objects.append(obj)
        
        # Limit results
        related_objects = related_objects[:limit]
        
        return {
            "success": True,
            "source_object": source_obj.dict(),
            "related_objects": [obj.dict() for obj in related_objects],
            "total": len(related_objects)
        }
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get related objects for {object_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Object versioning endpoints
@router.get("/{object_id}/versions", response_model=dict)
async def get_object_versions(
    object_id: str,
    session_data = Depends(get_authenticated_session)
):
    """Get version history for an object"""
    try:
        session, session_id = session_data
        user_id = session.user_id
        
        obj = await dungeonmind_db.get_object(object_id, user_id)
        if not obj:
            raise HTTPException(status_code=404, detail="Object not found")
        
        return {
            "success": True,
            "object_id": object_id,
            "current_version": obj.version,
            "version_history": [v.dict() for v in obj.versionHistory],
            "total_versions": len(obj.versionHistory) + 1  # +1 for current version
        }
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get versions for object {object_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Object analytics endpoints  
@router.get("/{object_id}/analytics", response_model=dict)
async def get_object_analytics(
    object_id: str,
    session_data = Depends(get_authenticated_session)
):
    """Get analytics data for an object"""
    try:
        session, session_id = session_data
        user_id = session.user_id
        
        obj = await dungeonmind_db.get_object(object_id, user_id)
        if not obj:
            raise HTTPException(status_code=404, detail="Object not found")
        
        # Only owners can see detailed analytics
        if obj.ownedBy != user_id:
            raise HTTPException(status_code=403, detail="Analytics only available to object owner")
        
        return {
            "success": True,
            "object_id": object_id,
            "analytics": {
                "total_accesses": obj.accessCount,
                "last_accessed": obj.lastAccessedAt,
                "created_at": obj.createdAt,
                "updated_at": obj.updatedAt,
                "current_version": obj.version,
                "total_versions": len(obj.versionHistory) + 1
            }
        }
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get analytics for object {object_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 