"""
Global Data Schema for DungeonMind Objects
Foundation for cross-tool object sharing and collaboration
"""

from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator
import uuid


class ObjectType(str, Enum):
    """Types of objects that can be created in DungeonMind tools"""
    ITEM = 'item'
    STORE = 'store'
    STATBLOCK = 'statblock'
    RULE = 'rule'
    SPELL = 'spell'
    WORLD = 'world'
    PROJECT = 'project'


class Visibility(str, Enum):
    """Object visibility levels"""
    PRIVATE = 'private'      # Only owner can see
    SHARED = 'shared'        # Only specific users can see
    PUBLIC = 'public'        # Everyone can see


class ObjectPermissions(BaseModel):
    """Granular permissions for object access"""
    canRead: List[str] = Field(default_factory=list, description="User IDs with read access")
    canWrite: List[str] = Field(default_factory=list, description="User IDs with write access")
    canAdmin: List[str] = Field(default_factory=list, description="User IDs with admin access")
    isPublicReadable: bool = Field(default=False, description="Whether object is publicly readable")


class AIGenerationMetadata(BaseModel):
    """Metadata about AI generation process"""
    model: str = Field(..., description="AI model used for generation")
    prompt: str = Field(..., description="Prompt used for generation")
    negativePrompt: Optional[str] = Field(None, description="Negative prompt if used")
    seed: Optional[int] = Field(None, description="Random seed if used")
    generationTime: float = Field(..., description="Time taken to generate in seconds")
    tokensUsed: int = Field(..., description="Number of tokens consumed")
    confidence: Optional[float] = Field(None, description="AI confidence score 0-1")
    fallbackUsed: bool = Field(default=False, description="Whether fallback generation was used")


class ObjectVersion(BaseModel):
    """Version history for object changes"""
    version: int = Field(..., description="Version number")
    timestamp: str = Field(..., description="ISO timestamp of change")
    changes: str = Field(..., description="Description of changes made")
    changedBy: str = Field(..., description="User ID who made the change")
    data: Dict[str, Any] = Field(..., description="Snapshot of object data at this version")


# CardGenerator-specific schemas
class StepId(str, Enum):
    """CardGenerator step identifiers"""
    TEXT_GENERATION = 'text-generation'
    CORE_IMAGE = 'core-image'
    BORDER_GENERATION = 'border-generation'
    FINAL_ASSEMBLY = 'final-assembly'


class VisualAsset(BaseModel):
    """Visual asset data for cards"""
    url: str = Field(..., description="URL to the asset")
    prompt: Optional[str] = Field(None, description="Generation prompt if AI-generated")
    generationMetadata: Optional[AIGenerationMetadata] = Field(None, description="AI generation details")


class BorderStyle(BaseModel):
    """Card border/template style"""
    id: str = Field(..., description="Unique border style ID")
    name: str = Field(..., description="Human-readable name")
    previewUrl: str = Field(..., description="URL to preview image")


class FinalCard(BaseModel):
    """Final assembled card data"""
    url: str = Field(..., description="URL to final card image")
    dimensions: Dict[str, int] = Field(..., description="Width and height of card")
    createdAt: str = Field(..., description="ISO timestamp of creation")


class GenerationState(BaseModel):
    """Current state of the generation workflow"""
    completedSteps: List[StepId] = Field(default_factory=list, description="Steps that have been completed")
    currentStep: StepId = Field(default=StepId.TEXT_GENERATION, description="Currently active step")
    canAdvanceToStep: Dict[StepId, bool] = Field(default_factory=dict, description="Which steps are available")
    lastSavedStep: StepId = Field(default=StepId.TEXT_GENERATION, description="Last step that was saved")


