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
        challenge_rating = request.challenge_rating_target or "1"
        include_spells = request.include_spells
        include_legendary = request.include_legendary
        include_lair = request.include_lair
        
        # Base prompt with core requirements
        prompt = f"""Create a complete D&D 5e creature statblock based on this description: "{description}"

Target Challenge Rating: {challenge_rating}

CORE REQUIREMENTS:
1. Name, size, type, alignment matching the description
2. Appropriate ability scores for CR {challenge_rating}
3. Armor Class, Hit Points, and Hit Dice consistent with CR
4. Movement speeds appropriate for creature type
5. Skills, senses, and languages fitting the theme
6. At least 2-4 regular actions (attacks, special abilities)
7. Engaging description that brings the creature to life
8. Stable Diffusion prompt for artwork generation
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
- Provide exactly 3 legendary actions with varying costs
- Each action must have: name, cost (1-3), and detailed description
- Legendary actions are weaker than regular actions
- Common action patterns:
  * Detection/Movement (cost 1): Perception check or move up to half speed
  * Attack (cost 2): Single weapon attack or cantrip
  * Powerful Ability (cost 3): Area effect, spell cast, or signature move

Example Legendary Actions Structure:
{
  "legendaryActions": {
    "description": "The ancient dragon can take 3 legendary actions, choosing from the options below. Only one legendary action can be used at a time and only at the end of another creature's turn. The dragon regains spent legendary actions at the start of its turn.",
    "actions": [
      {
        "name": "Detect",
        "cost": 1,
        "desc": "The dragon makes a Wisdom (Perception) check."
      },
      {
        "name": "Tail Attack",
        "cost": 2,
        "desc": "The dragon makes one tail attack."
      },
      {
        "name": "Wing Attack",
        "cost": 3,
        "desc": "The dragon beats its wings. Each creature within 15 feet must succeed on a DC 19 Dexterity saving throw or take 15 (2d6 + 8) bludgeoning damage and be knocked prone. The dragon can then fly up to half its flying speed."
      }
    ]
  }
}
"""
        else:
            prompt += "\n- DO NOT include legendary actions (set 'legendaryActions' field to null)\n"
        
        # Conditional: Lair Actions
        if include_lair:
            prompt += """
LAIR ACTIONS REQUIREMENTS (REQUIRED - DO NOT SET TO NULL):
- Populate the 'lairActions' field with a complete LairActionsBlock object
- Include a description explaining lair actions occur on initiative count 20
- Provide 3-4 lair actions themed to the creature's environment
- Each action must have: name and detailed description
- Lair actions create environmental hazards or control terrain
- Match actions to environment (water/aquatic, tremors/underground, wind/aerial, etc.)
- Each action should require saving throws or attack rolls with appropriate DCs

Example Lair Actions Structure:
{
  "lairActions": {
    "description": "On initiative count 20 (losing initiative ties), the dragon takes a lair action to cause one of the following effects. The dragon can't use the same effect two rounds in a row.",
    "actions": [
      {
        "name": "Magma Eruption",
        "desc": "Magma erupts from a point on the ground the dragon can see within 120 feet. Any creature within 20 feet of that point must make a DC 15 Dexterity saving throw or take 21 (6d6) fire damage."
      },
      {
        "name": "Tremor",
        "desc": "The lair shakes. Each creature on the ground within 60 feet of the dragon must succeed on a DC 15 Dexterity saving throw or be knocked prone."
      },
      {
        "name": "Volcanic Gas",
        "desc": "A cloud of poisonous, volcanic gas fills a 20-foot-radius sphere centered on a point the dragon can see within 120 feet. The cloud spreads around corners and lasts until initiative count 20 on the next round. Each creature that starts its turn in the cloud must make a DC 13 Constitution saving throw or be poisoned until the end of its turn."
      }
    ]
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
