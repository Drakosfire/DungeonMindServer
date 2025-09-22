"""
Performance comparison tests between old JSON validation approach and new Structured Outputs
"""

import pytest
import time
import json
import sys
import os
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from statblockgenerator.statblock_generator import StatBlockGenerator
from statblockgenerator.models.statblock_models import (
    StatBlockDetails,
    CreatureGenerationRequest,
    CreatureSize,
    CreatureType,
    Alignment,
    AbilityScores,
    SpeedObject,
    SensesObject,
    Action
)


class TestPerformanceComparison:
    """Compare performance between old and new approaches"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.generator = StatBlockGenerator()
        self.mock_statblock_data = self._create_mock_statblock_data()
    
    def _create_mock_statblock_data(self) -> Dict[str, Any]:
        """Create realistic statblock data for testing"""
        return {
            "name": "Ancient Red Dragon",
            "size": "Gargantuan",
            "type": "dragon",
            "alignment": "chaotic evil",
            "armor_class": 22,
            "hit_points": 546,
            "hit_dice": "28d20+252",
            "speed": {
                "walk": 40,
                "climb": 40,
                "fly": 80
            },
            "abilities": {
                "str": 30,
                "dex": 10,
                "con": 29,
                "intelligence": 18,
                "wis": 15,
                "cha": 23
            },
            "saving_throws": {
                "dex": 7,
                "con": 16,
                "wis": 9,
                "cha": 13
            },
            "skills": {
                "perception": 16,
                "stealth": 7
            },
            "damage_immunity": "fire",
            "senses": {
                "blindsight": 60,
                "darkvision": 120,
                "passive_perception": 26
            },
            "languages": "Common, Draconic",
            "challenge_rating": "24",
            "xp": 62000,
            "proficiency_bonus": 7,
            "actions": [
                {
                    "name": "Multiattack",
                    "desc": "The dragon can use its Frightful Presence. It then makes three attacks: one with its bite and two with its claws."
                },
                {
                    "name": "Bite",
                    "desc": "Melee Weapon Attack: +17 to hit, reach 15 ft., one target. Hit: 21 (2d10 + 10) piercing damage plus 14 (4d6) fire damage.",
                    "attack_bonus": 17,
                    "damage": "2d10+10",
                    "damage_type": "piercing"
                },
                {
                    "name": "Claw",
                    "desc": "Melee Weapon Attack: +17 to hit, reach 10 ft., one target. Hit: 17 (2d6 + 10) slashing damage.",
                    "attack_bonus": 17,
                    "damage": "2d6+10",
                    "damage_type": "slashing"
                },
                {
                    "name": "Tail",
                    "desc": "Melee Weapon Attack: +17 to hit, reach 20 ft., one target. Hit: 19 (2d8 + 10) bludgeoning damage.",
                    "attack_bonus": 17,
                    "damage": "2d8+10",
                    "damage_type": "bludgeoning"
                },
                {
                    "name": "Fire Breath",
                    "desc": "The dragon exhales fire in a 90-foot cone. Each creature in that area must make a DC 24 Dexterity saving throw, taking 91 (26d6) fire damage on a failed save, or half as much damage on a successful one.",
                    "recharge": "5-6"
                }
            ],
            "legendary_actions": {
                "actions_per_turn": 3,
                "actions": [
                    {
                        "name": "Detect",
                        "desc": "The dragon makes a Wisdom (Perception) check."
                    },
                    {
                        "name": "Tail Attack",
                        "desc": "The dragon makes a tail attack."
                    },
                    {
                        "name": "Wing Attack",
                        "desc": "The dragon beats its wings. Each creature within 15 feet of the dragon must succeed on a DC 25 Dexterity saving throw or take 17 (2d6 + 10) bludgeoning damage and be knocked prone."
                    }
                ]
            },
            "description": "The most fearsome and powerful of all chromatic dragons, ancient red dragons are engines of destruction and masters of fire.",
            "sd_prompt": "A massive ancient red dragon with glowing eyes, breathing fire, perched on a mountain of gold and treasure, dark volcanic background"
        }
    
    def test_pydantic_model_creation_performance(self):
        """Test how fast we can create StatBlockDetails objects"""
        data = self.mock_statblock_data
        
        # Time 100 model creations
        start_time = time.time()
        for _ in range(100):
            statblock = StatBlockDetails(**data)
        end_time = time.time()
        
        creation_time = end_time - start_time
        print(f"Created 100 StatBlockDetails objects in {creation_time:.4f} seconds")
        
        # Should be very fast (under 1 second for 100 creations)
        assert creation_time < 1.0
        assert statblock.name == "Ancient Red Dragon"
    
    def test_json_schema_generation_performance(self):
        """Test performance of JSON schema generation"""
        # Time schema generation
        start_time = time.time()
        schema = StatBlockDetails.model_json_schema()
        end_time = time.time()
        
        schema_time = end_time - start_time
        print(f"Generated JSON schema in {schema_time:.4f} seconds")
        
        # Schema generation should be very fast
        assert schema_time < 0.1
        assert "properties" in schema
        assert len(schema["properties"]) > 20  # Should have many properties
    
    def test_model_serialization_performance(self):
        """Test serialization performance"""
        statblock = StatBlockDetails(**self.mock_statblock_data)
        
        # Time serialization to dict
        start_time = time.time()
        for _ in range(100):
            data = statblock.dict()
        end_time = time.time()
        
        serialization_time = end_time - start_time
        print(f"Serialized 100 models to dict in {serialization_time:.4f} seconds")
        
        # Should be fast
        assert serialization_time < 1.0
        assert isinstance(data, dict)
        assert data["name"] == "Ancient Red Dragon"
    
    def test_model_validation_vs_manual_validation(self):
        """Compare Pydantic validation vs manual validation"""
        data = self.mock_statblock_data
        
        # Test Pydantic validation performance
        start_time = time.time()
        for _ in range(50):
            try:
                statblock = StatBlockDetails(**data)
                valid = True
            except Exception:
                valid = False
        pydantic_time = end_time = time.time() - start_time
        
        # Test manual validation (simulating old approach)
        def manual_validate(data):
            required_fields = [
                "name", "size", "type", "alignment", "armor_class",
                "hit_points", "hit_dice", "speed", "abilities", "senses",
                "languages", "challenge_rating", "xp", "actions",
                "description", "sd_prompt"
            ]
            
            for field in required_fields:
                if field not in data:
                    return False
            
            if "abilities" in data:
                required_abilities = ["str", "dex", "con", "intelligence", "wis", "cha"]
                abilities = data["abilities"]
                for ability in required_abilities:
                    if ability not in abilities:
                        return False
            
            return True
        
        start_time = time.time()
        for _ in range(50):
            valid = manual_validate(data)
        manual_time = time.time() - start_time
        
        print(f"Pydantic validation (50x): {pydantic_time:.4f}s")
        print(f"Manual validation (50x): {manual_time:.4f}s")
        
        # Both should be fast, but Pydantic provides much more comprehensive validation
        assert pydantic_time < 1.0
        assert manual_time < 1.0
    
    @pytest.mark.asyncio
    async def test_structured_outputs_vs_json_parsing_simulation(self):
        """Simulate the performance difference between structured outputs and JSON parsing"""
        
        # Simulate old approach: receive JSON string, parse, validate
        json_response = json.dumps(self.mock_statblock_data)
        
        # Old approach simulation
        start_time = time.time()
        for _ in range(20):
            # Parse JSON
            parsed_data = json.loads(json_response)
            
            # Manual validation (simplified)
            if "name" in parsed_data and "abilities" in parsed_data:
                # Create object
                try:
                    statblock = StatBlockDetails(**parsed_data)
                    success = True
                except Exception:
                    success = False
            else:
                success = False
        old_approach_time = time.time() - start_time
        
        # New approach simulation (structured outputs)
        start_time = time.time()
        for _ in range(20):
            # Directly create object (OpenAI guarantees schema compliance)
            statblock = StatBlockDetails(**self.mock_statblock_data)
            success = True
        new_approach_time = time.time() - start_time
        
        print(f"Old approach (JSON parsing + validation, 20x): {old_approach_time:.4f}s")
        print(f"New approach (direct model creation, 20x): {new_approach_time:.4f}s")
        
        # New approach should be faster and more reliable
        assert new_approach_time < old_approach_time
        assert success  # Should always succeed with valid data
    
    def test_memory_usage_comparison(self):
        """Test memory efficiency of new approach"""
        import tracemalloc
        
        # Test memory usage of creating many StatBlock objects
        tracemalloc.start()
        
        statblocks = []
        for i in range(50):
            data = self.mock_statblock_data.copy()
            data["name"] = f"Creature {i}"
            statblocks.append(StatBlockDetails(**data))
        
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        print(f"Memory usage for 50 StatBlocks: {peak / 1024 / 1024:.2f} MB")
        
        # Memory usage should be reasonable (under 10MB for 50 complex statblocks)
        assert peak < 10 * 1024 * 1024  # 10MB
        assert len(statblocks) == 50
    
    def test_complex_statblock_handling(self):
        """Test handling of complex statblocks with all optional fields"""
        complex_data = self.mock_statblock_data.copy()
        
        # Add complex spellcasting
        complex_data["spells"] = {
            "level": 18,
            "ability": "Charisma",
            "save_dc": 21,
            "attack_bonus": 13,
            "cantrips": [
                {"name": "Mage Hand", "level": 0},
                {"name": "Prestidigitation", "level": 0},
                {"name": "Fire Bolt", "level": 0}
            ],
            "known_spells": [
                {"name": "Fireball", "level": 3},
                {"name": "Counterspell", "level": 3},
                {"name": "Polymorph", "level": 4},
                {"name": "Dominate Person", "level": 5},
                {"name": "Disintegrate", "level": 6},
                {"name": "Teleport", "level": 7},
                {"name": "Power Word Kill", "level": 9}
            ],
            "spell_slots": {
                "level_1": 4,
                "level_2": 3,
                "level_3": 3,
                "level_4": 3,
                "level_5": 3,
                "level_6": 1,
                "level_7": 1,
                "level_8": 1,
                "level_9": 1
            }
        }
        
        # Time creation of complex statblock
        start_time = time.time()
        for _ in range(10):
            statblock = StatBlockDetails(**complex_data)
        end_time = time.time()
        
        complex_creation_time = end_time - start_time
        print(f"Created 10 complex statblocks in {complex_creation_time:.4f} seconds")
        
        # Should handle complex data efficiently
        assert complex_creation_time < 1.0
        assert statblock.spells is not None
        assert len(statblock.spells.known_spells) == 7
        assert statblock.spells.spell_slots.level_9 == 1
    
    def test_error_handling_performance(self):
        """Test performance when handling invalid data"""
        invalid_data = self.mock_statblock_data.copy()
        del invalid_data["name"]  # Remove required field
        
        # Time error handling
        start_time = time.time()
        errors = 0
        for _ in range(100):
            try:
                StatBlockDetails(**invalid_data)
            except Exception:
                errors += 1
        end_time = time.time()
        
        error_handling_time = end_time - start_time
        print(f"Handled 100 validation errors in {error_handling_time:.4f} seconds")
        
        # Error handling should be fast and catch all errors
        assert error_handling_time < 1.0
        assert errors == 100  # Should catch all errors


class TestReliabilityImprovements:
    """Test reliability improvements from structured outputs"""
    
    def test_schema_consistency(self):
        """Test that schema generation is consistent"""
        schemas = []
        for _ in range(10):
            schema = StatBlockDetails.model_json_schema()
            schemas.append(json.dumps(schema, sort_keys=True))
        
        # All schemas should be identical
        assert all(schema == schemas[0] for schema in schemas)
    
    def test_field_coverage(self):
        """Test that schema covers all expected D&D 5e fields"""
        schema = StatBlockDetails.model_json_schema()
        properties = schema["properties"]
        
        # Check for essential D&D 5e fields
        essential_fields = [
            "name", "size", "type", "alignment", "armor_class",
            "hit_points", "hit_dice", "speed", "abilities",
            "challenge_rating", "actions", "description"
        ]
        
        for field in essential_fields:
            assert field in properties, f"Missing essential field: {field}"
    
    def test_enum_validation(self):
        """Test that enums are properly validated"""
        data = {
            "name": "Test",
            "size": "InvalidSize",  # Invalid enum value
            "type": "humanoid",
            "alignment": "lawful good",
            "armor_class": 10,
            "hit_points": 10,
            "hit_dice": "2d8",
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
            "actions": [{"name": "Attack", "desc": "Basic attack"}],
            "description": "Test creature",
            "sd_prompt": "A test creature"
        }
        
        # Should raise validation error for invalid enum
        with pytest.raises(Exception):  # Pydantic ValidationError
            StatBlockDetails(**data)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])  # -s to see print output
