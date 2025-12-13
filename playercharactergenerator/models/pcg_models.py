"""
Pydantic models for Player Character Generator API

These models mirror the TypeScript interfaces in the frontend for consistency.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from enum import Enum


class AbilityName(str, Enum):
    """D&D 5e ability score names"""
    STRENGTH = "strength"
    DEXTERITY = "dexterity"
    CONSTITUTION = "constitution"
    INTELLIGENCE = "intelligence"
    WISDOM = "wisdom"
    CHARISMA = "charisma"


class GenerationInput(BaseModel):
    """
    User-provided character foundation
    These are the choices the user makes explicitly.
    """
    class_id: str = Field(..., alias="classId", description="D&D 5e class ID (e.g., 'fighter', 'wizard')")
    subclass_id: Optional[str] = Field(None, alias="subclassId", description="Subclass ID if level 3+")
    race_id: str = Field(..., alias="raceId", description="D&D 5e race ID (e.g., 'human', 'elf')")
    subrace_id: Optional[str] = Field(None, alias="subraceId", description="Subrace ID if applicable")
    level: int = Field(..., ge=1, le=3, description="Character level (1-3)")
    background_id: str = Field(..., alias="backgroundId", description="Background ID (e.g., 'soldier', 'sage')")
    concept: str = Field(..., min_length=10, max_length=500, description="Character concept/description")

    class Config:
        populate_by_name = True


class EquipmentPackage(BaseModel):
    """An equipment package option"""
    id: str
    description: str
    items: List[str]


class FeatureOption(BaseModel):
    """A feature choice option"""
    id: str
    name: str
    description: str


class FeatureChoice(BaseModel):
    """A feature that requires a choice"""
    feature_id: str = Field(..., alias="featureId")
    feature_name: str = Field(..., alias="featureName")
    options: List[FeatureOption]

    class Config:
        populate_by_name = True


class SpellcastingConstraints(BaseModel):
    """Spellcasting constraints for caster classes"""
    ability: AbilityName
    cantrips_known: int = Field(..., alias="cantripsKnown")
    spells_known: int = Field(..., alias="spellsKnown")
    spell_list_id: str = Field(..., alias="spellListId")

    class Config:
        populate_by_name = True


class SkillConstraints(BaseModel):
    """Skill selection constraints"""
    granted_by_background: List[str] = Field(..., alias="grantedByBackground")
    class_options: List[str] = Field(..., alias="classOptions")
    choose_count: int = Field(..., alias="chooseCount")
    overlap_handling: str = Field(..., alias="overlapHandling")

    class Config:
        populate_by_name = True


class ClassConstraints(BaseModel):
    """Class-specific constraints"""
    id: str
    name: str
    hit_die: int = Field(..., alias="hitDie")
    primary_abilities: List[AbilityName] = Field(..., alias="primaryAbilities")

    class Config:
        populate_by_name = True


class RaceConstraints(BaseModel):
    """Race-specific constraints"""
    id: str
    name: str
    ability_bonuses: Dict[str, int] = Field(..., alias="abilityBonuses")

    class Config:
        populate_by_name = True


class BackgroundConstraints(BaseModel):
    """Background-specific constraints"""
    id: str
    name: str
    granted_skills: List[str] = Field(..., alias="grantedSkills")

    class Config:
        populate_by_name = True


class GenerationConstraints(BaseModel):
    """
    Rule-engine derived constraints for AI generation
    These constrain what options are valid for the user's choices.
    """
    class_info: ClassConstraints = Field(..., alias="class")
    race: RaceConstraints
    background: BackgroundConstraints
    skills: SkillConstraints
    equipment: Dict[str, List[EquipmentPackage]]
    feature_choices: List[FeatureChoice] = Field(default_factory=list, alias="featureChoices")
    spellcasting: Optional[SpellcastingConstraints] = None

    class Config:
        populate_by_name = True


class CharacterPersonality(BaseModel):
    """Character personality traits"""
    traits: List[str] = Field(default_factory=list)
    ideals: List[str] = Field(default_factory=list)
    bonds: List[str] = Field(default_factory=list)
    flaws: List[str] = Field(default_factory=list)


class CharacterDetails(BaseModel):
    """AI-generated character details"""
    name: str
    personality: CharacterPersonality
    backstory: str
    appearance: Optional[str] = None
    age: Optional[int] = None


class FeaturePreference(BaseModel):
    """Preference for a feature choice"""
    id: str
    reasoning: Optional[str] = None


class AiPreferences(BaseModel):
    """
    AI-generated preferences for character creation
    These express creative intent, not exact mechanical values.
    """
    ability_priorities: List[AbilityName] = Field(
        ..., 
        alias="abilityPriorities",
        min_length=6,
        max_length=6,
        description="All 6 abilities ordered by priority"
    )
    ability_reasoning: Optional[str] = Field(None, alias="abilityReasoning")
    
    combat_approach: Optional[str] = Field(None, alias="combatApproach")
    skill_themes: List[str] = Field(default_factory=list, alias="skillThemes")
    
    equipment_style: str = Field(..., alias="equipmentStyle")
    
    subclass_preference: Optional[FeaturePreference] = Field(None, alias="subclassPreference")
    fighting_style_preference: Optional[FeaturePreference] = Field(None, alias="fightingStylePreference")
    
    cantrip_themes: Optional[List[str]] = Field(None, alias="cantripThemes")
    spell_themes: Optional[List[str]] = Field(None, alias="spellThemes")
    
    character: CharacterDetails

    class Config:
        populate_by_name = True


class PreferenceGenerationRequest(BaseModel):
    """
    Request to generate AI preferences for a character
    """
    input: GenerationInput
    constraints: Optional[GenerationConstraints] = None  # If None, backend will compute from input

    class Config:
        populate_by_name = True


class PreferenceGenerationResponse(BaseModel):
    """
    Response from AI preference generation
    """
    success: bool
    preferences: Optional[AiPreferences] = None
    raw_response: Optional[str] = Field(None, alias="rawResponse")
    error: Optional[str] = None
    generation_info: Optional[Dict[str, Any]] = Field(None, alias="generationInfo")

    class Config:
        populate_by_name = True

