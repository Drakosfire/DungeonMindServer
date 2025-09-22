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
        Generate prompt for creating D&D 5e creature statblocks using OpenAI Structured Outputs
        
        Args:
            request: CreatureGenerationRequest with all parameters
        """
        description = request.description
        challenge_rating = request.challenge_rating_target or "1"
        include_spells = request.include_spells
        include_legendary = request.include_legendary
        
        # Clean, focused prompt since OpenAI handles schema compliance automatically
        prompt = f"""Create a complete D&D 5e creature statblock based on this description: "{description}"

Target Challenge Rating: {challenge_rating}
Include Spellcasting: {include_spells}
Include Legendary Actions: {include_legendary}

Design Guidelines:
1. Ensure the creature fits the target Challenge Rating
2. Balance offensive and defensive capabilities appropriately
3. Include appropriate resistances/immunities for the creature type
4. Make sure all statistics are mathematically consistent with D&D 5e rules
5. Create engaging special abilities that match the creature's theme
6. Generate a vivid description that brings the creature to life
7. Include a detailed Stable Diffusion prompt for artwork generation

The creature should feel authentic to D&D 5e and match the provided description while being balanced for its Challenge Rating."""
        
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
