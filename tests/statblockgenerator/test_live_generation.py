"""
Live tests for StatBlock generation with real OpenAI API
These tests require OPENAI_API_KEY environment variable and will be skipped if not available
"""

import pytest
import os
import sys
import asyncio
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from statblockgenerator.statblock_generator import StatBlockGenerator
from statblockgenerator.models.statblock_models import (
    CreatureGenerationRequest,
    StatBlockValidationRequest,
    StatBlockDetails
)


# Skip all tests in this file if no OpenAI API key
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OpenAI API key not available - skipping live tests"
)


class TestLiveGeneration:
    """Live tests with real OpenAI API calls"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.generator = StatBlockGenerator()
        assert self.generator.openai_client is not None, "OpenAI client not initialized"
    
    @pytest.mark.asyncio
    @pytest.mark.slow  # Mark as slow test
    async def test_simple_creature_generation(self):
        """Test generating a simple creature"""
        request = CreatureGenerationRequest(
            description="A small forest sprite that can become invisible",
            challenge_rating_target="1/4",
            include_spells=False,
            include_legendary=False
        )
        
        success, result = await self.generator.generate_creature(request)
        
        # Should succeed
        assert success, f"Generation failed: {result.get('error', 'Unknown error')}"
        assert "statblock" in result
        
        statblock_data = result["statblock"]
        
        # Validate basic structure
        assert "name" in statblock_data
        assert "challenge_rating" in statblock_data
        assert "description" in statblock_data
        assert "sd_prompt" in statblock_data
        
        # Validate that it's a proper StatBlockDetails object
        statblock = StatBlockDetails(**statblock_data)
        assert statblock.name is not None
        assert len(statblock.name) > 0
        
        print(f"Generated creature: {statblock.name}")
        print(f"Challenge Rating: {statblock.challenge_rating}")
        print(f"Description: {statblock.description[:100]}...")
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_spellcaster_generation(self):
        """Test generating a creature with spellcasting"""
        request = CreatureGenerationRequest(
            description="A wise old wizard who has mastered elemental magic",
            challenge_rating_target="5",
            include_spells=True,
            include_legendary=False
        )
        
        success, result = await self.generator.generate_creature(request)
        
        assert success, f"Generation failed: {result.get('error', 'Unknown error')}"
        
        statblock = StatBlockDetails(**result["statblock"])
        
        # Should have spellcasting
        assert statblock.spells is not None, "Spellcaster should have spells"
        assert statblock.spells.level > 0, "Should have spellcaster level"
        assert statblock.spells.save_dc > 0, "Should have spell save DC"
        
        # Should have some spells
        if statblock.spells.cantrips:
            assert len(statblock.spells.cantrips) > 0
        if statblock.spells.known_spells:
            assert len(statblock.spells.known_spells) > 0
        
        print(f"Generated spellcaster: {statblock.name}")
        print(f"Spellcaster Level: {statblock.spells.level}")
        print(f"Spell Save DC: {statblock.spells.save_dc}")
        if statblock.spells.cantrips:
            print(f"Cantrips: {[c.name for c in statblock.spells.cantrips]}")
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_legendary_creature_generation(self):
        """Test generating a creature with legendary actions"""
        request = CreatureGenerationRequest(
            description="An ancient dragon lord who rules from a volcanic lair",
            challenge_rating_target="15",
            include_spells=False,
            include_legendary=True
        )
        
        success, result = await self.generator.generate_creature(request)
        
        assert success, f"Generation failed: {result.get('error', 'Unknown error')}"
        
        statblock = StatBlockDetails(**result["statblock"])
        
        # Should have legendary actions
        assert statblock.legendary_actions is not None, "Should have legendary actions"
        assert statblock.legendary_actions.actions_per_turn > 0
        assert len(statblock.legendary_actions.actions) > 0
        
        # High CR creature should have high stats
        assert statblock.proficiency_bonus >= 5  # CR 15+ should have high prof bonus
        assert statblock.hit_points > 100  # Should be tough
        
        print(f"Generated legendary creature: {statblock.name}")
        print(f"Legendary Actions per Turn: {statblock.legendary_actions.actions_per_turn}")
        print(f"Number of Legendary Actions: {len(statblock.legendary_actions.actions)}")
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_complex_creature_with_all_features(self):
        """Test generating a complex creature with all features"""
        request = CreatureGenerationRequest(
            description="An archlich sorcerer-king who commands undead legions and casts devastating spells",
            challenge_rating_target="20",
            include_spells=True,
            include_legendary=True
        )
        
        success, result = await self.generator.generate_creature(request)
        
        assert success, f"Generation failed: {result.get('error', 'Unknown error')}"
        
        statblock = StatBlockDetails(**result["statblock"])
        
        # Should have all features
        assert statblock.spells is not None
        assert statblock.legendary_actions is not None
        
        # Should be very powerful
        assert float(str(statblock.challenge_rating).replace("/", ".")) >= 15
        assert statblock.hit_points > 200
        assert statblock.proficiency_bonus >= 6
        
        # Should have resistances/immunities appropriate for undead
        print(f"Generated archlich: {statblock.name}")
        print(f"Challenge Rating: {statblock.challenge_rating}")
        print(f"Hit Points: {statblock.hit_points}")
        print(f"Spellcaster Level: {statblock.spells.level}")
        
        # Validate the statblock is internally consistent
        validation_request = StatBlockValidationRequest(
            statblock=statblock,
            strict_validation=False
        )
        
        validation_success, validation_result = await self.generator.validate_statblock(validation_request)
        assert validation_success
        
        # Should pass basic validation
        assert validation_result["is_valid"] or len(validation_result["errors"]) == 0
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_generation_consistency(self):
        """Test that multiple generations produce valid but different results"""
        base_description = "A magical creature of the forest"
        
        results = []
        for i in range(3):
            request = CreatureGenerationRequest(
                description=f"{base_description} (variant {i+1})",
                challenge_rating_target="2"
            )
            
            success, result = await self.generator.generate_creature(request)
            assert success
            
            statblock = StatBlockDetails(**result["statblock"])
            results.append(statblock)
        
        # All should be valid
        assert len(results) == 3
        
        # Should have different names (creativity test)
        names = [r.name for r in results]
        assert len(set(names)) > 1, "Should generate different creature names"
        
        # All should have reasonable stats for CR 2
        for statblock in results:
            cr_num = float(str(statblock.challenge_rating).replace("/", "."))
            assert 1 <= cr_num <= 4, f"CR should be around 2, got {statblock.challenge_rating}"
            assert 20 <= statblock.hit_points <= 100, "HP should be reasonable for CR 2"
        
        print("Generated creatures:")
        for i, statblock in enumerate(results):
            print(f"  {i+1}. {statblock.name} (CR {statblock.challenge_rating}, HP {statblock.hit_points})")
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_error_handling_with_problematic_descriptions(self):
        """Test how the system handles edge cases and problematic descriptions"""
        
        # Very short description
        request = CreatureGenerationRequest(
            description="Cat",
            challenge_rating_target="1/8"
        )
        
        success, result = await self.generator.generate_creature(request)
        
        # Should either succeed or fail gracefully
        if success:
            statblock = StatBlockDetails(**result["statblock"])
            assert "cat" in statblock.name.lower() or "feline" in statblock.name.lower()
        else:
            assert "error" in result
        
        # Very long description
        long_description = "A " + "very " * 100 + "complicated magical creature with many abilities"
        request = CreatureGenerationRequest(
            description=long_description,
            challenge_rating_target="1"
        )
        
        success, result = await self.generator.generate_creature(request)
        
        # Should handle long descriptions
        if success:
            statblock = StatBlockDetails(**result["statblock"])
            assert len(statblock.name) < 100  # Name should be reasonable length
        else:
            # If it fails, should fail gracefully
            assert "error" in result
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_challenge_rating_accuracy(self):
        """Test that generated creatures match their target challenge ratings reasonably well"""
        test_crs = ["1/4", "1", "5", "10"]
        
        for target_cr in test_crs:
            request = CreatureGenerationRequest(
                description=f"A balanced creature suitable for CR {target_cr} encounters",
                challenge_rating_target=target_cr
            )
            
            success, result = await self.generator.generate_creature(request)
            assert success, f"Failed to generate CR {target_cr} creature"
            
            statblock = StatBlockDetails(**result["statblock"])
            
            # Calculate CR analysis
            cr_success, cr_result = await self.generator.calculate_challenge_rating(statblock)
            
            if cr_success:
                print(f"CR {target_cr} creature '{statblock.name}':")
                print(f"  Generated CR: {statblock.challenge_rating}")
                print(f"  Calculated CR: {cr_result.get('recommended_cr', 'N/A')}")
                print(f"  Hit Points: {statblock.hit_points}")
                print(f"  Armor Class: {statblock.armor_class}")


class TestErrorConditions:
    """Test error conditions and edge cases"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.generator = StatBlockGenerator()
    
    @pytest.mark.asyncio
    async def test_no_api_key_handling(self):
        """Test behavior when no API key is available"""
        # Temporarily remove API key
        original_client = self.generator.openai_client
        self.generator.openai_client = None
        
        try:
            request = CreatureGenerationRequest(
                description="A test creature"
            )
            
            success, result = await self.generator.generate_creature(request)
            
            assert not success
            assert "OpenAI client not initialized" in result["error"]
        
        finally:
            # Restore client
            self.generator.openai_client = original_client


