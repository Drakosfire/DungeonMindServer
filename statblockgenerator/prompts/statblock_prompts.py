"""
Prompt management and templates for StatBlock generation with OpenAI Structured Outputs
"""

import logging
from typing import Dict, Any
from ..models.statblock_models import CreatureGenerationRequest

logger = logging.getLogger(__name__)

class StatBlockPromptManager:
    """Manages prompts for D&D 5e creature generation"""
    
    def __init__(self):
        self.version = "1.0.0"
        logger.info(f"StatBlockPromptManager initialized v{self.version}")
    
    def get_creature_generation_prompt(self, request: CreatureGenerationRequest) -> str:
        """
        Generate comprehensive prompt for creating D&D 5e creature statblocks using OpenAI Structured Outputs
        
        Args:
            request: CreatureGenerationRequest with all parameters
        """
        description = request.description
        include_spells = request.include_spells
        include_legendary = request.include_legendary
        include_lair = request.include_lair
        
        # Base prompt with core requirements
        # IMPORTANT: Let LLM determine appropriate CR based on description power level
        prompt = f"""Create a complete D&D 5e creature statblock based on this description: "{description}"

CRITICAL: Determine an appropriate Challenge Rating based on the creature's described power level, abilities, and threat.
- Use descriptor words (weak, minor, dangerous, powerful, ancient, godlike, etc.) to infer CR
- Consider implied abilities, size, and role (minion, boss, legendary creature)
- A "weak goblin" should be CR 1/4, a "powerful dragon" should be CR 15+, an "ancient demon lord" should be CR 20+

CORE REQUIREMENTS:
1. Name, size, type, alignment matching the description
2. Ability scores, AC, HP, and Hit Dice consistent with the determined Challenge Rating
3. Movement speeds appropriate for creature type
4. Skills, senses, and languages fitting the theme
5. At least 2-4 regular actions (attacks, special abilities) scaled to CR
6. Engaging description that brings the creature to life
7. Stable Diffusion prompt for artwork generation
8. XP value matching the Challenge Rating (use official D&D 5e XP table)
"""
        
        # Conditional: Spellcasting
        if include_spells:
            prompt += """
SPELLCASTING REQUIREMENTS (REQUIRED - DO NOT SET TO NULL):
- Populate the 'spells' field with a complete SpellcastingBlock object
- Include spellcasting ability (Intelligence, Wisdom, or Charisma) based on creature type
- Calculate spell_save_dc = 8 + proficiency_bonus + ability_modifier
- Calculate spell_attack_bonus = proficiency_bonus + ability_modifier
- Provide spell slots appropriate for the creature's CR:
  * CR 1-4: 1st-2nd level spells (cantrips + 2-4 spell slots per level)
  * CR 5-10: Up to 3rd-5th level spells (cantrips + 3-6 spell slots per level)
  * CR 11-16: Up to 6th-7th level spells (cantrips + appropriate slots)
  * CR 17+: Up to 9th level spells (cantrips + appropriate slots)
- Include at least 3-5 cantrips
- Include 5-10 leveled spells appropriate for the creature's theme and role
- Choose thematically appropriate spells (damage, control, support, etc.)

Example Spell Structure (ALL SPELLS MUST HAVE DESCRIPTIONS):
{
  "spells": {
    "spellcasting_ability": "Intelligence",
    "spell_save_dc": 15,
    "spell_attack_bonus": 7,
    "spell_slots": {
      "level_1": 4,
      "level_2": 3,
      "level_3": 2
    },
    "cantrips": [
      {
        "name": "Fire Bolt",
        "level": 0,
        "description": "Ranged spell attack. Hit: 1d10 fire damage.",
        "school": "Evocation"
      },
      {
        "name": "Mage Hand",
        "level": 0,
        "description": "Conjure a spectral hand to manipulate objects within 30 feet.",
        "school": "Conjuration"
      },
      {
        "name": "Prestidigitation",
        "level": 0,
        "description": "Minor magical trick or effect.",
        "school": "Transmutation"
      }
    ],
    "known_spells": [
      {
        "name": "Shield",
        "level": 1,
        "description": "Reaction to grant +5 AC until the start of your next turn.",
        "school": "Abjuration"
      },
      {
        "name": "Magic Missile",
        "level": 1,
        "description": "Three darts of magical force, each dealing 1d4+1 damage.",
        "school": "Evocation"
      },
      {
        "name": "Misty Step",
        "level": 2,
        "description": "Teleport up to 30 feet to an unoccupied space you can see.",
        "school": "Conjuration"
      },
      {
        "name": "Fireball",
        "level": 3,
        "description": "20-foot-radius sphere. DC 15 Dex save or 8d6 fire damage (half on save).",
        "school": "Evocation"
      }
    ]
  }
}

CRITICAL: Every spell (cantrips and known_spells) MUST include:
- name: The spell's name
- level: Spell level (0 for cantrips)
- description: Complete effect description (damage, duration, save DC, etc.)
- school: School of magic (Abjuration, Conjuration, Divination, Enchantment, Evocation, Illusion, Necromancy, Transmutation)
"""
        else:
            prompt += "\n- DO NOT include spellcasting (set 'spells' field to null)\n"
        
        # Conditional: Legendary Actions
        if include_legendary:
            prompt += """
LEGENDARY ACTIONS REQUIREMENTS (REQUIRED - DO NOT SET TO NULL):
- Populate the 'legendaryActions' field with a complete LegendaryActionsBlock object
- Include a description explaining how legendary actions work
- Provide exactly 3 legendary actions with varying costs (1, 2, and 3)
- Each action must have: name, cost (1-3), and detailed description
- Legendary actions are weaker than regular actions

CRITICAL: Create UNIQUE legendary actions appropriate to this specific creature's abilities and theme.
DO NOT use generic "Detect" actions unless the creature is specifically described as perceptive or sensory-focused.

Action Cost Guidelines (customize to creature):
  * Cost 1: Minor action (reposition, quick attack, sensory ability, defensive stance)
  * Cost 2: Standard attack or moderate ability (single weapon attack, spell, special move)
  * Cost 3: Powerful signature ability (area effect, devastating attack, major spell)

Example Structure (CUSTOMIZE NAMES AND EFFECTS TO MATCH CREATURE):
{
  "legendaryActions": {
    "description": "The [creature] can take 3 legendary actions, choosing from the options below. Only one legendary action can be used at a time and only at the end of another creature's turn. The [creature] regains spent legendary actions at the start of its turn.",
    "actions": [
      {
        "name": "[Thematic Name - Cost 1]",
        "cost": 1,
        "desc": "[Minor ability specific to this creature's theme and capabilities]"
      },
      {
        "name": "[Thematic Name - Cost 2]",
        "cost": 2,
        "desc": "[Attack or ability specific to this creature]"
      },
      {
        "name": "[Thematic Name - Cost 3]",
        "cost": 3,
        "desc": "[Powerful signature move unique to this creature with mechanics and damage]"
      }
    ]
  }
}

Examples of thematic legendary actions:
- Fire creature: "Flame Burst" (cost 1), "Scorching Ray" (cost 2), "Inferno Wave" (cost 3)
- Corporate creature: "Delegate Task" (cost 1), "Hostile Takeover" (cost 2), "Boardroom Domination" (cost 3)
- Shadow creature: "Shadow Step" (cost 1), "Drain Life" (cost 2), "Engulfing Darkness" (cost 3)
"""
        else:
            prompt += "\n- DO NOT include legendary actions (set 'legendaryActions' field to null)\n"
        
        # Conditional: Lair Actions
        if include_lair:
            prompt += """
LAIR ACTIONS REQUIREMENTS (REQUIRED - DO NOT SET TO NULL):
- Populate the 'lairActions' field with a complete LairActionsBlock object
- Include ALL required fields: lairName, lairDescription, description, and actions

LAIR ATMOSPHERE (REQUIRED):
- lairName: A evocative name for the creature's lair (e.g., "The Obsidian Throne", "Boardroom of Eternal Meetings")
- lairDescription: A rich sensory description of the lair (2-3 sentences):
  * What does it look/feel/sound/smell like?
  * What is the atmosphere and mood?
  * What unique environmental features exist?
  * Make it immersive and atmospheric!

LAIR MECHANICS:
- description: Standard rules text explaining initiative count 20 mechanics
- Provide 3-4 lair actions themed to the creature's SPECIFIC environment
- Each action must have: name and detailed description with mechanics (DC, damage, area)

CRITICAL: Create UNIQUE lair actions that match this specific creature's environment and theme.
Consider where this creature would actually live and what environmental effects would occur there.

Environment Examples:
- Underwater lair: Whirlpools, crushing pressure, blinding ink clouds
- Volcanic lair: Lava eruptions, toxic gases, tremors
- Forest lair: Grasping vines, summoning beasts, terrain manipulation
- Corporate office: Security lockdown, conference call interference, hostile merger paperwork
- Arcane laboratory: Wild magic surges, teleportation fields, animated equipment

Example Structure (CUSTOMIZE ALL FIELDS TO CREATURE):
{
  "lairActions": {
    "lairName": "The [Thematic Lair Name]",
    "lairDescription": "The [lair] is [sensory details]. [Atmospheric description]. [Unique environmental feature that makes it memorable and dangerous].",
    "description": "On initiative count 20 (losing initiative ties), the [creature] takes a lair action to cause one of the following effects. The [creature] can't use the same effect two rounds in a row.",
    "actions": [
      {
        "name": "[Environment-Specific Action 1]",
        "desc": "[Hazard with mechanics: DC, damage, area, effect]"
      },
      {
        "name": "[Environment-Specific Action 2]",
        "desc": "[Terrain control with mechanics]"
      },
      {
        "name": "[Environment-Specific Action 3]",
        "desc": "[Environmental effect with mechanics]"
      }
    ]
  }
}

Concrete Example:
{
  "lairActions": {
    "lairName": "The Sunken Boardroom",
    "lairDescription": "The underwater conference room is lit by flickering fluorescent lights that struggle against the crushing deep-sea darkness. Waterlogged motivational posters peel from barnacle-encrusted walls, and the air (for those who can breathe it) reeks of brine and corporate desperation. A massive table dominates the space, its surface covered in contracts that somehow remain dry despite the aquatic environment.",
    "description": "On initiative count 20 (losing initiative ties), the Corporate Merperson takes a lair action to cause one of the following effects. It can't use the same effect two rounds in a row.",
    "actions": [...]
  }
}
"""
        else:
            prompt += "\n- DO NOT include lair actions (set 'lairActions' field to null)\n"
        
        # Footer with balance guidelines
        prompt += """
BALANCE AND CONSISTENCY:
- Proficiency bonus: +2 (CR 0-4), +3 (CR 5-8), +4 (CR 9-12), +5 (CR 13-16), +6 (CR 17-20), +7 (CR 21-24), +8 (CR 25-28), +9 (CR 29-30)
- Attack bonus = ability_modifier + proficiency_bonus
- Save DC = 8 + ability_modifier + proficiency_bonus
- Hit Points should match CR expectations (consult DMG CR tables)
- Armor Class should match CR expectations
- Average damage per round should align with CR offensive power
- All statistics must follow D&D 5e mathematical rules exactly

The creature should feel authentic, balanced, and exciting to use in a D&D 5e game."""
        
        return prompt
    
    
    def get_validation_prompt(self, statblock: dict) -> str:
        """Generate prompt for validating a statblock using structured outputs"""
        return f"""Review this D&D 5e creature statblock for accuracy and balance:

Creature: {statblock.get('name', 'Unknown')}
Challenge Rating: {statblock.get('challenge_rating', 'Unknown')}
Hit Points: {statblock.get('hit_points', 'Unknown')}
Armor Class: {statblock.get('armor_class', 'Unknown')}

Analyze the complete statblock for:
1. Mathematical accuracy (attack bonuses, save DCs, ability modifiers)
2. Challenge Rating appropriateness compared to actual defensive/offensive capabilities
3. D&D 5e rule compliance and internal consistency
4. Balanced offensive/defensive capabilities for the stated CR
5. Appropriate creature abilities and traits for its type and theme

Provide a comprehensive validation assessment."""
    
    def get_cr_calculation_prompt(self, statblock: dict) -> str:
        """Generate prompt for calculating challenge rating using structured outputs"""
        return f"""Calculate the appropriate Challenge Rating for this D&D 5e creature using the official DMG method:

Creature: {statblock.get('name', 'Unknown')}
Current CR: {statblock.get('challenge_rating', 'Unknown')}
Hit Points: {statblock.get('hit_points', 'Unknown')}
Armor Class: {statblock.get('armor_class', 'Unknown')}

Use the D&D 5e Dungeon Master's Guide CR calculation method:

1. Calculate Defensive Challenge Rating from:
   - Effective Hit Points (including resistances/immunities)
   - Armor Class adjustments
   - Special defensive abilities and traits

2. Calculate Offensive Challenge Rating from:
   - Average damage per round across all attacks
   - Attack bonus or spell save DC
   - Action economy and special offensive abilities
   - Spellcasting capabilities if present

3. Determine final CR as the average of defensive and offensive ratings
4. Consider special abilities that might adjust the final rating

Provide detailed calculations and reasoning for the recommended Challenge Rating."""
