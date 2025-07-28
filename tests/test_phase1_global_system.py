"""
Phase 1 Implementation Tests
Tests for Global Data Schema and Session Integration
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, patch
from models.dungeonmind_objects import (
    DungeonMindObject, ObjectType, Visibility, ItemCardData,
    CreateObjectRequest, GenerationState, StepId
)
from models.session_models import (
    EnhancedGlobalSession, CardGeneratorSessionState,
    GlobalSessionPreferences
)
from session_management import EnhancedGlobalSessionManager
from database.dungeonmind_objects_db import DungeonMindObjectsDB


class TestGlobalDataSchema:
    """Test the global data schema models"""
    
    def test_dungeonmind_object_creation(self):
        """Test creating a basic DungeonMind object"""
        item_data = ItemCardData(
            itemType="Weapon",
            rarity="rare",
            value="1000 gp",
            properties=["Finesse", "Light"],
            damageFormula="1d8+1",
            damageType="Slashing"
        )
        
        obj = DungeonMindObject(
            type=ObjectType.ITEM,
            createdBy="test_user_123",
            ownedBy="test_user_123",
            name="Test Sword",
            description="A test magic sword",
            tags=["weapon", "magic", "test"],
            itemData=item_data
        )
        
        assert obj.type == ObjectType.ITEM
        assert obj.name == "Test Sword"
        assert obj.itemData.itemType == "Weapon"
        assert obj.itemData.rarity == "rare"
        assert "weapon" in obj.tags
        assert obj.can_read("test_user_123")
        assert obj.can_write("test_user_123")
        assert obj.can_admin("test_user_123")
        
    def test_object_permissions(self):
        """Test object permission system"""
        obj = DungeonMindObject(
            type=ObjectType.ITEM,
            createdBy="owner_123",
            ownedBy="owner_123",
            name="Private Item",
            description="A private test item",
            visibility=Visibility.PRIVATE,
            itemData=ItemCardData(itemType="Tool", rarity="common")
        )
        
        # Owner can do everything
        assert obj.can_read("owner_123")
        assert obj.can_write("owner_123")
        assert obj.can_admin("owner_123")
        
        # Other users cannot access private object
        assert not obj.can_read("other_user")
        assert not obj.can_write("other_user")
        assert not obj.can_admin("other_user")
        
        # Test sharing
        obj.sharedWith.append("shared_user")
        assert obj.can_read("shared_user")
        assert not obj.can_write("shared_user")  # Only read access by default
        
        # Test public visibility
        obj.visibility = Visibility.PUBLIC
        assert obj.can_read("any_user")
        assert not obj.can_write("any_user")  # Still no write access

    def test_version_management(self):
        """Test object versioning"""
        obj = DungeonMindObject(
            type=ObjectType.ITEM,
            createdBy="test_user",
            ownedBy="test_user",
            name="Versioned Item",
            description="Original description",
            itemData=ItemCardData(itemType="Weapon", rarity="common")
        )
        
        assert obj.version == 1
        assert len(obj.versionHistory) == 0
        
        # Add a version
        original_data = obj.model_dump()
        obj.add_version("Updated description", "test_user", original_data)
        
        assert obj.version == 2
        assert len(obj.versionHistory) == 1
        assert obj.versionHistory[0].changes == "Updated description"
        assert obj.versionHistory[0].changedBy == "test_user"


class TestEnhancedSessionManager:
    """Test the enhanced global session manager"""
    
    def test_session_creation(self):
        """Test creating a new session"""
        manager = EnhancedGlobalSessionManager()
        
        session_id = manager.create_session(user_id="test_user", platform="web")
        
        assert session_id is not None
        assert session_id in manager.sessions
        
        session = manager.get_session(session_id)
        assert session is not None
        assert session.user_id == "test_user"
        assert session.platform == "web"
        assert not session.is_expired()
        
    def test_cardgenerator_state_management(self):
        """Test CardGenerator state updates"""
        manager = EnhancedGlobalSessionManager()
        session_id = manager.create_session(user_id="test_user")
        
        # Update CardGenerator state
        updates = {
            "current_step": StepId.CORE_IMAGE,
            "active_item_id": "test_item_123",
            "draft_item_data": {"name": "Test Item"},
            "generation_locks": {"image_generation": True}
        }
        
        result = asyncio.run(manager.update_cardgenerator_state(session_id, updates))
        assert result is True
        
        session = manager.get_session(session_id)
        assert session.cardgenerator is not None
        assert session.cardgenerator.current_step == StepId.CORE_IMAGE
        assert session.cardgenerator.active_item_id == "test_item_123"
        assert "test_item_123" in session.recently_viewed
        
    def test_cross_tool_features(self):
        """Test cross-tool clipboard and recently viewed"""
        manager = EnhancedGlobalSessionManager()
        session_id = manager.create_session(user_id="test_user")
        session = manager.get_session(session_id)
        
        # Test clipboard
        session.add_to_clipboard("item_1")
        session.add_to_clipboard("item_2")
        assert len(session.clipboard) == 2
        assert "item_1" in session.clipboard
        
        # Test recently viewed
        session.add_to_recently_viewed("item_3")
        session.add_to_recently_viewed("item_4")
        assert len(session.recently_viewed) == 2
        assert session.recently_viewed[0] == "item_4"  # Most recent first
        
        # Test pinning
        session.pin_object("item_1")
        assert "item_1" in session.pinned_objects
        
    def test_session_expiration(self):
        """Test session expiration handling"""
        manager = EnhancedGlobalSessionManager(session_timeout_hours=0)  # Immediate expiration
        session_id = manager.create_session()
        
        # Session should exist initially
        session = manager.get_session(session_id)
        assert session is not None
        
        # Force expiration
        session.expires_at = datetime.now()
        
        # Session should be cleaned up
        expired_session = manager.get_session(session_id)
        assert expired_session is None
        assert session_id not in manager.sessions


class TestGlobalObjectDatabase:
    """Test the global object database integration"""
    
    @pytest.fixture
    def mock_firestore(self):
        """Mock Firestore for testing"""
        with patch('database.dungeonmind_objects_db.db') as mock_db:
            # Setup mock collection
            mock_collection = Mock()
            mock_document = Mock()
            mock_db.collection.return_value = mock_collection
            mock_collection.document.return_value = mock_document
            
            yield mock_db, mock_collection, mock_document
    
    def test_object_creation_flow(self, mock_firestore):
        """Test complete object creation flow"""
        mock_db, mock_collection, mock_document = mock_firestore
        
        # Setup mock responses
        mock_document.set.return_value = None
        
        db = DungeonMindObjectsDB()
        
        # Create test object
        obj = DungeonMindObject(
            type=ObjectType.ITEM,
            createdBy="test_user",
            ownedBy="test_user",
            name="Test Item",
            description="A test item",
            itemData=ItemCardData(itemType="Weapon", rarity="common")
        )
        
        # This would normally hit Firestore, but we're mocking it
        # Just test that the validation passes
        db._validate_object(obj)
        
        # Should not raise any exceptions
        assert obj.name == "Test Item"
        assert obj.type == ObjectType.ITEM
        
    def test_permission_validation(self):
        """Test database permission checking"""
        db = DungeonMindObjectsDB()
        
        obj = DungeonMindObject(
            type=ObjectType.ITEM,
            createdBy="owner",
            ownedBy="owner",
            name="Test",
            description="Test",
            itemData=ItemCardData(itemType="Tool", rarity="common")
        )
        
        # Test validation
        db._validate_object(obj)  # Should pass
        
        # Test invalid object (Pydantic validates at creation time now)
        with pytest.raises(ValueError):  # Pydantic validation error
            invalid_obj = DungeonMindObject(
                type=ObjectType.ITEM,
                createdBy="owner",
                ownedBy="owner",
                name="",  # Empty name should fail
                description="Test",
                itemData=ItemCardData(itemType="Tool", rarity="common")
            )


class TestIntegrationFlow:
    """Test complete integration between session management and object database"""
    
    def test_cardgenerator_workflow(self):
        """Test a complete CardGenerator workflow"""
        # 1. Create session
        manager = EnhancedGlobalSessionManager()
        session_id = manager.create_session(user_id="test_user")
        session = manager.get_session(session_id)
        
        # 2. Start CardGenerator workflow
        initial_updates = {
            "current_step": StepId.TEXT_GENERATION,
            "draft_item_data": {
                "name": "Magic Sword",
                "type": "Weapon",
                "description": "A glowing blade"
            }
        }
        
        result = asyncio.run(manager.update_cardgenerator_state(session_id, initial_updates))
        assert result is True
        
        # 3. Progress through steps
        step2_updates = {
            "current_step": StepId.CORE_IMAGE,
            "generated_images": ["image_url_1", "image_url_2"],
            "step_completion": {
                StepId.TEXT_GENERATION.value: True,
                StepId.CORE_IMAGE.value: False
            }
        }
        
        result = asyncio.run(manager.update_cardgenerator_state(session_id, step2_updates))
        assert result is True
        
        # 4. Verify session state
        updated_session = manager.get_session(session_id)
        assert updated_session.cardgenerator.current_step == StepId.CORE_IMAGE
        assert len(updated_session.cardgenerator.generated_images) == 2
        
        # 5. Simulate saving as global object (would need actual database for full test)
        item_data = ItemCardData(
            itemType="Weapon",
            rarity="rare",
            generationState=GenerationState(
                currentStep=StepId.CORE_IMAGE,
                completedSteps=[StepId.TEXT_GENERATION]
            )
        )
        
        obj = DungeonMindObject(
            type=ObjectType.ITEM,
            createdBy="test_user",
            ownedBy="test_user",
            name="Magic Sword",
            description="A glowing blade",
            itemData=item_data
        )
        
        # Verify object structure
        assert obj.itemData.generationState.currentStep == StepId.CORE_IMAGE
        assert StepId.TEXT_GENERATION in obj.itemData.generationState.completedSteps
        
    def test_cross_tool_object_sharing(self):
        """Test sharing objects between tools"""
        manager = EnhancedGlobalSessionManager()
        session_id = manager.create_session(user_id="test_user")
        session = manager.get_session(session_id)
        
        # Simulate CardGenerator creating an item
        item_id = "item_123"
        cardgen_updates = {
            "active_item_id": item_id,
            "recent_items": [item_id]
        }
        
        asyncio.run(manager.update_cardgenerator_state(session_id, cardgen_updates))
        
        # Add to clipboard for cross-tool sharing
        session.add_to_clipboard(item_id)
        
        # Simulate StoreGenerator accessing the item
        storegen_updates = {
            "active_store_id": "store_456",
            "session_data": {"clipboard_items": [item_id]}
        }
        
        result = asyncio.run(manager.update_tool_state(session_id, "storegenerator", storegen_updates))
        assert result is True
        
        # Verify cross-tool state
        updated_session = manager.get_session(session_id)
        assert item_id in updated_session.clipboard
        assert item_id in updated_session.recently_viewed
        assert updated_session.cardgenerator.active_item_id == item_id
        assert updated_session.storegenerator is not None


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"]) 