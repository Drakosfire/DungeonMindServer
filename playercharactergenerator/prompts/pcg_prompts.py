"""
Prompt templates for Player Character Generator AI generation

This mirrors the frontend promptBuilder.ts for consistency.
"""

import logging
from typing import Dict, Any, List, Optional

from ..models.pcg_models import (
    GenerationInput,
    GenerationConstraints,
    EquipmentPackage,
    FeatureChoice,
    SpellcastingConstraints,
)

logger = logging.getLogger(__name__)


class PCGPromptManager:
    """Manages prompts for D&D 5e character preference generation"""

    def __init__(self):
        self.version = "1.0.0"
        logger.info(f"PCGPromptManager initialized v{self.version}")

    def get_system_prompt(self) -> str:
        """Get the system prompt for preference generation"""
        return """You are a D&D 5e character creation assistant. Your job is to express CHARACTER PREFERENCES based on a concept.

CRITICAL RULES:
1. You express PREFERENCES and THEMES, not exact mechanical values
2. All abilities must be ranked in priority order (all 6, highest first)
3. Skill themes should describe what the character is good at, not specific skill names
4. Equipment style describes the look and feel, not specific items
5. Your output must be valid JSON matching the exact schema provided

You are creative and evocative, but you work WITHIN the constraints provided."""

    def build_preference_prompt(
        self,
        input_data: GenerationInput,
        constraints: GenerationConstraints
    ) -> str:
        """
        Build the user prompt for preference generation

        Args:
            input_data: User's character foundation choices
            constraints: Rule-engine derived constraints

        Returns:
            Complete user prompt string
        """
        sections = []

        # Section 1: Character Foundation
        sections.append(self._build_foundation_section(input_data, constraints))

        # Section 2: Available Options
        sections.append(self._build_options_section(constraints))

        # Section 3: Output Format
        sections.append(self._build_output_format_section(constraints.spellcasting is not None))

        # Section 4: Character Concept
        sections.append(self._build_concept_section(input_data.concept))

        return "\n".join(sections)

    def _build_foundation_section(
        self,
        input_data: GenerationInput,
        constraints: GenerationConstraints
    ) -> str:
        """Build the character foundation section"""
        # Format ability bonuses
        bonuses = constraints.race.ability_bonuses
        bonus_parts = [f"{k} +{v}" for k, v in bonuses.items() if v > 0]
        bonus_str = ", ".join(bonus_parts) if bonus_parts else "None"

        # Format primary abilities
        primary_str = ", ".join([a.value for a in constraints.class_info.primary_abilities])

        return f"""## CHARACTER FOUNDATION (Fixed by Player)

**Class:** {constraints.class_info.name}
**Race:** {constraints.race.name}
**Level:** {input_data.level}
**Background:** {constraints.background.name}

**Hit Die:** d{constraints.class_info.hit_die}
**Primary Abilities:** {primary_str}
**Racial Bonuses:** {bonus_str}"""

    def _build_options_section(self, constraints: GenerationConstraints) -> str:
        """Build the available options section"""
        parts = ["## AVAILABLE OPTIONS"]

        # Skills
        parts.append(self._format_skill_options(constraints))

        # Equipment
        parts.append(self._format_equipment_options(constraints))

        # Feature Choices (if any)
        if constraints.feature_choices:
            parts.append(self._format_feature_choices(constraints.feature_choices))

        # Spellcasting (if applicable)
        if constraints.spellcasting:
            parts.append(self._format_spellcasting(constraints.spellcasting))

        return "\n\n".join(parts)

    def _format_skill_options(self, constraints: GenerationConstraints) -> str:
        """Format skill options section"""
        granted = ", ".join(constraints.skills.granted_by_background)
        options = ", ".join(constraints.skills.class_options)
        count = constraints.skills.choose_count

        return f"""### Skills
Background grants: {granted}
Choose {count} from: {options}"""

    def _format_equipment_options(self, constraints: GenerationConstraints) -> str:
        """Format equipment packages section"""
        lines = ["### Equipment Packages"]

        packages = constraints.equipment.get("packages", [])
        for pkg in packages:
            items = ", ".join(pkg.items) if hasattr(pkg, 'items') else str(pkg.get('items', []))
            desc = pkg.description if hasattr(pkg, 'description') else pkg.get('description', '')
            pkg_id = pkg.id if hasattr(pkg, 'id') else pkg.get('id', '?')
            lines.append(f"- **{pkg_id}:** {desc}")

        return "\n".join(lines)

    def _format_feature_choices(self, choices: List[FeatureChoice]) -> str:
        """Format feature choice options"""
        lines = ["### Feature Choices"]

        for choice in choices:
            lines.append(f"\n**{choice.feature_name}:**")
            for opt in choice.options:
                lines.append(f"- {opt.name}: {opt.description}")

        return "\n".join(lines)

    def _format_spellcasting(self, spellcasting: SpellcastingConstraints) -> str:
        """Format spellcasting section"""
        return f"""### Spellcasting
Spellcasting Ability: {spellcasting.ability.value}
Cantrips Known: {spellcasting.cantrips_known}
Spells Known: {spellcasting.spells_known}

*Note: Specific spell lists would be injected here from the Rule Engine.*"""

    def _build_output_format_section(self, has_spellcasting: bool) -> str:
        """Build the output format section"""
        spell_fields = ""
        if has_spellcasting:
            spell_fields = """
  "cantripThemes": ["theme1", "theme2"],
  "spellThemes": ["theme1", "theme2", "theme3"],"""

        return f"""## OUTPUT FORMAT

Respond with ONLY valid JSON matching this exact structure:

```json
{{
  "abilityPriorities": ["ability1", "ability2", "ability3", "ability4", "ability5", "ability6"],
  "abilityReasoning": "Brief explanation of why these priorities fit the character concept",
  
  "combatApproach": "Description of how this character fights (e.g., 'Defensive tank who protects allies')",
  "skillThemes": ["theme1", "theme2", "theme3"],
  
  "equipmentStyle": "Description of preferred equipment (e.g., 'Heavy armor with shield for maximum protection')",{spell_fields}
  
  "character": {{
    "name": "Character Name",
    "personality": {{
      "traits": ["Personality trait 1", "Personality trait 2"],
      "ideals": ["What the character believes in"],
      "bonds": ["What connects the character to the world"],
      "flaws": ["Character weakness or vice"]
    }},
    "backstory": "2-4 paragraphs of character history that connects to the concept and explains their current situation.",
    "appearance": "Physical description of the character",
    "age": 25
  }}
}}
```

### Ability Priority Rules
- List ALL SIX abilities in order from highest to lowest priority
- Valid abilities: strength, dexterity, constitution, intelligence, wisdom, charisma
- Consider the class's primary abilities when prioritizing

### Skill Theme Examples
Good themes: "physical prowess", "stealth and subterfuge", "social manipulation", "arcane knowledge", "wilderness survival", "keen observation"
Bad themes: "Athletics" (too specific), "good at stuff" (too vague)

### Equipment Style Examples
Good: "Heavy armor and shield, favoring defense over offense"
Good: "Light and mobile, preferring ranged combat"
Bad: "Chain mail" (too specific - we pick the package)"""

    def _build_concept_section(self, concept: str) -> str:
        """Build the character concept section"""
        return f"""## CHARACTER CONCEPT

"{concept}" """


