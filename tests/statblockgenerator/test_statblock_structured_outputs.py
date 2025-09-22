"""
Comprehensive test suite for StatBlock Generator with OpenAI Structured Outputs
"""

import pytest
import json
import os
import sys
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from statblockgenerator.statblock_generator import StatBlockGenerator
from statblockgenerator.prompts.statblock_prompts import StatBlockPromptManager
from statblockgenerator.models.statblock_models import (
    StatBlockDetails,
    CreatureGenerationRequest,
    StatBlockValidationRequest,
    CreatureSize,
    CreatureType,
    Alignment,
    AbilityScores,
    SpeedObject,
    SensesObject,
    Action
)


class TestStatBlockPromptManager:
    """Test the prompt management system"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.prompt_manager = StatBlockPromptManager()
    
    def test_prompt_manager_initialization(self):
        """Test that the prompt manager initializes correctly"""
        assert self.prompt_manager.version == "1.0.0"
        assert isinstance(self.prompt_manager, StatBlockPromptManager)
    
    def test_creature_generation_prompt_basic(self):
        """Test basic creature generation prompt"""
        request = CreatureGenerationRequest(
            description="A fierce dragon with ice breath",
            include_spells=False,
            include_legendary=False,
            challenge_rating_target="5"
        )
        
        prompt = self.prompt_manager.get_creature_generation_prompt(request)
        
        # Check that prompt contains key elements
        assert "A fierce dragon with ice breath" in prompt
        assert "Target Challenge Rating: 5" in prompt
        assert "Include Spellcasting: False" in prompt
        assert "Include Legendary Actions: False" in prompt
        assert "Design Guidelines:" in prompt
        assert "D&D 5e" in prompt
    
    def test_creature_generation_prompt_with_spells_and_legendary(self):
        """Test creature generation prompt with spells and legendary actions"""
        request = CreatureGenerationRequest(
            description="An ancient lich sorcerer",
            include_spells=True,
            include_legendary=True,
            challenge_rating_target="15"
        )
        
        prompt = self.prompt_manager.get_creature_generation_prompt(request)
        
        assert "An ancient lich sorcerer" in prompt
        assert "Target Challenge Rating: 15" in prompt
        assert "Include Spellcasting: True" in prompt
        assert "Include Legendary Actions: True" in prompt
    
    def test_validation_prompt(self):
        """Test validation prompt generation"""
        statblock_dict = {
            "name": "Test Creature",
            "challenge_rating": "5",
            "hit_points": 68,
            "armor_class": 15
        }
        
        prompt = self.prompt_manager.get_validation_prompt(statblock_dict)
        
        assert "Test Creature" in prompt
        assert "Challenge Rating: 5" in prompt
        assert "Hit Points: 68" in prompt
        assert "Armor Class: 15" in prompt
        assert "Mathematical accuracy" in prompt
    
    def test_cr_calculation_prompt(self):
        """Test CR calculation prompt generation"""
        statblock_dict = {
            "name": "Test Monster",
            "challenge_rating": "3",
            "hit_points": 45,
            "armor_class": 14
        }
        
        prompt = self.prompt_manager.get_cr_calculation_prompt(statblock_dict)
        
        assert "Test Monster" in prompt
        assert "Current CR: 3" in prompt
        assert "Hit Points: 45" in prompt
        assert "Armor Class: 14" in prompt
        assert "DMG method" in prompt
        assert "Defensive Challenge Rating" in prompt
        assert "Offensive Challenge Rating" in prompt


class TestStatBlockModels:
    """Test Pydantic model validation and schema generation"""
    
    def test_statblock_details_valid_creation(self):
        """Test creating a valid StatBlockDetails object"""
        abilities = AbilityScores(
            str=16, dex=14, con=15, intelligence=12, wis=13, cha=11
        )
        speed = SpeedObject(walk=30)
        senses = SensesObject(passive_perception=11)
        action = Action(
            name="Longsword",
            desc="Melee Weapon Attack: +5 to hit, reach 5 ft., one target. Hit: 7 (1d8 + 3) slashing damage.",
            attack_bonus=5,
            damage="1d8+3",
            damage_type="slashing"
        )
        
        statblock = StatBlockDetails(
            name="Test Warrior",
            size=CreatureSize.MEDIUM,
            type=CreatureType.HUMANOID,
            alignment=Alignment.LAWFUL_NEUTRAL,
            armor_class=14,
            hit_points=58,
            hit_dice="9d8+18",
            speed=speed,
            abilities=abilities,
            senses=senses,
            languages="Common",
            challenge_rating="1",
            xp=200,
            proficiency_bonus=2,
            actions=[action],
            description="A skilled warrior",
            sd_prompt="A medieval warrior in armor"
        )
        
        assert statblock.name == "Test Warrior"
        assert statblock.abilities.str == 16
        assert statblock.abilities.get_modifier("str") == 3
        assert len(statblock.actions) == 1
        assert statblock.actions[0].name == "Longsword"
    
    def test_statblock_json_schema_generation(self):
        """Test that StatBlockDetails generates a valid JSON schema"""
        schema = StatBlockDetails.model_json_schema()
        
        # Check that schema has required structure for OpenAI
        assert "type" in schema
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema
        
        # Check for key fields
        properties = schema["properties"]
        assert "name" in properties
        assert "size" in properties
        assert "type" in properties
        assert "abilities" in properties
        assert "actions" in properties
        
        # Check that enums are properly defined
        assert "enum" in properties["size"]
        assert "Medium" in properties["size"]["enum"]
    
    def test_ability_scores_modifier_calculation(self):
        """Test ability score modifier calculations"""
        abilities = AbilityScores(
            str=8, dex=10, con=12, intelligence=14, wis=16, cha=18
        )
        
        assert abilities.get_modifier("str") == -1
        assert abilities.get_modifier("dex") == 0
        assert abilities.get_modifier("con") == 1
        assert abilities.get_modifier("int") == 2  # Test alias
        assert abilities.get_modifier("intelligence") == 2  # Test direct
        assert abilities.get_modifier("wis") == 3
        assert abilities.get_modifier("cha") == 4
    
    def test_challenge_rating_validation(self):
        """Test challenge rating validation for various formats"""
        # Test with fraction string
        statblock_data = self._get_basic_statblock_data()
        statblock_data["challenge_rating"] = "1/4"
        statblock = StatBlockDetails(**statblock_data)
        assert statblock.challenge_rating == "1/4"
        
        # Test with integer
        statblock_data["challenge_rating"] = 5
        statblock = StatBlockDetails(**statblock_data)
        assert statblock.challenge_rating == 5
        
        # Test with float
        statblock_data["challenge_rating"] = 2.5
        statblock = StatBlockDetails(**statblock_data)
        assert statblock.challenge_rating == 2.5
    
    def _get_basic_statblock_data(self) -> Dict[str, Any]:
        """Helper to get basic valid statblock data"""
        return {
            "name": "Test Creature",
            "size": CreatureSize.MEDIUM,
            "type": CreatureType.HUMANOID,
            "alignment": Alignment.TRUE_NEUTRAL,
            "armor_class": 10,
            "hit_points": 10,
            "hit_dice": "2d8+2",
            "speed": {"walk": 30},
            "abilities": {
                "str": 10, "dex": 10, "con": 10,
                "intelligence": 10, "wis": 10, "cha": 10
            },
            "senses": {"passive_perception": 10},
            "languages": "Common",
            "challenge_rating": "1",
            "xp": 200,
            "proficiency_bonus": 2,
            "actions": [{
                "name": "Unarmed Strike",
                "desc": "Simple attack"
            }],
            "description": "A basic creature",
            "sd_prompt": "A simple humanoid"
        }


class TestStatBlockGenerator:
    """Test the main StatBlock generator with mocked OpenAI calls"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.generator = StatBlockGenerator()
    
    def test_generator_initialization_without_api_key(self):
        """Test generator initialization without OpenAI API key"""
        with patch.dict(os.environ, {}, clear=True):
            generator = StatBlockGenerator()
            assert generator.openai_client is None
    
    def test_generator_initialization_with_api_key(self):
        """Test generator initialization with OpenAI API key"""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch("statblockgenerator.statblock_generator.OpenAI") as mock_openai:
                generator = StatBlockGenerator()
                mock_openai.assert_called_once_with(api_key="test-key")
    
    @pytest.mark.asyncio
    async def test_generate_creature_without_openai_client(self):
        """Test creature generation fails gracefully without OpenAI client"""
        generator = StatBlockGenerator()
        generator.openai_client = None
        
        request = CreatureGenerationRequest(
            description="A test creature"
        )
        
        success, result = await generator.generate_creature(request)
        
        assert not success
        assert "OpenAI client not initialized" in result["error"]
    
    @pytest.mark.asyncio
    async def test_generate_creature_with_structured_outputs(self):
        """Test successful creature generation with structured outputs"""
        # Mock the OpenAI response
        mock_statblock = StatBlockDetails(
            name="Generated Creature",
            size=CreatureSize.MEDIUM,
            type=CreatureType.BEAST,
            alignment=Alignment.UNALIGNED,
            armor_class=12,
            hit_points=22,
            hit_dice="4d8+4",
            speed=SpeedObject(walk=30),
            abilities=AbilityScores(
                str=12, dex=14, con=12, intelligence=2, wis=12, cha=6
            ),
            senses=SensesObject(passive_perception=11),
            languages="—",
            challenge_rating="1/2",
            xp=100,
            proficiency_bonus=2,
            actions=[Action(
                name="Bite",
                desc="Melee Weapon Attack: +4 to hit, reach 5 ft., one target. Hit: 5 (1d6 + 2) piercing damage."
            )],
            description="A wild beast creature",
            sd_prompt="A fierce beast in a natural setting"
        )
        
        generator = StatBlockGenerator()
        generator.openai_client = Mock()
        
        # Mock the structured API call
        with patch.object(generator, '_call_openai_structured', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "success": True,
                "statblock": mock_statblock,
                "model": "gpt-4o-2024-08-06",
                "usage": {"total_tokens": 500}
            }
            
            request = CreatureGenerationRequest(
                description="A fierce beast that prowls the forest"
            )
            
            success, result = await generator.generate_creature(request)
            
            assert success
            assert "statblock" in result
            assert result["statblock"]["name"] == "Generated Creature"
            assert result["generation_info"]["structured_outputs"] is True
            mock_call.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_creature_with_openai_refusal(self):
        """Test handling of OpenAI refusal"""
        generator = StatBlockGenerator()
        generator.openai_client = Mock()
        
        with patch.object(generator, '_call_openai_structured', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "success": False,
                "error": "Generation refused",
                "refusal": "I cannot create violent content"
            }
            
            request = CreatureGenerationRequest(
                description="An extremely violent creature"
            )
            
            success, result = await generator.generate_creature(request)
            
            assert not success
            assert "Generation refused" in result["error"]
    
    def test_basic_cr_calculation(self):
        """Test basic CR calculation logic"""
        statblock = StatBlockDetails(
            **TestStatBlockModels()._get_basic_statblock_data()
        )
        statblock.hit_points = 100
        statblock.armor_class = 15
        
        generator = StatBlockGenerator()
        cr_result = generator._calculate_basic_cr(statblock)
        
        assert "defensive_cr" in cr_result
        assert "offensive_cr" in cr_result
        assert "final_cr" in cr_result
        assert isinstance(cr_result["final_cr"], int)
    
    def test_proficiency_bonus_calculation(self):
        """Test proficiency bonus calculation for different CRs"""
        generator = StatBlockGenerator()
        
        assert generator._get_proficiency_bonus_for_cr("1/4") == 2
        assert generator._get_proficiency_bonus_for_cr("2") == 2
        assert generator._get_proficiency_bonus_for_cr("5") == 3
        assert generator._get_proficiency_bonus_for_cr("9") == 4
        assert generator._get_proficiency_bonus_for_cr("17") == 6