class ItemCardData(BaseModel):
    """Complete data for a magic item card"""
    # Basic item properties
    itemType: str = Field(..., description="Type of item (Weapon, Armor, etc.)")
    rarity: str = Field(..., description="Item rarity level")
    value: str = Field(default="", description="Monetary value or description")
    weight: str = Field(default="", description="Weight description")
    
    # Mechanical properties
    properties: List[str] = Field(default_factory=list, description="Item properties like Finesse, Light")
    damageFormula: Optional[str] = Field(None, description="Damage dice formula")
    damageType: Optional[str] = Field(None, description="Type of damage dealt")
    armorClass: Optional[str] = Field(None, description="Armor class provided")
    requirements: Optional[str] = Field(None, description="Requirements to use item")
    
    # Flavor and presentation
    quote: Optional[str] = Field(None, description="Flavor text quote")
    lore: Optional[str] = Field(None, description="Extended background lore")
    
    # Visual assets
    visualAssets: Dict[str, Any] = Field(default_factory=dict, description="Visual assets for the card")
    
    # Generation workflow state
    generationState: GenerationState = Field(default_factory=GenerationState, description="Current generation state")
    
    # System compatibility data
    systemData: Dict[str, Any] = Field(default_factory=dict, description="System-specific data (D&D 5e, PF2e, etc.)")

    @validator('rarity')
    def validate_rarity(cls, v):
        valid_rarities = ['common', 'uncommon', 'rare', 'very rare', 'legendary', 'artifact']
        if v.lower() not in valid_rarities:
            raise ValueError(f"Rarity must be one of: {', '.join(valid_rarities)}")
        return v.lower()


# Placeholder schemas for other tools (will be expanded later)
class StoreData(BaseModel):
    """Data for store/shop objects"""
    shopName: str = Field(..., description="Name of the shop")
    shopType: str = Field(..., description="Type of shop")
    # Will be expanded when StoreGenerator is integrated
    placeholderData: Dict[str, Any] = Field(default_factory=dict)


class StatblockData(BaseModel):
    """Data for creature statblock objects"""
    creatureName: str = Field(..., description="Name of the creature")
    creatureType: str = Field(..., description="Type of creature")
    # Will be expanded when StatblockGenerator is integrated
    placeholderData: Dict[str, Any] = Field(default_factory=dict)


class RuleData(BaseModel):
    """Data for rules/mechanics objects"""
    ruleName: str = Field(..., description="Name of the rule")
    ruleCategory: str = Field(..., description="Category of rule")
    # Will be expanded when RulesLawyer is integrated
    placeholderData: Dict[str, Any] = Field(default_factory=dict)


class SpellData(BaseModel):
    """Data for spell objects"""
    spellName: str = Field(..., description="Name of the spell")
    spellLevel: int = Field(..., description="Spell level")
    # Will be expanded for future spell tools
    placeholderData: Dict[str, Any] = Field(default_factory=dict)


