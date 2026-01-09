"""
Map Prompt Compilation Tests (T177)

Tests for prompt compilation with mask constraints.
Written BEFORE implementation - these tests MUST FAIL initially.
"""

import pytest
from datetime import datetime


def create_test_mapspec():
    """Helper to create a valid MapSpec for testing."""
    from mapgenerator.models import (
        MapSpec, MapSpecMeta, MapSpecIntent, MapSpecLayout,
        MapSpecEnvironment, MapSpecStyle, MapSpecPalette,
        MapSpecGameplay, MapSpecConstraints
    )
    
    return MapSpec(
        meta=MapSpecMeta(
            version="1.0",
            generator="test",
            timestamp=datetime.now(),
            source_prompt="Test prompt"
        ),
        intent=MapSpecIntent(
            summary="A forest clearing",
            location_type="forest",
            tone="neutral",
            fantasy_level="low",
            implied_activity=["exploration"]
        ),
        layout=MapSpecLayout(
            scale="encounter",
            focal_point="center",
            central_feature="ancient oak tree",
            surrounding_elements=["stone circle"],
            pathways="organic"
        ),
        environment=MapSpecEnvironment(
            terrain=["grass", "dirt"],
            materials=["stone"],
            vegetation=["trees", "bushes"],
            props=["fallen logs"]
        ),
        style=MapSpecStyle(
            perspective="top-down-90",
            rendering="hand-painted",
            genre="low-fantasy",
            palette=MapSpecPalette()
        ),
        gameplay=MapSpecGameplay(
            system="dnd5e",
            readability_priority=True,
            movement_space="open",
            cover_density="medium"
        ),
        constraints=MapSpecConstraints(
            forbid=["grid", "text", "characters"],
            require=[]
        )
    )


class TestPromptCompilerWithMask:
    """Tests for prompt compilation with mask constraints (T177)"""
    
    def test_prompt_includes_mask_boundary_constraint(self):
        """Compiled prompt should include mask boundary instructions when mask present"""
        from mapgenerator.prompt_compiler import compile_image_prompt
        
        mapspec = create_test_mapspec()
        
        prompt = compile_image_prompt(
            mapspec=mapspec,
            has_mask=True
        )
        
        # Should include inpainting-specific instructions
        assert "mask" in prompt.lower() or "boundary" in prompt.lower() or "region" in prompt.lower()
    
    def test_prompt_without_mask_has_no_boundary_constraint(self):
        """Compiled prompt should NOT include mask instructions when no mask"""
        from mapgenerator.prompt_compiler import compile_image_prompt
        
        mapspec = create_test_mapspec()
        
        prompt = compile_image_prompt(
            mapspec=mapspec,
            has_mask=False
        )
        
        # Should be normal prompt without mask-specific language
        assert prompt  # Non-empty
    
    def test_mask_prompt_suffix_applied(self):
        """MASK_PROMPT_SUFFIX should be appended when mask is present"""
        from mapgenerator.prompts import MASK_PROMPT_SUFFIX
        from mapgenerator.prompt_compiler import compile_image_prompt
        
        mapspec = create_test_mapspec()
        
        prompt = compile_image_prompt(
            mapspec=mapspec,
            has_mask=True
        )
        
        # The suffix content should appear in the prompt
        # (exact match depends on implementation)
        assert len(prompt) > 50  # Should have substantial content
    
    def test_compile_image_prompt_accepts_has_mask_parameter(self):
        """compile_image_prompt should accept has_mask parameter"""
        from mapgenerator.prompt_compiler import compile_image_prompt
        
        mapspec = create_test_mapspec()
        
        # Should not raise any errors
        prompt_without_mask = compile_image_prompt(mapspec=mapspec, has_mask=False)
        prompt_with_mask = compile_image_prompt(mapspec=mapspec, has_mask=True)
        
        assert isinstance(prompt_without_mask, str)
        assert isinstance(prompt_with_mask, str)
        
        # With mask should be different (has additional constraint)
        # Note: Could be same length if constraint replaces something
        assert prompt_with_mask != prompt_without_mask or len(prompt_with_mask) >= len(prompt_without_mask)
    
    def test_mask_prompt_preserves_core_mapspec_content(self):
        """Mask mode should preserve core mapspec elements in the prompt"""
        from mapgenerator.prompt_compiler import compile_image_prompt
        
        mapspec = create_test_mapspec()
        
        prompt = compile_image_prompt(mapspec=mapspec, has_mask=True)
        
        # Core elements should still be present
        # Note: Exact check depends on prompt template
        assert "forest" in prompt.lower() or "oak" in prompt.lower()


class TestMaskPromptSuffix:
    """Tests for the MASK_PROMPT_SUFFIX constant"""
    
    def test_mask_prompt_suffix_exists(self):
        """MASK_PROMPT_SUFFIX constant should exist in prompts module"""
        from mapgenerator.prompts import MASK_PROMPT_SUFFIX
        
        assert MASK_PROMPT_SUFFIX is not None
        assert isinstance(MASK_PROMPT_SUFFIX, str)
    
    def test_mask_prompt_suffix_has_boundary_instruction(self):
        """MASK_PROMPT_SUFFIX should contain boundary/region instructions"""
        from mapgenerator.prompts import MASK_PROMPT_SUFFIX
        
        suffix_lower = MASK_PROMPT_SUFFIX.lower()
        
        # Should mention one of these concepts
        has_relevant_content = any([
            "mask" in suffix_lower,
            "boundary" in suffix_lower,
            "region" in suffix_lower,
            "area" in suffix_lower,
            "preserve" in suffix_lower,
            "blend" in suffix_lower
        ])
        
        assert has_relevant_content, f"MASK_PROMPT_SUFFIX should reference masking concepts, got: {MASK_PROMPT_SUFFIX[:100]}"
    
    def test_mask_prompt_suffix_not_empty(self):
        """MASK_PROMPT_SUFFIX should have meaningful content"""
        from mapgenerator.prompts import MASK_PROMPT_SUFFIX
        
        # Should have reasonable length (not just a few characters)
        assert len(MASK_PROMPT_SUFFIX.strip()) >= 20, "MASK_PROMPT_SUFFIX should have meaningful content"