# Mock constraints for testing (mirrors frontend)
def create_mock_fighter_constraints() -> dict:
    """Create mock constraints for a Fighter"""
    return {
        "class": {
            "id": "fighter",
            "name": "Fighter",
            "hitDie": 10,
            "primaryAbilities": ["strength", "constitution"]
        },
        "race": {
            "id": "human",
            "name": "Human",
            "abilityBonuses": {
                "strength": 1,
                "dexterity": 1,
                "constitution": 1,
                "intelligence": 1,
                "wisdom": 1,
                "charisma": 1
            }
        },
        "background": {
            "id": "soldier",
            "name": "Soldier",
            "grantedSkills": ["Athletics", "Intimidation"]
        },
        "skills": {
            "grantedByBackground": ["Athletics", "Intimidation"],
            "classOptions": ["Acrobatics", "Animal Handling", "Athletics", "History", "Insight", "Intimidation", "Perception", "Survival"],
            "chooseCount": 2,
            "overlapHandling": "free-choice"
        },
        "equipment": {
            "packages": [
                {
                    "id": "A",
                    "description": "Chain mail, shield, and martial weapon",
                    "items": ["Chain mail", "Shield", "Longsword"]
                },
                {
                    "id": "B",
                    "description": "Leather armor, longbow, and two handaxes",
                    "items": ["Leather armor", "Longbow", "Handaxe (2)"]
                }
            ]
        },
        "featureChoices": [
            {
                "featureId": "fighting-style",
                "featureName": "Fighting Style",
                "options": [
                    {"id": "defense", "name": "Defense", "description": "+1 AC while wearing armor"},
                    {"id": "dueling", "name": "Dueling", "description": "+2 damage with one-handed weapon"},
                    {"id": "great-weapon", "name": "Great Weapon Fighting", "description": "Reroll 1s and 2s on damage"},
                    {"id": "protection", "name": "Protection", "description": "Impose disadvantage on attacks against allies"}
                ]
            }
        ],
        "spellcasting": None
    }


def create_mock_wizard_constraints() -> dict:
    """Create mock constraints for a Wizard"""
    return {
        "class": {
            "id": "wizard",
            "name": "Wizard",
            "hitDie": 6,
            "primaryAbilities": ["intelligence"]
        },
        "race": {
            "id": "human",
            "name": "Human",
            "abilityBonuses": {
                "strength": 1,
                "dexterity": 1,
                "constitution": 1,
                "intelligence": 1,
                "wisdom": 1,
                "charisma": 1
            }
        },
        "background": {
            "id": "sage",
            "name": "Sage",
            "grantedSkills": ["Arcana", "History"]
        },
        "skills": {
            "grantedByBackground": ["Arcana", "History"],
            "classOptions": ["Arcana", "History", "Insight", "Investigation", "Medicine", "Religion"],
            "chooseCount": 2,
            "overlapHandling": "free-choice"
        },
        "equipment": {
            "packages": [
                {
                    "id": "A",
                    "description": "Quarterstaff, component pouch, scholar's pack, spellbook",
                    "items": ["Quarterstaff", "Component pouch", "Scholar's pack", "Spellbook"]
                },
                {
                    "id": "B",
                    "description": "Dagger, arcane focus, explorer's pack, spellbook",
                    "items": ["Dagger", "Arcane focus", "Explorer's pack", "Spellbook"]
                }
            ]
        },
        "featureChoices": [],
        "spellcasting": {
            "ability": "intelligence",
            "cantripsKnown": 3,
            "spellsKnown": 6,
            "spellListId": "wizard"
        }
    }