class DungeonMindObject(BaseModel):
    """
    Base class for all DungeonMind objects.
    Provides common structure for cross-tool object sharing.
    """
    # Identity and ownership
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique object identifier")
    type: ObjectType = Field(..., description="Type of object")
    createdBy: str = Field(..., description="User ID of creator")
    ownedBy: str = Field(..., description="User ID of current owner")
    
    # Organization and context
    worldId: Optional[str] = Field(None, description="World/campaign this object belongs to")
    projectId: Optional[str] = Field(None, description="Project this object belongs to")
    collectionId: Optional[str] = Field(None, description="Collection this object belongs to")
    
    # Core metadata (universal across all tools)
    name: str = Field(..., min_length=1, max_length=200, description="Object name")
    description: str = Field(..., min_length=1, description="Object description")
    tags: List[str] = Field(default_factory=list, description="Tags for organization and search")
    category: Optional[str] = Field(None, description="Tool-specific category")
    
    # Collaboration and sharing
    visibility: Visibility = Field(default=Visibility.PRIVATE, description="Who can see this object")
    sharedWith: List[str] = Field(default_factory=list, description="User IDs with shared access")
    permissions: ObjectPermissions = Field(default_factory=ObjectPermissions, description="Granular permissions")
    
    # Content versioning
    version: int = Field(default=1, description="Current version number")
    versionHistory: List[ObjectVersion] = Field(default_factory=list, description="History of changes")
    isTemplate: bool = Field(default=False, description="Whether this can be used as a template")
    basedOnTemplate: Optional[str] = Field(None, description="Template object ID if derived from template")
    
    # Tool-specific data (exactly one should be present)
    itemData: Optional[ItemCardData] = Field(None, description="Data for item cards")
    storeData: Optional[StoreData] = Field(None, description="Data for store objects")
    statblockData: Optional[StatblockData] = Field(None, description="Data for statblock objects")
    ruleData: Optional[RuleData] = Field(None, description="Data for rule objects")
    spellData: Optional[SpellData] = Field(None, description="Data for spell objects")
    
    # System metadata
    createdAt: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), description="Creation timestamp")
    updatedAt: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), description="Last update timestamp")
    lastAccessedAt: Optional[str] = Field(None, description="Last access timestamp")
    accessCount: int = Field(default=0, description="Number of times accessed")
    
    # AI generation metadata
    generationMetadata: Optional[AIGenerationMetadata] = Field(None, description="AI generation details")

    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()

    @validator('description')
    def validate_description(cls, v):
        if not v or not v.strip():
            raise ValueError("Description cannot be empty")
        return v.strip()

    @validator('tags')
    def validate_tags(cls, v):
        # Clean up tags: remove empty strings, strip whitespace, remove duplicates
        cleaned_tags = list(set(tag.strip().lower() for tag in v if tag and tag.strip()))
        return cleaned_tags

    @validator('ownedBy')
    def owned_by_must_match_created_by_on_creation(cls, v, values):
        # On creation, ownedBy should match createdBy
        if 'createdBy' in values and v != values['createdBy']:
            # Allow transfer of ownership after creation, but log it
            pass
        return v

    def model_post_init(self, __context: Any) -> None:
        """Post-initialization validation"""
        # Ensure exactly one tool-specific data field is present
        tool_data_fields = [
            self.itemData, self.storeData, self.statblockData, 
            self.ruleData, self.spellData
        ]
        
        non_null_count = sum(1 for field in tool_data_fields if field is not None)
        
        if non_null_count == 0:
            raise ValueError("Object must have exactly one tool-specific data field")
        elif non_null_count > 1:
            raise ValueError("Object cannot have multiple tool-specific data fields")
        
        # Validate that the tool data matches the object type
        type_to_data_map = {
            ObjectType.ITEM: self.itemData,
            ObjectType.STORE: self.storeData,
            ObjectType.STATBLOCK: self.statblockData,
            ObjectType.RULE: self.ruleData,
            ObjectType.SPELL: self.spellData
        }
        
        if self.type in type_to_data_map and type_to_data_map[self.type] is None:
            raise ValueError(f"Object of type {self.type} must have corresponding data field")

    def update_timestamp(self):
        """Update the updatedAt timestamp"""
        self.updatedAt = datetime.utcnow().isoformat()

    def increment_access_count(self):
        """Increment access count and update last accessed time"""
        self.accessCount += 1
        self.lastAccessedAt = datetime.utcnow().isoformat()

    def add_version(self, changes: str, changed_by: str, data_snapshot: Dict[str, Any]):
        """Add a new version to the history"""
        new_version = ObjectVersion(
            version=self.version + 1,
            timestamp=datetime.utcnow().isoformat(),
            changes=changes,
            changedBy=changed_by,
            data=data_snapshot
        )
        
        self.versionHistory.append(new_version)
        self.version += 1
        self.update_timestamp()

    def can_read(self, user_id: str) -> bool:
        """Check if user can read this object"""
        return (
            self.ownedBy == user_id or
            user_id in self.sharedWith or
            user_id in self.permissions.canRead or
            (self.visibility == Visibility.PUBLIC) or
            self.permissions.isPublicReadable
        )

    def can_write(self, user_id: str) -> bool:
        """Check if user can write to this object"""
        return (
            self.ownedBy == user_id or
            user_id in self.permissions.canWrite or
            user_id in self.permissions.canAdmin
        )

    def can_admin(self, user_id: str) -> bool:
        """Check if user can admin this object"""
        return (
            self.ownedBy == user_id or
            user_id in self.permissions.canAdmin
        )


# World and Project organization schemas
class WorldMember(BaseModel):
    """Member of a DungeonMind world"""
    userId: str = Field(..., description="User ID")
    role: str = Field(..., description="Role in world (owner, admin, member, viewer)")
    joinedAt: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), description="When user joined")
    permissions: List[str] = Field(default_factory=list, description="Specific permissions")