class TestIntegrationScenarios:
    """Integration tests for complete workflows"""
    
    @pytest.mark.asyncio
    async def test_complete_generation_workflow(self):
        """Test a complete generation workflow from request to validated statblock"""
        generator = StatBlockGenerator()
        
        # Mock a complete successful generation
        mock_statblock = StatBlockDetails(
            name="Integration Test Dragon",
            size=CreatureSize.LARGE,
            type=CreatureType.DRAGON,
            alignment=Alignment.CHAOTIC_EVIL,
            armor_class=18,
            hit_points=178,
            hit_dice="17d12+85",
            speed=SpeedObject(walk=40, fly=80),
            abilities=AbilityScores(
                str=23, dex=10, con=21, intelligence=14, wis=11, cha=19
            ),
            senses=SensesObject(
                darkvision=120,
                passive_perception=10
            ),
            languages="Common, Draconic",
            challenge_rating="13",
            xp=10000,
            proficiency_bonus=5,
            actions=[
                Action(
                    name="Multiattack",
                    desc="The dragon can use its Frightful Presence. It then makes three attacks: one with its bite and two with its claws."
                ),
                Action(
                    name="Bite",
                    desc="Melee Weapon Attack: +11 to hit, reach 10 ft., one target. Hit: 17 (2d10 + 6) piercing damage plus 3 (1d6) fire damage.",
                    attack_bonus=11,
                    damage="2d10+6",
                    damage_type="piercing"
                )
            ],
            description="A mighty red dragon that terrorizes the countryside",
            sd_prompt="A massive red dragon breathing fire, wings spread, in a mountainous lair"
        )
        
        generator.openai_client = Mock()
        
        with patch.object(generator, '_call_openai_structured', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "success": True,
                "statblock": mock_statblock,
                "model": "gpt-4o-2024-08-06"
            }
            
            # Test generation
            request = CreatureGenerationRequest(
                description="A mighty red dragon",
                challenge_rating_target="13",
                include_legendary=True
            )
            
            success, result = await generator.generate_creature(request)
            
            assert success
            assert result["statblock"]["name"] == "Integration Test Dragon"
            assert result["statblock"]["challenge_rating"] == "13"
            
            # Test validation
            validation_request = StatBlockValidationRequest(
                statblock=mock_statblock,
                strict_validation=False
            )
            
            validation_success, validation_result = await generator.validate_statblock(validation_request)
            
            assert validation_success
            assert validation_result["is_valid"]


