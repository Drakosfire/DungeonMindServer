"""
Enhanced Session Models for Global Session Management
Supports CardGenerator and future tool integrations
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from models.dungeonmind_objects import StepId


class ToolSessionState(BaseModel):
    """Base class for tool-specific session state"""
    last_updated: datetime = Field(default_factory=datetime.now, description="Last time this tool state was updated")
    active_object_id: Optional[str] = Field(None, description="Currently active object ID")
    session_data: Dict[str, Any] = Field(default_factory=dict, description="Tool-specific session data")

    class Config:
        arbitrary_types_allowed = True


class CardGeneratorSessionState(ToolSessionState):
    """CardGenerator-specific session state"""
    current_step: StepId = Field(default=StepId.TEXT_GENERATION, description="Current generation step")
    active_item_id: Optional[str] = Field(None, description="Currently active item object ID")
    draft_item_data: Optional[Dict[str, Any]] = Field(None, description="Unsaved item data")
    generation_locks: Dict[str, bool] = Field(default_factory=dict, description="Active generation locks")
    step_completion: Dict[str, bool] = Field(default_factory=dict, description="Completion status of each step")
    
    # Quick access to recent work
    recent_items: List[str] = Field(default_factory=list, description="Recently worked on item IDs")
    current_project_id: Optional[str] = Field(None, description="Currently active project")
    
    # Generation preferences and state
    preferences: Dict[str, Any] = Field(default_factory=dict, description="User preferences for card generation")
    
    # Visual asset tracking
    generated_images: List[str] = Field(default_factory=list, description="URLs of generated images")
    selected_assets: Dict[str, str] = Field(default_factory=dict, description="Selected visual assets")


class StoreGeneratorSessionState(ToolSessionState):
    """StoreGenerator-specific session state (placeholder for future expansion)"""
    active_store_id: Optional[str] = Field(None, description="Currently active store object ID")
    store_draft_data: Optional[Dict[str, Any]] = Field(None, description="Unsaved store data")
    recent_stores: List[str] = Field(default_factory=list, description="Recently worked on store IDs")


class StatblockGeneratorSessionState(ToolSessionState):
    """StatblockGenerator-specific session state (placeholder for future expansion)"""
    active_statblock_id: Optional[str] = Field(None, description="Currently active statblock object ID")
    statblock_draft_data: Optional[Dict[str, Any]] = Field(None, description="Unsaved statblock data")
    recent_statblocks: List[str] = Field(default_factory=list, description="Recently worked on statblock IDs")


class RulesLawyerSessionState(ToolSessionState):
    """RulesLawyer-specific session state"""
    active_query_history: List[Dict[str, Any]] = Field(default_factory=list, description="Recent queries and responses")
    favorite_rules: List[str] = Field(default_factory=list, description="Bookmarked rule IDs")
    search_context: Dict[str, Any] = Field(default_factory=dict, description="Current search context")


class GlobalSessionPreferences(BaseModel):
    """Global user preferences across all tools"""
    default_ai_model: str = Field(default='gpt-4o', description="Preferred AI model")
    auto_save_interval: int = Field(default=30, description="Auto-save interval in seconds")
    show_ai_confidence: bool = Field(default=True, description="Show AI confidence scores")
    enable_cross_tool_suggestions: bool = Field(default=True, description="Enable suggestions across tools")
    theme: str = Field(default='light', description="UI theme preference")
    language: str = Field(default='en', description="Language preference")
    
    # Collaboration preferences
    default_object_visibility: str = Field(default='private', description="Default visibility for new objects")
    auto_share_with_world: bool = Field(default=False, description="Auto-share objects with active world")
    notify_on_shared_updates: bool = Field(default=True, description="Notify when shared objects are updated")


class EnhancedGlobalSession(BaseModel):
    """Enhanced global session with tool-specific states and cross-tool features"""
    
    # Session identity
    session_id: str = Field(..., description="Unique session identifier")
    user_id: Optional[str] = Field(None, description="User ID if authenticated")
    created_at: datetime = Field(default_factory=datetime.now, description="Session creation time")
    last_accessed: datetime = Field(default_factory=datetime.now, description="Last access time")
    expires_at: datetime = Field(default_factory=lambda: datetime.now() + timedelta(hours=24), description="Session expiration time")
    
    # Tool-specific states
    cardgenerator: Optional[CardGeneratorSessionState] = Field(None, description="CardGenerator state")
    storegenerator: Optional[StoreGeneratorSessionState] = Field(None, description="StoreGenerator state")
    ruleslawyer: Optional[RulesLawyerSessionState] = Field(None, description="RulesLawyer state")
    statblockgenerator: Optional[StatblockGeneratorSessionState] = Field(None, description="StatblockGenerator state")
    
    # Global context
    active_world_id: Optional[str] = Field(None, description="Currently active world/campaign")
    active_project_id: Optional[str] = Field(None, description="Currently active project")
    current_tool: str = Field(default='cardgenerator', description="Currently active tool")
    
    # Cross-tool features
    clipboard: List[str] = Field(default_factory=list, description="Object IDs in cross-tool clipboard")
    recently_viewed: List[str] = Field(default_factory=list, description="Recently viewed objects across all tools")
    pinned_objects: List[str] = Field(default_factory=list, description="User-pinned objects for quick access")
    
    # Global preferences
    preferences: GlobalSessionPreferences = Field(default_factory=GlobalSessionPreferences, description="User preferences")
    
    # Session metadata
    ip_address: Optional[str] = Field(None, description="Client IP address")
    user_agent: Optional[str] = Field(None, description="Client user agent")
    platform: str = Field(default='web', description="Platform (web, mobile, desktop)")

    class Config:
        arbitrary_types_allowed = True

    def update_access_time(self):
        """Update the last accessed timestamp"""
        self.last_accessed = datetime.now()

    def is_expired(self) -> bool:
        """Check if session has expired"""
        return datetime.now() > self.expires_at

    def extend_expiration(self, hours: int = 24):
        """Extend session expiration time"""
        self.expires_at = datetime.now() + timedelta(hours=hours)
        self.update_access_time()

    def get_tool_state(self, tool_name: str) -> Optional[ToolSessionState]:
        """Get state for a specific tool"""
        tool_states = {
            'cardgenerator': self.cardgenerator,
            'storegenerator': self.storegenerator,
            'ruleslawyer': self.ruleslawyer,
            'statblockgenerator': self.statblockgenerator
        }
        return tool_states.get(tool_name)

    def set_tool_state(self, tool_name: str, state: ToolSessionState):
        """Set state for a specific tool"""
        if tool_name == 'cardgenerator' and isinstance(state, CardGeneratorSessionState):
            self.cardgenerator = state
        elif tool_name == 'storegenerator' and isinstance(state, StoreGeneratorSessionState):
            self.storegenerator = state
        elif tool_name == 'ruleslawyer' and isinstance(state, RulesLawyerSessionState):
            self.ruleslawyer = state
        elif tool_name == 'statblockgenerator' and isinstance(state, StatblockGeneratorSessionState):
            self.statblockgenerator = state
        else:
            raise ValueError(f"Invalid tool name or state type: {tool_name}")

    def add_to_recently_viewed(self, object_id: str):
        """Add object to recently viewed list"""
        if object_id in self.recently_viewed:
            self.recently_viewed.remove(object_id)
        self.recently_viewed.insert(0, object_id)
        # Keep only last 50 items
        self.recently_viewed = self.recently_viewed[:50]

    def add_to_clipboard(self, object_id: str):
        """Add object to cross-tool clipboard"""
        if object_id not in self.clipboard:
            self.clipboard.append(object_id)
        # Keep only last 10 items in clipboard
        self.clipboard = self.clipboard[-10:]

    def remove_from_clipboard(self, object_id: str):
        """Remove object from clipboard"""
        if object_id in self.clipboard:
            self.clipboard.remove(object_id)

    def pin_object(self, object_id: str):
        """Pin object for quick access"""
        if object_id not in self.pinned_objects:
            self.pinned_objects.append(object_id)

    def unpin_object(self, object_id: str):
        """Unpin object"""
        if object_id in self.pinned_objects:
            self.pinned_objects.remove(object_id)

    def switch_world(self, world_id: Optional[str]):
        """Switch active world context"""
        self.active_world_id = world_id
        self.update_access_time()

    def switch_project(self, project_id: Optional[str]):
        """Switch active project context"""
        self.active_project_id = project_id
        self.update_access_time()

    def switch_tool(self, tool_name: str):
        """Switch active tool"""
        valid_tools = ['cardgenerator', 'storegenerator', 'ruleslawyer', 'statblockgenerator']
        if tool_name in valid_tools:
            self.current_tool = tool_name
            self.update_access_time()


class SessionStatus(BaseModel):
    """Session status information"""
    active: bool = Field(..., description="Whether session is active")
    expires_at: datetime = Field(..., description="Session expiration time")
    last_accessed: datetime = Field(..., description="Last access timestamp")
    current_tool: str = Field(..., description="Currently active tool")
    active_world_id: Optional[str] = Field(None, description="Active world ID")
    active_project_id: Optional[str] = Field(None, description="Active project ID")
    
    # Tool states
    has_cardgenerator: bool = Field(default=False, description="Has CardGenerator state")
    has_storegenerator: bool = Field(default=False, description="Has StoreGenerator state")
    has_ruleslawyer: bool = Field(default=False, description="Has RulesLawyer state")
    has_statblockgenerator: bool = Field(default=False, description="Has StatblockGenerator state")
    
    # Cross-tool data
    clipboard_count: int = Field(default=0, description="Number of items in clipboard")
    recently_viewed_count: int = Field(default=0, description="Number of recently viewed items")
    pinned_objects_count: int = Field(default=0, description="Number of pinned objects")

    class Config:
        arbitrary_types_allowed = True


# Request/Response models for session API
class CreateSessionRequest(BaseModel):
    """Request to create a new session"""
    user_id: Optional[str] = Field(None, description="User ID if authenticated")
    platform: str = Field(default='web', description="Platform creating the session")
    preferences: Optional[GlobalSessionPreferences] = Field(None, description="Initial preferences")


class UpdateSessionRequest(BaseModel):
    """Request to update session data"""
    tool_name: str = Field(..., description="Tool to update")
    state_updates: Dict[str, Any] = Field(..., description="State updates to apply")


class RestoreSessionRequest(BaseModel):
    """Request to restore session state"""
    session_id: Optional[str] = Field(None, description="Session ID to restore")
    fallback_to_new: bool = Field(default=True, description="Create new session if restore fails")


class SessionResponse(BaseModel):
    """Response containing session information"""
    success: bool = Field(..., description="Whether operation succeeded")
    session_id: str = Field(..., description="Session ID")
    status: SessionStatus = Field(..., description="Session status")
    message: Optional[str] = Field(None, description="Additional message")


# Tool-specific update requests
class CardGeneratorUpdateRequest(BaseModel):
    """Update request for CardGenerator session state"""
    current_step: Optional[StepId] = None
    active_item_id: Optional[str] = None
    draft_item_data: Optional[Dict[str, Any]] = None
    generation_locks: Optional[Dict[str, bool]] = None
    step_completion: Optional[Dict[str, bool]] = None
    recent_items: Optional[List[str]] = None
    current_project_id: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None
    generated_images: Optional[List[str]] = None
    selected_assets: Optional[Dict[str, str]] = None 