@pytest.mark.integration
class TestGenerationWorkflow:
    """Test complete generation workflows"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.generator = StatBlockGenerator()
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_full_creature_creation_workflow(self):
        """Test a complete creature creation and validation workflow"""
        
        # Step 1: Generate creature
        request = CreatureGenerationRequest(
            description="A forest guardian that protects ancient trees",
            challenge_rating_target="3",
            include_spells=True,
            include_legendary=False
        )
        
        print("Step 1: Generating creature...")
        gen_success, gen_result = await self.generator.generate_creature(request)
        assert gen_success
        
        statblock = StatBlockDetails(**gen_result["statblock"])
        print(f"Generated: {statblock.name}")
        
        # Step 2: Validate creature
        print("Step 2: Validating creature...")
        validation_request = StatBlockValidationRequest(
            statblock=statblock,
            strict_validation=True
        )
        
        val_success, val_result = await self.generator.validate_statblock(validation_request)
        assert val_success
        print(f"Validation result: {val_result['is_valid']}")
        
        # Step 3: Calculate CR
        print("Step 3: Calculating challenge rating...")
        cr_success, cr_result = await self.generator.calculate_challenge_rating(statblock)
        assert cr_success
        
        print(f"Original CR: {statblock.challenge_rating}")
        print(f"Calculated CR: {cr_result.get('recommended_cr', 'N/A')}")
        
        # Final validation: creature should be usable
        assert statblock.name is not None
        assert len(statblock.actions) > 0
        assert statblock.hit_points > 0
        assert statblock.armor_class > 0
        
        print("Workflow completed successfully!")


if __name__ == "__main__":
    # Run with specific markers
    pytest.main([
        __file__,
        "-v",
        "-s",  # Show print output
        "-m", "not slow",  # Skip slow tests by default
        "--tb=short"  # Shorter traceback format
    ])