class TestPerformanceAndReliability:
    """Tests for performance characteristics and reliability"""
    
    def test_schema_generation_performance(self):
        """Test that schema generation is fast enough"""
        import time
        
        start_time = time.time()
        schema = StatBlockDetails.model_json_schema()
        end_time = time.time()
        
        # Schema generation should be very fast (< 100ms)
        assert (end_time - start_time) < 0.1
        assert schema is not None
    
    def test_model_validation_performance(self):
        """Test that model validation is performant"""
        import time
        
        data = TestStatBlockModels()._get_basic_statblock_data()
        
        start_time = time.time()
        for _ in range(100):  # Test 100 validations
            statblock = StatBlockDetails(**data)
        end_time = time.time()
        
        # Should validate 100 models in less than 1 second
        assert (end_time - start_time) < 1.0
    
    def test_prompt_generation_consistency(self):
        """Test that prompts are generated consistently"""
        prompt_manager = StatBlockPromptManager()
        
        request = CreatureGenerationRequest(
            description="A test creature",
            challenge_rating_target="5"
        )
        
        # Generate the same prompt multiple times
        prompts = [
            prompt_manager.get_creature_generation_prompt(request)
            for _ in range(10)
        ]
        
        # All prompts should be identical
        assert all(prompt == prompts[0] for prompt in prompts)
        assert len(prompts[0]) > 0


# Pytest configuration
@pytest.fixture
def sample_statblock_data():
    """Fixture providing sample statblock data"""
    return {
        "name": "Test Goblin",
        "size": "Small",
        "type": "humanoid",
        "alignment": "neutral evil",
        "armor_class": 15,
        "hit_points": 7,
        "hit_dice": "2d6",
        "speed": {"walk": 30},
        "abilities": {
            "str": 8, "dex": 14, "con": 10,
            "intelligence": 10, "wis": 8, "cha": 8
        },
        "senses": {"darkvision": 60, "passive_perception": 9},
        "languages": "Common, Goblin",
        "challenge_rating": "1/4",
        "xp": 50,
        "proficiency_bonus": 2,
        "actions": [{
            "name": "Scimitar",
            "desc": "Melee Weapon Attack: +4 to hit, reach 5 ft., one target. Hit: 5 (1d6 + 2) slashing damage."
        }],
        "description": "A small, cunning goblin warrior",
        "sd_prompt": "A green-skinned goblin with a curved sword"
    }


if __name__ == "__main__":
    # Run tests if script is executed directly
    pytest.main([__file__, "-v"])
