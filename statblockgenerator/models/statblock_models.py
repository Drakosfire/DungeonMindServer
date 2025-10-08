"""
Pydantic models for D&D 5e StatBlock data structures
Optimized for OpenAI Structured Outputs
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any, Union
from enum import Enum
from datetime import datetime

# Enums for creature properties
class CreatureSize(str, Enum):
    TINY = "Tiny"
    SMALL = "Small"
    MEDIUM = "Medium"
    LARGE = "Large"
    HUGE = "Huge"
    GARGANTUAN = "Gargantuan"

class CreatureType(str, Enum):
    ABERRATION = "aberration"
    BEAST = "beast"
    CELESTIAL = "celestial"
    CONSTRUCT = "construct"
    DRAGON = "dragon"
    ELEMENTAL = "elemental"
    FEY = "fey"
    FIEND = "fiend"
    GIANT = "giant"
    HUMANOID = "humanoid"
    MONSTROSITY = "monstrosity"
    OOZE = "ooze"
    PLANT = "plant"
    UNDEAD = "undead"

class Alignment(str, Enum):
    LAWFUL_GOOD = "lawful good"
    NEUTRAL_GOOD = "neutral good"
    CHAOTIC_GOOD = "chaotic good"
    LAWFUL_NEUTRAL = "lawful neutral"
    TRUE_NEUTRAL = "true neutral"
    CHAOTIC_NEUTRAL = "chaotic neutral"
    LAWFUL_EVIL = "lawful evil"
    NEUTRAL_EVIL = "neutral evil"
    CHAOTIC_EVIL = "chaotic evil"
    UNALIGNED = "unaligned"

# Core data structures
class AbilityScores(BaseModel):
    """D&D 5e ability scores"""
    str: int = Field(..., ge=1, le=30, description="Strength score")
    dex: int = Field(..., ge=1, le=30, description="Dexterity score")
    con: int = Field(..., ge=1, le=30, description="Constitution score")
    intelligence: int = Field(..., ge=1, le=30, description="Intelligence score", alias="int")
    wis: int = Field(..., ge=1, le=30, description="Wisdom score")
    cha: int = Field(..., ge=1, le=30, description="Charisma score")
    
    model_config = {"populate_by_name": True}
    
    def get_modifier(self, ability: str) -> int:
        """Calculate ability modifier"""
        # Handle the intelligence field alias
        if ability == "int":
            ability = "intelligence"
        score = getattr(self, ability)
        return (score - 10) // 2

class SpeedObject(BaseModel):
    """Creature movement speeds"""
    walk: Optional[int] = Field(None, ge=0, description="Walking speed in feet")
    fly: Optional[int] = Field(None, ge=0, description="Flying speed in feet")
    swim: Optional[int] = Field(None, ge=0, description="Swimming speed in feet")
    climb: Optional[int] = Field(None, ge=0, description="Climbing speed in feet")
    burrow: Optional[int] = Field(None, ge=0, description="Burrowing speed in feet")

class SensesObject(BaseModel):
    """Creature senses"""
    darkvision: Optional[int] = Field(None, ge=0, description="Darkvision range in feet")
    blindsight: Optional[int] = Field(None, ge=0, description="Blindsight range in feet")
    tremorsense: Optional[int] = Field(None, ge=0, description="Tremorsense range in feet")
    truesight: Optional[int] = Field(None, ge=0, description="Truesight range in feet")
    passive_perception: int = Field(..., ge=1, description="Passive Perception score")

class Action(BaseModel):
    """Creature action (attack, ability, etc.)"""
    name: str = Field(..., description="Action name")
    desc: str = Field(..., description="Action description")
    attack_bonus: Optional[int] = Field(None, description="Attack bonus (if attack)")
    damage: Optional[str] = Field(None, description="Damage dice and type")
    damage_type: Optional[str] = Field(None, description="Type of damage")
    range: Optional[str] = Field(None, description="Attack range")
    recharge: Optional[str] = Field(None, description="Recharge requirement (e.g., '5-6')")

class Spell(BaseModel):
    """Individual spell"""
    name: str = Field(..., description="Spell name")
    level: int = Field(..., ge=0, le=9, description="Spell level (0 for cantrips)")
    description: Optional[str] = Field(None, description="Spell description/effect")
    school: Optional[str] = Field(None, description="School of magic")
    
    model_config = {"populate_by_name": True}

class SpellSlots(BaseModel):
    """Spell slots per level"""
    level_1: Optional[int] = Field(None, ge=0, alias="level1", description="1st level spell slots")
    level_2: Optional[int] = Field(None, ge=0, alias="level2", description="2nd level spell slots")
    level_3: Optional[int] = Field(None, ge=0, alias="level3", description="3rd level spell slots")
    level_4: Optional[int] = Field(None, ge=0, alias="level4", description="4th level spell slots")
    level_5: Optional[int] = Field(None, ge=0, alias="level5", description="5th level spell slots")
    level_6: Optional[int] = Field(None, ge=0, alias="level6", description="6th level spell slots")
    level_7: Optional[int] = Field(None, ge=0, alias="level7", description="7th level spell slots")
    level_8: Optional[int] = Field(None, ge=0, alias="level8", description="8th level spell slots")
    level_9: Optional[int] = Field(None, ge=0, alias="level9", description="9th level spell slots")
    
    model_config = {"populate_by_name": True}

class SpellcastingBlock(BaseModel):
    """Spellcasting ability block"""
    level: int = Field(..., ge=1, le=20, description="Spellcaster level")
    ability: str = Field(..., description="Spellcasting ability")
    save_dc: int = Field(..., ge=8, alias="saveDc", description="Spell save DC")
    attack_bonus: int = Field(..., alias="attackBonus", description="Spell attack bonus")
    cantrips: Optional[List[Spell]] = Field(None, description="Known cantrips")
    known_spells: Optional[List[Spell]] = Field(None, alias="knownSpells", description="Known spells")
    spell_slots: Optional[SpellSlots] = Field(None, alias="spellSlots", description="Available spell slots")
    
    model_config = {"populate_by_name": True}

class LegendaryActionsBlock(BaseModel):
    """Legendary actions block"""
    actions_per_turn: int = Field(3, ge=1, alias="actionsPerTurn", description="Number of legendary actions per turn")
    actions: List[Action] = Field(..., description="Available legendary actions")
    description: Optional[str] = Field(None, description="Introductory text for legendary actions")
    
    model_config = {"populate_by_name": True}

class LairActionsBlock(BaseModel):
    """Lair actions block"""
    initiative: int = Field(20, description="Initiative count for lair actions")
    actions: List[Action] = Field(..., description="Lair action descriptions")
    description: Optional[str] = Field(None, description="Introductory text for lair actions")
    
    model_config = {"populate_by_name": True}

# Main StatBlock model
class StatBlockDetails(BaseModel):
    """Complete D&D 5e creature statblock optimized for OpenAI Structured Outputs"""
    
    # Basic Information
    name: str = Field(..., description="Creature name")
    size: CreatureSize = Field(..., description="Creature size category")
    type: CreatureType = Field(..., description="Creature type")
    subtype: Optional[str] = Field(None, description="Creature subtype (e.g., 'human', 'elf')")
    alignment: Alignment = Field(..., description="Creature alignment")
    
    # Combat Statistics
    armor_class: int = Field(..., ge=1, alias="armorClass", description="Armor Class")
    hit_points: int = Field(..., ge=1, alias="hitPoints", description="Hit Points")
    hit_dice: str = Field(..., alias="hitDice", description="Hit dice formula (e.g., '8d8+16')")
    speed: SpeedObject = Field(..., description="Movement speeds")
    
    # Ability Scores
    abilities: AbilityScores = Field(..., description="Six ability scores")
    saving_throws: Optional[Dict[str, int]] = Field(None, alias="savingThrows", description="Saving throw bonuses")
    skills: Optional[Dict[str, int]] = Field(None, description="Skill bonuses")
    
    # Resistances and Immunities
    damage_resistance: Optional[str] = Field(None, alias="damageResistance", description="Damage resistances")
    damage_immunity: Optional[str] = Field(None, alias="damageImmunity", description="Damage immunities")
    condition_immunity: Optional[str] = Field(None, alias="conditionImmunity", description="Condition immunities")
    damage_vulnerability: Optional[str] = Field(None, alias="damageVulnerability", description="Damage vulnerabilities")
    
    # Senses and Communication
    senses: SensesObject = Field(..., description="Creature senses")
    languages: str = Field(..., description="Known languages")
    
    # Challenge and Experience
    challenge_rating: Union[str, float] = Field(..., alias="challengeRating", description="Challenge Rating")
    xp: int = Field(..., ge=0, description="Experience Points")
    proficiency_bonus: int = Field(..., ge=2, alias="proficiencyBonus", description="Proficiency bonus")
    
    # Actions and Abilities
    actions: List[Action] = Field(..., description="Actions")
    bonus_actions: Optional[List[Action]] = Field(None, alias="bonusActions", description="Bonus actions")
    reactions: Optional[List[Action]] = Field(None, description="Reactions")
    
    # Special Abilities
    special_abilities: Optional[List[Action]] = Field(None, alias="specialAbilities", description="Special abilities/traits")
    
    # Spellcasting
    spells: Optional[SpellcastingBlock] = Field(None, description="Spellcasting block")
    
    # Legendary/Lair Actions
    legendary_actions: Optional[LegendaryActionsBlock] = Field(None, alias="legendaryActions", description="Legendary actions")
    lair_actions: Optional[LairActionsBlock] = Field(None, alias="lairActions", description="Lair actions")
    
    # Descriptive Content
    description: str = Field(..., description="Creature description/lore")
    sd_prompt: str = Field(..., alias="sdPrompt", description="Stable Diffusion prompt for image generation")
    
    # Project Integration
    project_id: Optional[str] = Field(None, alias="projectId", description="Associated project ID")
    created_at: Optional[datetime] = Field(None, alias="createdAt", description="Creation timestamp")
    last_modified: Optional[datetime] = Field(None, alias="lastModified", description="Last modification timestamp")
    tags: Optional[List[str]] = Field(None, description="Creature tags")
    
    model_config = {"populate_by_name": True}  # Accept both camelCase and snake_case
    
    @field_validator('challenge_rating')
    @classmethod
    def validate_challenge_rating(cls, v):
        """Validate challenge rating format"""
        if isinstance(v, str):
            # Allow fractions like "1/4", "1/2", etc.
            if '/' in v:
                try:
                    numerator, denominator = v.split('/')
                    float(numerator) / float(denominator)
                    return v
                except (ValueError, ZeroDivisionError):
                    raise ValueError("Invalid challenge rating fraction")
            else:
                try:
                    float(v)
                    return v
                except ValueError:
                    raise ValueError("Challenge rating must be a number or fraction")
        elif isinstance(v, (int, float)):
            return v
        else:
            raise ValueError("Challenge rating must be a number or fraction string")

# Project and session models
class StatBlockProject(BaseModel):
    """StatBlock project for organization"""
    project_id: str = Field(..., description="Unique project identifier")
    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(None, description="Project description")
    user_id: str = Field(..., description="Owner user ID")
    creatures: List[str] = Field(default_factory=list, description="List of creature IDs")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    last_modified: datetime = Field(default_factory=datetime.now, description="Last modification")
    tags: Optional[List[str]] = Field(None, description="Project tags")

class GeneratedImage(BaseModel):
    """Generated creature image data"""
    image_id: str = Field(..., description="Unique image identifier")
    url: str = Field(..., description="Image URL")
    prompt: str = Field(..., description="Generation prompt used")
    created_at: datetime = Field(default_factory=datetime.now)

class Generated3DModel(BaseModel):
    """Generated 3D model data"""
    model_id: str = Field(..., description="Unique model identifier")
    url: str = Field(..., description="Model file URL")
    format: str = Field("glb", description="Model file format")
    source_image_id: str = Field(..., description="Source image ID")
    created_at: datetime = Field(default_factory=datetime.now)

class GeneratedExport(BaseModel):
    """Generated export data"""
    export_id: str = Field(..., description="Unique export identifier")
    format: str = Field(..., description="Export format (html, pdf, json, etc.)")
    url: str = Field(..., description="Export file URL")
    created_at: datetime = Field(default_factory=datetime.now)

class SelectedAssets(BaseModel):
    """Selected assets for the statblock"""
    creature_image: Optional[str] = Field(None, description="Selected creature image URL")
    selected_image_index: Optional[int] = Field(None, description="Index of selected image")
    generated_images: List[str] = Field(default_factory=list, description="All generated image URLs")
    model_file: Optional[str] = Field(None, description="Selected 3D model file URL")

class GeneratedContent(BaseModel):
    """All generated content for the statblock"""
    images: List[GeneratedImage] = Field(default_factory=list)
    models: List[Generated3DModel] = Field(default_factory=list)
    exports: List[GeneratedExport] = Field(default_factory=list)

class StatBlockGeneratorState(BaseModel):
    """Complete state for StatBlock generator session"""
    session_id: str = Field(..., description="Session identifier")
    user_id: Optional[str] = Field(None, description="User ID (if authenticated)")
    project_id: Optional[str] = Field(None, description="Associated project ID")
    
    # Step progression
    current_step_id: str = Field("step1", description="Current workflow step")
    step_completion: Dict[str, bool] = Field(default_factory=dict, description="Step completion status")
    
    # Core data
    creature_details: Optional[StatBlockDetails] = Field(None, description="Creature statblock data")
    selected_assets: SelectedAssets = Field(default_factory=SelectedAssets, description="Selected assets")
    generated_content: GeneratedContent = Field(default_factory=GeneratedContent, description="Generated content")
    
    # Session management
    auto_save_enabled: bool = Field(True, description="Auto-save enabled")
    last_saved: Optional[datetime] = Field(None, description="Last save timestamp")
    generation_lock: bool = Field(False, description="Lock during generation")
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    last_modified: datetime = Field(default_factory=datetime.now)

# Request/Response models for API
class CreatureGenerationRequest(BaseModel):
    """Request for generating a creature with optional special features"""
    description: str = Field(..., description="Natural language creature description")
    
    # Accept both camelCase (frontend) and snake_case (Python convention)
    include_spells: bool = Field(
        False, 
        alias="includeSpellcasting",
        description="Include spellcasting abilities with spell slots and known spells"
    )
    include_legendary: bool = Field(
        False, 
        alias="includeLegendaryActions",
        description="Include legendary actions (3 actions with varying costs)"
    )
    include_lair: bool = Field(
        False, 
        alias="includeLairActions",
        description="Include lair actions (environmental effects on initiative count 20)"
    )
    
    challenge_rating_target: Optional[Union[str, float]] = Field(
        None, 
        description="Target challenge rating (e.g., '1', '5', '1/4')"
    )
    
    model_config = {"populate_by_name": True}  # Accept both camelCase and snake_case

class ImageGenerationRequest(BaseModel):
    """Request for generating creature images"""
    sd_prompt: str = Field(..., description="Stable Diffusion prompt")
    num_images: int = Field(4, ge=1, le=8, description="Number of images to generate")
    model: str = Field("flux-pro", description="Image generation model: 'flux-pro', 'imagen4', or 'openai'")

class ModelGenerationRequest(BaseModel):
    """Request for generating 3D model"""
    image_url: str = Field(..., description="Source image URL")
    model_type: str = Field("standard", description="Model generation type")

class StatBlockValidationRequest(BaseModel):
    """Request for validating a statblock"""
    statblock: StatBlockDetails = Field(..., description="Statblock to validate")
    strict_validation: bool = Field(False, description="Use strict D&D 5e validation")

class ProjectCreateRequest(BaseModel):
    """Request for creating a new project"""
    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(None, description="Project description")
    tags: Optional[List[str]] = Field(None, description="Project tags")

class SessionSaveRequest(BaseModel):
    """Request for saving session state"""
    session_data: StatBlockGeneratorState = Field(..., description="Session state to save")
    creature_name: Optional[str] = Field(None, description="Creature name for manual saves")
    is_auto_save: bool = Field(True, description="Is this an auto-save")
