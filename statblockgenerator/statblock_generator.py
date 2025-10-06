"""
Core StatBlock generation logic for D&D 5e creatures using OpenAI Structured Outputs
"""

import logging
import json
import asyncio
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from openai import OpenAI
import os

from .models.statblock_models import (
    StatBlockDetails, 
    CreatureGenerationRequest,
    StatBlockValidationRequest
)
from .prompts.statblock_prompts import StatBlockPromptManager

logger = logging.getLogger(__name__)

class StatBlockGenerator:
    """
    Main StatBlock generation engine following CardGenerator patterns
    """
    
    def __init__(self):
        self.prompt_manager = StatBlockPromptManager()
        self.openai_client = None
        
        # Initialize OpenAI client if API key is available
        api_key = os.environ.get('OPENAI_API_KEY')
        if api_key:
            self.openai_client = OpenAI(api_key=api_key)
            logger.info("StatBlockGenerator initialized with OpenAI client")
        else:
            logger.warning("No OpenAI API key found - AI generation will not work")
    
    async def generate_creature(self, request: CreatureGenerationRequest) -> Tuple[bool, Dict[str, Any]]:
        """
        Generate a complete D&D 5e creature statblock using OpenAI Structured Outputs
        
        Args:
            request: Generation request with description and options
            
        Returns:
            Tuple of (success, result_data)
        """
        try:
            logger.info(f"Generating creature from description: {request.description[:100]}...")
            
            if not self.openai_client:
                return False, {"error": "OpenAI client not initialized"}
            
            # Prepare simplified prompt (no JSON schema instructions needed)
            prompt = self.prompt_manager.get_creature_generation_prompt(request)
            
            # Call OpenAI API with structured outputs
            response = await self._call_openai_structured(prompt, StatBlockDetails)
            
            if not response["success"]:
                return False, response
            
            # OpenAI guarantees schema compliance, so we get a valid StatBlockDetails directly
            statblock = response["statblock"]
            statblock.created_at = datetime.now()
            statblock.last_modified = datetime.now()
            
            logger.info(f"Successfully generated creature: {statblock.name}")
            
            # Serialize with camelCase aliases for frontend
            serialized_statblock = statblock.model_dump(by_alias=True)
            
            # Debug: Log special features to verify serialization
            if serialized_statblock.get('spells'):
                logger.info(f"Spells serialized with keys: {list(serialized_statblock['spells'].keys())}")
            if serialized_statblock.get('legendaryActions'):
                logger.info(f"Legendary actions count: {len(serialized_statblock['legendaryActions'].get('actions', []))}")
            if serialized_statblock.get('lairActions'):
                logger.info(f"Lair actions count: {len(serialized_statblock['lairActions'].get('actions', []))}")
            
            return True, {
                "statblock": serialized_statblock,
                "generation_info": {
                    "prompt_version": self.prompt_manager.version,
                    "model_used": "gpt-4o-2024-08-06",
                    "generation_time": datetime.now().isoformat(),
                    "structured_outputs": True
                }
            }
                
        except Exception as e:
            logger.error(f"Error generating creature: {str(e)}")
            return False, {"error": "Generation failed", "details": str(e)}
    
    async def validate_statblock(self, request: StatBlockValidationRequest) -> Tuple[bool, Dict[str, Any]]:
        """
        Validate a D&D 5e statblock for accuracy and balance
        
        Args:
            request: Validation request with statblock data
            
        Returns:
            Tuple of (success, validation_results)
        """
        try:
            logger.info(f"Validating statblock: {request.statblock.name}")
            
            # Basic Pydantic validation already passed if we got here
            basic_validation = {
                "is_valid": True,
                "warnings": [],
                "errors": [],
                "suggestions": []
            }
            
            # Advanced validation with AI if enabled and available
            if request.strict_validation and self.openai_client:
                statblock_dict = request.statblock.dict()
                prompt = self.prompt_manager.get_validation_prompt(statblock_dict)
                
                ai_response = await self._call_openai(prompt)
                if ai_response["success"]:
                    # For now, use the basic response - could add structured validation response model later
                    basic_validation["ai_analysis"] = ai_response["content"]
            
            # Perform basic rule checks
            rule_validation = self._perform_basic_validation(request.statblock)
            
            # Merge validations
            final_validation = {
                "is_valid": basic_validation["is_valid"] and rule_validation["is_valid"],
                "warnings": basic_validation["warnings"] + rule_validation["warnings"],
                "errors": basic_validation["errors"] + rule_validation["errors"],
                "suggestions": basic_validation["suggestions"] + rule_validation["suggestions"],
                "calculated_cr": rule_validation.get("calculated_cr"),
                "validation_type": "strict" if request.strict_validation else "basic"
            }
            
            return True, final_validation
            
        except Exception as e:
            logger.error(f"Error validating statblock: {str(e)}")
            return False, {"error": "Validation failed", "details": str(e)}
    
    async def calculate_challenge_rating(self, statblock: StatBlockDetails) -> Tuple[bool, Dict[str, Any]]:
        """
        Calculate appropriate challenge rating for a creature
        
        Args:
            statblock: Creature statblock to analyze
            
        Returns:
            Tuple of (success, cr_analysis)
        """
        try:
            logger.info(f"Calculating CR for: {statblock.name}")
            
            # Basic CR calculation using DMG guidelines
            basic_cr = self._calculate_basic_cr(statblock)
            
            # Enhanced calculation with AI if available
            if self.openai_client:
                statblock_dict = statblock.dict()
                prompt = self.prompt_manager.get_cr_calculation_prompt(statblock_dict)
                
                ai_response = await self._call_openai(prompt)
                if ai_response["success"]:
                    return True, {
                        "basic_calculation": basic_cr,
                        "ai_analysis": ai_response["content"],
                        "recommended_cr": basic_cr["final_cr"]  # Use basic calculation for now
                    }
            
            return True, {
                "basic_calculation": basic_cr,
                "recommended_cr": basic_cr["final_cr"]
            }
            
        except Exception as e:
            logger.error(f"Error calculating CR: {str(e)}")
            return False, {"error": "CR calculation failed", "details": str(e)}
    
    def _make_schema_strict(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform Pydantic schema for OpenAI structured outputs strict mode.
        
        Requirements:
        1. All objects must have 'additionalProperties: false'
        2. All properties must be in the 'required' array
        3. Optional fields should be handled by allowing null in their type
        4. $ref cannot have additional keywords (description, default, etc.)
        5. $defs section must also be cleaned
        """
        import copy
        
        # Deep copy to avoid mutating original
        schema = copy.deepcopy(schema)
        
        # CRITICAL: Process $defs section FIRST (Hypothesis 2)
        # This is where referenced types live (like SpellSlots)
        if "$defs" in schema:
            logger.info(f"Found $defs with {len(schema['$defs'])} definitions")
            for def_name in list(schema["$defs"].keys()):
                logger.info(f"Processing definition: {def_name}")
                schema["$defs"][def_name] = self._clean_schema_node(schema["$defs"][def_name])
        
        # Then process the main schema
        schema = self._clean_schema_node(schema)
        
        return schema
    
    def _clean_schema_node(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Clean a single schema node (recursive helper for _make_schema_strict)
        """
        if not isinstance(schema, dict):
            return schema
        
        # FIRST: Handle nullable $ref (anyOf with $ref and null) BEFORE other processing
        # This is a special case: {"anyOf": [{"$ref": "..."}, {"type": "null"}], "default": null, ...}
        # OpenAI strict mode doesn't allow $ref with sibling keywords
        if "anyOf" in schema:
            any_of_types = schema["anyOf"]
            non_null_types = [t for t in any_of_types if t.get("type") != "null"]
            has_null = any(t.get("type") == "null" for t in any_of_types)
            
            # Check if the non-null type is a $ref
            if has_null and len(non_null_types) == 1 and "$ref" in non_null_types[0]:
                # Nullable $ref - we need to keep anyOf structure
                # OpenAI doesn't allow {"$ref": "...", "default": null}
                # So we keep it as anyOf but clean up the structure
                return {
                    "anyOf": [
                        {"$ref": non_null_types[0]["$ref"]},
                        {"type": "null"}
                    ]
                }
            elif has_null and len(non_null_types) == 1:
                # Nullable non-$ref type - can flatten to type array
                actual_type = non_null_types[0]
                # Start fresh with just the actual type
                result = {}
                for key, value in actual_type.items():
                    result[key] = value
                # Add null to type
                if "type" in result:
                    result["type"] = [result["type"], "null"]
                return self._clean_schema_node(result)
        
        # SECOND: Handle $ref with extra keywords - must be done before any other processing
        if "$ref" in schema and len(schema) > 1:
            # $ref must be alone - return a clean $ref
            logger.debug(f"Cleaning $ref with extra keys: {list(schema.keys())}")
            return {"$ref": schema["$ref"]}
        
        # THIRD: Recursively process nested schemas BEFORE modifying current schema
        # This ensures all nested $refs are cleaned up first
        for key, value in list(schema.items()):  # Use list() to avoid dict size change during iteration
            if isinstance(value, dict):
                schema[key] = self._clean_schema_node(value)
            elif isinstance(value, list):
                schema[key] = [self._clean_schema_node(item) if isinstance(item, dict) else item for item in value]
        
        # FOURTH: Add additionalProperties: false to objects
        if schema.get("type") == "object":
            schema["additionalProperties"] = False
            
            # Make sure all properties are required
            # OpenAI strict mode requires all properties to be in required array
            if "properties" in schema:
                all_props = list(schema["properties"].keys())
                schema["required"] = all_props
        
        return schema
    
    async def _call_openai_structured(self, prompt: str, response_model, model: str = "gpt-4o-2024-08-06") -> Dict[str, Any]:
        """
        Call OpenAI API with Structured Outputs
        
        Args:
            prompt: Prompt to send
            response_model: Pydantic model for structured response
            model: Model to use (must support structured outputs: gpt-4o-2024-08-06 or gpt-4o-mini)
            
        Returns:
            Response dictionary with parsed statblock
        """
        try:
            # Convert Pydantic model to JSON schema for OpenAI
            schema = response_model.model_json_schema()
            
            logger.info("=" * 80)
            logger.info("ORIGINAL PYDANTIC SCHEMA (first 1000 chars):")
            logger.info(json.dumps(schema, indent=2)[:1000])
            logger.info("=" * 80)
            
            # Make schema strict (add additionalProperties: false to all objects)
            schema = self._make_schema_strict(schema)
            
            logger.info("=" * 80)
            logger.info("TRANSFORMED STRICT SCHEMA (full):")
            logger.info(json.dumps(schema, indent=2))
            logger.info("=" * 80)
            
            response = await asyncio.to_thread(
                self.openai_client.chat.completions.create,
                model=model,
                messages=[
                    {"role": "system", "content": "You are an expert D&D 5e game designer."},
                    {"role": "user", "content": prompt}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "statblock_generation",
                        "strict": True,
                        "schema": schema
                    }
                },
                temperature=0.7
            )
            
            # Check for refusal
            message = response.choices[0].message
            if hasattr(message, 'refusal') and message.refusal:
                logger.warning(f"OpenAI refused generation request: {message.refusal}")
                return {
                    "success": False,
                    "error": "Generation refused",
                    "refusal": message.refusal
                }
            
            # Parse the structured response directly into our model
            content = message.content
            statblock_data = json.loads(content)
            statblock = response_model(**statblock_data)
            
            return {
                "success": True,
                "statblock": statblock,
                "model": model,
                "usage": response.usage.dict() if response.usage else None
            }
            
        except Exception as e:
            logger.error(f"OpenAI Structured Outputs API error: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _call_openai(self, prompt: str, model: str = "gpt-4") -> Dict[str, Any]:
        """
        Legacy OpenAI API call for non-structured responses (validation, CR calculation)
        
        Args:
            prompt: Prompt to send
            model: Model to use
            
        Returns:
            Response dictionary
        """
        try:
            response = await asyncio.to_thread(
                self.openai_client.chat.completions.create,
                model=model,
                messages=[
                    {"role": "system", "content": "You are an expert D&D 5e game designer. Respond only with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=4000
            )
            
            content = response.choices[0].message.content.strip()
            
            return {
                "success": True,
                "content": content,
                "model": model,
                "usage": response.usage.dict() if response.usage else None
            }
            
        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _perform_basic_validation(self, statblock: StatBlockDetails) -> Dict[str, Any]:
        """
        Perform basic D&D 5e rule validation
        
        Args:
            statblock: Statblock to validate
            
        Returns:
            Validation results
        """
        warnings = []
        errors = []
        suggestions = []
        
        # Validate ability score modifiers
        abilities = statblock.abilities
        ability_mapping = {
            "str": "str",
            "dex": "dex", 
            "con": "con",
            "int": "intelligence",  # Handle the alias
            "wis": "wis",
            "cha": "cha"
        }
        
        for ability_name in ["str", "dex", "con", "int", "wis", "cha"]:
            field_name = ability_mapping[ability_name]
            score = getattr(abilities, field_name)
            if score < 1 or score > 30:
                errors.append(f"{ability_name.upper()} score {score} is outside valid range (1-30)")
            elif score < 6:
                warnings.append(f"{ability_name.upper()} score {score} is unusually low")
            elif score > 20:
                suggestions.append(f"{ability_name.upper()} score {score} is very high - consider if appropriate for CR")
        
        # Validate proficiency bonus
        expected_pb = self._get_proficiency_bonus_for_cr(statblock.challenge_rating)
        if statblock.proficiency_bonus != expected_pb:
            errors.append(f"Proficiency bonus {statblock.proficiency_bonus} doesn't match CR {statblock.challenge_rating} (expected {expected_pb})")
        
        # Validate hit points vs hit dice
        if statblock.hit_dice:
            estimated_hp = self._estimate_hp_from_dice(statblock.hit_dice, abilities.con)
            hp_diff = abs(statblock.hit_points - estimated_hp)
            if hp_diff > statblock.hit_points * 0.2:  # 20% tolerance
                warnings.append(f"Hit points {statblock.hit_points} seem inconsistent with hit dice {statblock.hit_dice}")
        
        # Validate passive perception
        wis_mod = abilities.get_modifier("wis")
        base_perception = 10 + wis_mod
        
        # Check if creature has perception skill
        perception_bonus = 0
        if statblock.skills and "perception" in statblock.skills:
            perception_bonus = statblock.skills["perception"] - wis_mod
            base_perception += perception_bonus
        
        if statblock.senses.passive_perception != base_perception:
            warnings.append(f"Passive Perception {statblock.senses.passive_perception} doesn't match calculated value {base_perception}")
        
        return {
            "is_valid": len(errors) == 0,
            "warnings": warnings,
            "errors": errors,
            "suggestions": suggestions,
            "calculated_cr": self._calculate_basic_cr(statblock)["final_cr"]
        }
    
    def _calculate_basic_cr(self, statblock: StatBlockDetails) -> Dict[str, Any]:
        """
        Calculate basic challenge rating using DMG guidelines
        
        Args:
            statblock: Statblock to analyze
            
        Returns:
            CR calculation breakdown
        """
        # Simplified CR calculation - in a full implementation this would be more complex
        
        # Defensive CR based on HP and AC
        hp = statblock.hit_points
        ac = statblock.armor_class
        
        # Basic defensive CR lookup (simplified)
        defensive_cr = 0
        if hp >= 400:
            defensive_cr = 17
        elif hp >= 300:
            defensive_cr = 13
        elif hp >= 200:
            defensive_cr = 10
        elif hp >= 100:
            defensive_cr = 5
        elif hp >= 50:
            defensive_cr = 2
        else:
            defensive_cr = 0
        
        # Adjust for AC
        if ac >= 19:
            defensive_cr += 2
        elif ac >= 17:
            defensive_cr += 1
        elif ac <= 13:
            defensive_cr -= 1
        
        # Offensive CR based on damage and attack bonus
        offensive_cr = 1  # Default
        
        # Look at first action for damage estimation
        if statblock.actions:
            first_action = statblock.actions[0]
            if first_action.attack_bonus:
                if first_action.attack_bonus >= 11:
                    offensive_cr = 8
                elif first_action.attack_bonus >= 8:
                    offensive_cr = 4
                elif first_action.attack_bonus >= 5:
                    offensive_cr = 2
        
        # Final CR is average
        final_cr = max(0, (defensive_cr + offensive_cr) // 2)
        
        return {
            "defensive_cr": defensive_cr,
            "offensive_cr": offensive_cr,
            "final_cr": final_cr,
            "reasoning": f"Defensive CR {defensive_cr} (HP: {hp}, AC: {ac}), Offensive CR {offensive_cr}"
        }
    
    def _get_proficiency_bonus_for_cr(self, cr: str) -> int:
        """Get expected proficiency bonus for a challenge rating"""
        try:
            if isinstance(cr, str):
                if '/' in cr:
                    cr_num = eval(cr)  # Handle fractions like "1/4"
                else:
                    cr_num = float(cr)
            else:
                cr_num = float(cr)
            
            if cr_num <= 4:
                return 2
            elif cr_num <= 8:
                return 3
            elif cr_num <= 12:
                return 4
            elif cr_num <= 16:
                return 5
            elif cr_num <= 20:
                return 6
            else:
                return 7
                
        except:
            return 2  # Default
    
    def _estimate_hp_from_dice(self, hit_dice: str, con_score: int) -> int:
        """Estimate hit points from hit dice string"""
        try:
            # Parse hit dice like "8d8+16"
            import re
            match = re.match(r'(\d+)d(\d+)([+-]\d+)?', hit_dice)
            if not match:
                return 0
            
            num_dice = int(match.group(1))
            die_size = int(match.group(2))
            modifier = int(match.group(3) or 0)
            
            # Average roll
            avg_roll = (die_size + 1) / 2
            estimated_hp = int(num_dice * avg_roll + modifier)
            
            return estimated_hp
            
        except:
            return 0