class WorldCollection(BaseModel):
    """Collection of objects within a world"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Collection ID")
    name: str = Field(..., description="Collection name")
    description: str = Field(default="", description="Collection description")
    type: Optional[ObjectType] = Field(None, description="Filter by object type")
    tags: List[str] = Field(default_factory=list, description="Auto-include objects with these tags")
    objectIds: List[str] = Field(default_factory=list, description="Manually curated object IDs")
    isPublic: bool = Field(default=False, description="Whether collection is publicly visible")


class DungeonMindWorld(BaseModel):
    """World/campaign organization for DungeonMind objects"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="World ID")
    name: str = Field(..., description="World name")
    description: str = Field(..., description="World description")
    createdBy: str = Field(..., description="Creator user ID")
    
    # World metadata
    setting: str = Field(default="Homebrew", description="Campaign setting")
    theme: str = Field(default="High Fantasy", description="World theme")
    magicLevel: str = Field(default="moderate", description="Magic level in world")
    
    # Collaboration
    members: List[WorldMember] = Field(default_factory=list, description="World members")
    joinCode: Optional[str] = Field(None, description="Code for easy joining")
    isPublic: bool = Field(default=False, description="Whether world is publicly visible")
    
    # Organization
    collections: List[WorldCollection] = Field(default_factory=list, description="Object collections")
    defaultPermissions: ObjectPermissions = Field(default_factory=ObjectPermissions, description="Default permissions for new objects")
    
    createdAt: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updatedAt: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    @validator('magicLevel')
    def validate_magic_level(cls, v):
        valid_levels = ['none', 'low', 'moderate', 'high', 'very_high']
        if v not in valid_levels:
            raise ValueError(f"Magic level must be one of: {', '.join(valid_levels)}")
        return v


class DungeonMindProject(BaseModel):
    """Project organization for DungeonMind objects"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Project ID")
    name: str = Field(..., description="Project name")
    description: str = Field(..., description="Project description")
    worldId: Optional[str] = Field(None, description="Associated world ID")
    createdBy: str = Field(..., description="Creator user ID")
    
    # Project-specific organization
    objectives: List[str] = Field(default_factory=list, description="Project objectives")
    deadline: Optional[str] = Field(None, description="Project deadline")
    status: str = Field(default="active", description="Project status")
    
    # Content tracking
    objectIds: List[str] = Field(default_factory=list, description="Objects in this project")
    templates: List[str] = Field(default_factory=list, description="Template object IDs")
    
    createdAt: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updatedAt: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    @validator('status')
    def validate_status(cls, v):
        valid_statuses = ['planning', 'active', 'completed', 'archived']
        if v not in valid_statuses:
            raise ValueError(f"Status must be one of: {', '.join(valid_statuses)}")
        return v


# Request/Response models for API endpoints
class CreateObjectRequest(BaseModel):
    """Request to create a new DungeonMind object"""
    type: ObjectType
    name: str
    description: str
    tags: List[str] = Field(default_factory=list)
    worldId: Optional[str] = None
    projectId: Optional[str] = None
    visibility: Visibility = Visibility.PRIVATE
    
    # Tool-specific data
    itemData: Optional[ItemCardData] = None
    storeData: Optional[StoreData] = None
    statblockData: Optional[StatblockData] = None
    ruleData: Optional[RuleData] = None
    spellData: Optional[SpellData] = None


class UpdateObjectRequest(BaseModel):
    """Request to update an existing DungeonMind object"""
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    visibility: Optional[Visibility] = None
    
    # Tool-specific data updates
    itemData: Optional[ItemCardData] = None
    storeData: Optional[StoreData] = None
    statblockData: Optional[StatblockData] = None
    ruleData: Optional[RuleData] = None
    spellData: Optional[SpellData] = None


class ObjectSearchRequest(BaseModel):
    """Request to search for objects"""
    query: Optional[str] = None
    type: Optional[ObjectType] = None
    worldId: Optional[str] = None
    projectId: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    visibility: Optional[Visibility] = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0) 