"""
Database Access Layer for DungeonMind Objects
Handles all CRUD operations for global objects with permissions and analytics
"""

from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timedelta
import logging
import uuid
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from firestore.firebase_config import db
from models.dungeonmind_objects import (
    DungeonMindObject, ObjectType, Visibility, 
    DungeonMindWorld, DungeonMindProject,
    CreateObjectRequest, UpdateObjectRequest, ObjectSearchRequest
)

logger = logging.getLogger(__name__)


class PermissionError(Exception):
    """Raised when user lacks permission for requested operation"""
    pass


class DungeonMindObjectsDB:
    """Database access layer for DungeonMind objects with full permission management"""
    
    def __init__(self):
        self.db = db
        self.objects_collection = self.db.collection('dungeonmind-objects')
        self.worlds_collection = self.db.collection('worlds')
        self.projects_collection = self.db.collection('projects')
        self.analytics_collection = self.db.collection('analytics')
        
    async def save_object(self, obj: DungeonMindObject) -> str:
        """Save a DungeonMind object to Firestore"""
        try:
            # Validate object schema
            self._validate_object(obj)
            
            # Update timestamp
            obj.update_timestamp()
            
            # Convert to dictionary for Firestore
            obj_dict = obj.dict()
            
            # Convert datetime objects to ISO strings for Firestore
            obj_dict = self._prepare_for_firestore(obj_dict)
            
            # Save to Firestore
            doc_ref = self.objects_collection.document(obj.id)
            doc_ref.set(obj_dict)
            
            # Update analytics
            await self._update_analytics(obj.createdBy, 'object_created', obj.type.value)
            
            logger.info(f"Saved object {obj.id} of type {obj.type}")
            return obj.id
            
        except Exception as e:
            logger.error(f"Failed to save object {obj.id}: {e}")
            raise
    
    async def get_object(self, object_id: str, user_id: str) -> Optional[DungeonMindObject]:
        """Retrieve an object with permission checking"""
        try:
            doc = self.objects_collection.document(object_id).get()
            
            if not doc.exists:
                logger.warning(f"Object {object_id} not found")
                return None
                
            obj_data = doc.to_dict()
            obj_data = self._restore_from_firestore(obj_data)
            obj = DungeonMindObject(**obj_data)
            
            # Check permissions
            if not obj.can_read(user_id):
                logger.warning(f"User {user_id} denied read access to object {object_id}")
                raise PermissionError(f"User {user_id} cannot read object {object_id}")
            
            # Update access analytics
            await self._update_object_access(object_id, user_id)
            obj.increment_access_count()
            
            # Save updated access count back to Firestore
            self.objects_collection.document(object_id).update({
                'accessCount': obj.accessCount,
                'lastAccessedAt': obj.lastAccessedAt
            })
            
            logger.debug(f"Retrieved object {object_id} for user {user_id}")
            return obj
            
        except PermissionError:
            raise
        except Exception as e:
            logger.error(f"Failed to get object {object_id}: {e}")
            raise
    
    async def update_object(
        self, 
        object_id: str, 
        updates: UpdateObjectRequest, 
        user_id: str
    ) -> bool:
        """Update an existing object with permission checking"""
        try:
            # Get existing object
            existing_obj = await self.get_object(object_id, user_id)
            if not existing_obj:
                return False
            
            # Check write permissions
            if not existing_obj.can_write(user_id):
                raise PermissionError(f"User {user_id} cannot write to object {object_id}")
            
            # Create version snapshot before updating
            changes_description = self._describe_changes(existing_obj, updates)
            if changes_description:
                existing_obj.add_version(
                    changes=changes_description,
                    changed_by=user_id,
                    data_snapshot=existing_obj.dict()
                )
            
            # Apply updates
            update_dict = {}
            for field, value in updates.dict(exclude_unset=True).items():
                if value is not None:
                    setattr(existing_obj, field, value)
                    update_dict[field] = value
            
            # Update timestamp
            existing_obj.update_timestamp()
            update_dict['updatedAt'] = existing_obj.updatedAt
            update_dict['version'] = existing_obj.version
            update_dict['versionHistory'] = [v.dict() for v in existing_obj.versionHistory]
            
            # Save to Firestore
            update_dict = self._prepare_for_firestore(update_dict)
            self.objects_collection.document(object_id).update(update_dict)
            
            logger.info(f"Updated object {object_id} by user {user_id}")
            return True
            
        except PermissionError:
            raise
        except Exception as e:
            logger.error(f"Failed to update object {object_id}: {e}")
            raise
    
    async def delete_object(self, object_id: str, user_id: str) -> bool:
        """Delete an object with permission checking"""
        try:
            # Get existing object to check permissions
            existing_obj = await self.get_object(object_id, user_id)
            if not existing_obj:
                return False
            
            # Check admin permissions (required for deletion)
            if not existing_obj.can_admin(user_id):
                raise PermissionError(f"User {user_id} cannot delete object {object_id}")
            
            # Delete from Firestore
            self.objects_collection.document(object_id).delete()
            
            # Update analytics
            await self._update_analytics(user_id, 'object_deleted', existing_obj.type.value)
            
            logger.info(f"Deleted object {object_id} by user {user_id}")
            return True
            
        except PermissionError:
            raise
        except Exception as e:
            logger.error(f"Failed to delete object {object_id}: {e}")
            raise
    
    async def get_user_objects(
        self, 
        user_id: str, 
        object_type: Optional[ObjectType] = None,
        world_id: Optional[str] = None,
        project_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[DungeonMindObject]:
        """Get objects owned by or shared with a user"""
        try:
            # Build query for objects user can access
            query = self.objects_collection
            
            # Filter by owned objects
            owned_query = query.where('ownedBy', '==', user_id)
            
            # Filter by shared objects
            shared_query = query.where('sharedWith', 'array_contains', user_id)
            
            # Filter by public objects
            public_query = query.where('visibility', '==', 'public')
            
            # Apply additional filters
            if object_type:
                owned_query = owned_query.where('type', '==', object_type.value)
                shared_query = shared_query.where('type', '==', object_type.value)
                public_query = public_query.where('type', '==', object_type.value)
                
            if world_id:
                owned_query = owned_query.where('worldId', '==', world_id)
                shared_query = shared_query.where('worldId', '==', world_id)
                public_query = public_query.where('worldId', '==', world_id)
                
            if project_id:
                owned_query = owned_query.where('projectId', '==', project_id)
                shared_query = shared_query.where('projectId', '==', project_id)
                public_query = public_query.where('projectId', '==', project_id)
            
            # Order by update time
            owned_query = owned_query.order_by('updatedAt', direction=firestore.Query.DESCENDING)
            shared_query = shared_query.order_by('updatedAt', direction=firestore.Query.DESCENDING)
            public_query = public_query.order_by('updatedAt', direction=firestore.Query.DESCENDING)
            
            # Execute queries
            owned_docs = list(owned_query.limit(limit).offset(offset).stream())
            shared_docs = list(shared_query.limit(limit).offset(offset).stream())
            public_docs = list(public_query.limit(limit).offset(offset).stream())
            
            # Combine and deduplicate results
            all_docs = owned_docs + shared_docs + public_docs
            seen_ids = set()
            unique_docs = []
            
            for doc in all_docs:
                if doc.id not in seen_ids:
                    seen_ids.add(doc.id)
                    unique_docs.append(doc)
            
            # Convert to objects
            objects = []
            for doc in unique_docs[:limit]:  # Respect limit after deduplication
                try:
                    obj_data = self._restore_from_firestore(doc.to_dict())
                    obj = DungeonMindObject(**obj_data)
                    
                    # Double-check permissions
                    if obj.can_read(user_id):
                        objects.append(obj)
                        
                except Exception as e:
                    logger.warning(f"Failed to parse object {doc.id}: {e}")
                    continue
            
            logger.debug(f"Retrieved {len(objects)} objects for user {user_id}")
            return objects
            
        except Exception as e:
            logger.error(f"Failed to get user objects for {user_id}: {e}")
            raise
    
    async def search_objects(
        self,
        search_request: ObjectSearchRequest,
        user_id: str
    ) -> List[DungeonMindObject]:
        """Search objects with text matching and filters"""
        try:
            # Start with accessible objects query
            query = self.objects_collection
            
            # Apply filters
            if search_request.type:
                query = query.where('type', '==', search_request.type.value)
            if search_request.worldId:
                query = query.where('worldId', '==', search_request.worldId)
            if search_request.projectId:
                query = query.where('projectId', '==', search_request.projectId)
            if search_request.visibility:
                query = query.where('visibility', '==', search_request.visibility.value)
            
            # Get more docs than needed for text filtering
            docs = list(query.limit(search_request.limit * 3).stream())
            
            # Client-side filtering for text and permissions
            results = []
            query_lower = search_request.query.lower() if search_request.query else ""
            
            for doc in docs:
                try:
                    obj_data = self._restore_from_firestore(doc.to_dict())
                    obj = DungeonMindObject(**obj_data)
                    
                    # Check permissions
                    if not obj.can_read(user_id):
                        continue
                    
                    # Text matching
                    if search_request.query:
                        text_matches = (
                            query_lower in obj.name.lower() or
                            query_lower in obj.description.lower() or
                            any(query_lower in tag.lower() for tag in obj.tags)
                        )
                        if not text_matches:
                            continue
                    
                    # Tag filtering
                    if search_request.tags:
                        if not any(tag in obj.tags for tag in search_request.tags):
                            continue
                    
                    results.append(obj)
                    
                    if len(results) >= search_request.limit:
                        break
                        
                except Exception as e:
                    logger.warning(f"Failed to parse search result {doc.id}: {e}")
                    continue
            
            logger.debug(f"Search returned {len(results)} objects for user {user_id}")
            return results
            
        except Exception as e:
            logger.error(f"Failed to search objects: {e}")
            raise
    
    async def create_object_from_request(
        self, 
        request: CreateObjectRequest, 
        user_id: str
    ) -> DungeonMindObject:
        """Create a new object from a request"""
        try:
            # Create the object
            obj = DungeonMindObject(
                type=request.type,
                createdBy=user_id,
                ownedBy=user_id,
                name=request.name,
                description=request.description,
                tags=request.tags,
                worldId=request.worldId,
                projectId=request.projectId,
                visibility=request.visibility,
                itemData=request.itemData,
                storeData=request.storeData,
                statblockData=request.statblockData,
                ruleData=request.ruleData,
                spellData=request.spellData
            )
            
            # Save to database
            await self.save_object(obj)
            
            logger.info(f"Created new {request.type} object {obj.id} for user {user_id}")
            return obj
            
        except Exception as e:
            logger.error(f"Failed to create object from request: {e}")
            raise
    
    def _validate_object(self, obj: DungeonMindObject):
        """Validate object before saving"""
        if not obj.name.strip():
            raise ValueError("Object name cannot be empty")
            
        if not obj.createdBy:
            raise ValueError("Object must have a creator")
            
        if not obj.ownedBy:
            raise ValueError("Object must have an owner")
        
        # Validate tool-specific data exists and matches type
        tool_data_count = sum([
            bool(obj.itemData),
            bool(obj.storeData),
            bool(obj.statblockData),
            bool(obj.ruleData),
            bool(obj.spellData)
        ])
        
        if tool_data_count != 1:
            raise ValueError("Object must have exactly one tool-specific data field")
    
    def _prepare_for_firestore(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare data for Firestore storage (handle datetime objects)"""
        prepared = {}
        
        for key, value in data.items():
            if isinstance(value, datetime):
                prepared[key] = value.isoformat()
            elif isinstance(value, dict):
                prepared[key] = self._prepare_for_firestore(value)
            elif isinstance(value, list):
                prepared[key] = [
                    self._prepare_for_firestore(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                prepared[key] = value
                
        return prepared
    
    def _restore_from_firestore(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Restore data from Firestore (convert ISO strings back to datetime)"""
        restored = {}
        
        # Fields that should be datetime objects
        datetime_fields = {
            'createdAt', 'updatedAt', 'lastAccessedAt', 
            'last_updated', 'created_at', 'expires_at'
        }
        
        for key, value in data.items():
            if key in datetime_fields and isinstance(value, str):
                try:
                    restored[key] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                except ValueError:
                    restored[key] = value
            elif isinstance(value, dict):
                restored[key] = self._restore_from_firestore(value)
            elif isinstance(value, list):
                restored[key] = [
                    self._restore_from_firestore(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                restored[key] = value
                
        return restored
    
    def _describe_changes(self, existing_obj: DungeonMindObject, updates: UpdateObjectRequest) -> str:
        """Generate a description of changes being made"""
        changes = []
        
        for field, value in updates.dict(exclude_unset=True).items():
            if value is not None:
                old_value = getattr(existing_obj, field, None)
                if old_value != value:
                    changes.append(f"Updated {field}")
        
        return ", ".join(changes) if changes else ""
    
    async def _update_analytics(self, user_id: str, action: str, object_type: str):
        """Update analytics for user actions"""
        try:
            # Update user activity
            user_activity_ref = self.analytics_collection.document('user-activity').collection(user_id).document('summary')
            user_activity_ref.set({
                f'actions.{action}': firestore.Increment(1),
                f'object_types.{object_type}': firestore.Increment(1),
                'last_activity': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat()
            }, merge=True)
            
            # Update global analytics
            global_analytics_ref = self.analytics_collection.document('global-stats')
            global_analytics_ref.set({
                f'actions.{action}': firestore.Increment(1),
                f'object_types.{object_type}': firestore.Increment(1),
                'updated_at': datetime.utcnow().isoformat()
            }, merge=True)
            
        except Exception as e:
            logger.warning(f"Failed to update analytics: {e}")
    
    async def _update_object_access(self, object_id: str, user_id: str):
        """Update object access analytics"""
        try:
            access_ref = self.analytics_collection.document('object-access').collection(object_id).document('summary')
            access_ref.set({
                'total_accesses': firestore.Increment(1),
                'last_accessed': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat(),
                f'users.{user_id}': firestore.Increment(1)
            }, merge=True)
            
        except Exception as e:
            logger.warning(f"Failed to update object access analytics: {e}")


# Create global database instance
dungeonmind_db = DungeonMindObjectsDB() 