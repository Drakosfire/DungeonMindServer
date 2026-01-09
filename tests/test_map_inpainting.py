"""
Map Inpainting Service Tests (T181)

Tests for the inpainting integration with GenerationEngine.
Updated to match actual implementation using ImageService.generate().
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from generationengine.models.image_responses import ImageGenerationResponse, ImageResult


class TestMapInpaintingService:
    """Tests for inpainting call to GenerationEngine (T181)"""
    
    @pytest.mark.asyncio
    async def test_inpainting_calls_generation_engine(self):
        """Inpainting should call GenerationEngine with correct parameters"""
        from mapgenerator.inpainting import generate_inpainted_map
        
        # Create a proper mock response
        mock_response = ImageGenerationResponse(
            success=True,
            images=[ImageResult(url="https://example.com/generated.png", width=1024, height=1024, model_used="flux-2-pro")],
        )
        
        # Mock the GenerationEngine
        with patch('mapgenerator.inpainting.ImageService') as MockImageService:
            mock_instance = MagicMock()
            mock_instance.generate = AsyncMock(return_value=mock_response)
            MockImageService.return_value = mock_instance
            
            result = await generate_inpainted_map(
                prompt="A forest clearing",
                mask_base64="data:image/png;base64,iVBORw0KGgo...",
                base_image_base64="data:image/png;base64,iVBORw0KGgo..."
            )
            
            # Should have called the service
            mock_instance.generate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_inpainting_passes_mask_to_service(self):
        """Inpainting should pass mask data to the generation service"""
        from mapgenerator.inpainting import generate_inpainted_map
        
        test_mask = "data:image/png;base64,testmaskdata"
        test_image = "data:image/png;base64,testimagedata"
        
        mock_response = ImageGenerationResponse(
            success=True,
            images=[ImageResult(url="https://example.com/generated.png", width=1024, height=1024, model_used="flux-2-pro")],
        )
        
        with patch('mapgenerator.inpainting.ImageService') as MockImageService:
            mock_instance = MagicMock()
            mock_instance.generate = AsyncMock(return_value=mock_response)
            MockImageService.return_value = mock_instance
            
            await generate_inpainted_map(
                prompt="A dungeon room",
                mask_base64=test_mask,
                base_image_base64=test_image
            )
            
            # Verify mask was passed in the call
            call_args = mock_instance.generate.call_args
            assert call_args is not None
            
            # The request object should have mask_base64
            request = call_args[0][0]  # First positional arg
            assert request.mask_base64 == test_mask
    
    @pytest.mark.asyncio
    async def test_inpainting_passes_base_image_to_service(self):
        """Inpainting should pass base image data to the generation service"""
        from mapgenerator.inpainting import generate_inpainted_map
        
        test_mask = "data:image/png;base64,testmaskdata"
        test_image = "data:image/png;base64,testimagedata"
        
        mock_response = ImageGenerationResponse(
            success=True,
            images=[ImageResult(url="https://example.com/generated.png", width=1024, height=1024, model_used="flux-2-pro")],
        )
        
        with patch('mapgenerator.inpainting.ImageService') as MockImageService:
            mock_instance = MagicMock()
            mock_instance.generate = AsyncMock(return_value=mock_response)
            MockImageService.return_value = mock_instance
            
            await generate_inpainted_map(
                prompt="A castle tower",
                mask_base64=test_mask,
                base_image_base64=test_image
            )
            
            # Verify base image was passed in the call
            call_args = mock_instance.generate.call_args
            assert call_args is not None
            
            # The request object should have base_image_base64
            request = call_args[0][0]  # First positional arg
            assert request.base_image_base64 == test_image
    
    @pytest.mark.asyncio
    async def test_inpainting_returns_image_url(self):
        """Inpainting should return the generated image URL"""
        from mapgenerator.inpainting import generate_inpainted_map
        
        expected_url = "https://cdn.example.com/inpainted-map.png"
        
        mock_response = ImageGenerationResponse(
            success=True,
            images=[ImageResult(url=expected_url, width=1024, height=1024, model_used="flux-2-pro")],
        )
        
        with patch('mapgenerator.inpainting.ImageService') as MockImageService:
            mock_instance = MagicMock()
            mock_instance.generate = AsyncMock(return_value=mock_response)
            MockImageService.return_value = mock_instance
            
            result = await generate_inpainted_map(
                prompt="A tavern interior",
                mask_base64="data:image/png;base64,mask",
                base_image_base64="data:image/png;base64,image"
            )
            
            assert result is not None
            assert result == expected_url
    
    @pytest.mark.asyncio
    async def test_inpainting_handles_generation_error(self):
        """Inpainting should handle errors from GenerationEngine gracefully"""
        from mapgenerator.inpainting import generate_inpainted_map
        
        with patch('mapgenerator.inpainting.ImageService') as MockImageService:
            mock_instance = MagicMock()
            mock_instance.generate = AsyncMock(side_effect=Exception("Generation failed"))
            MockImageService.return_value = mock_instance
            
            with pytest.raises(Exception) as exc_info:
                await generate_inpainted_map(
                    prompt="A forest path",
                    mask_base64="data:image/png;base64,mask",
                    base_image_base64="data:image/png;base64,image"
                )
            
            # Should propagate the error or wrap it
            assert "Generation failed" in str(exc_info.value) or "inpainting" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_inpainting_validates_mask_format(self):
        """Inpainting should validate mask is proper base64 PNG"""
        from mapgenerator.inpainting import generate_inpainted_map, InpaintingValidationError
        
        invalid_mask = "not-a-valid-base64-image"
        
        with pytest.raises((InpaintingValidationError, ValueError, Exception)) as exc_info:
            await generate_inpainted_map(
                prompt="A mountain pass",
                mask_base64=invalid_mask,
                base_image_base64="data:image/png;base64,validimage"
            )
        
        # Should indicate the mask was invalid
        error_msg = str(exc_info.value).lower()
        assert "mask" in error_msg or "base64" in error_msg or "invalid" in error_msg


class TestInpaintingModuleExists:
    """Tests to verify the inpainting module exists"""
    
    def test_inpainting_module_importable(self):
        """mapgenerator.inpainting module should be importable"""
        try:
            from mapgenerator import inpainting
            assert inpainting is not None
        except ImportError as e:
            pytest.fail(f"Could not import mapgenerator.inpainting: {e}")
    
    def test_generate_inpainted_map_function_exists(self):
        """generate_inpainted_map function should exist"""
        from mapgenerator.inpainting import generate_inpainted_map
        
        assert callable(generate_inpainted_map)
