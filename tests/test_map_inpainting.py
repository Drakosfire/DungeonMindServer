"""Map inpainting uses GenerationEngine edit_image and product Cloudflare publish."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from generationengine import GeneratedImage, ImageRequest, ImageResult
from generationengine.observation import InferenceObservation, ObservationState


def _png_result() -> ImageResult:
    return ImageResult(
        images=[GeneratedImage(content=b"png-bytes", media_type="image/png", width=1024, height=1024)],
        observation=InferenceObservation(
            provider="fal",
            requested_profile="image_edit_high_quality",
            resolved_model="gpt-image-1.5",
            latency_ms=12,
            retry_count=0,
            state=ObservationState.COMPLETED,
        ),
    )


def _patch_bounds():
    return patch.multiple(
        "mapgenerator.inpainting",
        _get_image_dimensions=MagicMock(return_value=(1024, 1024)),
    )


@pytest.mark.asyncio
async def test_inpainting_calls_edit_image_and_publishes():
    from mapgenerator.inpainting import generate_inpainted_map

    client = MagicMock()
    client.edit_image = AsyncMock(return_value=_png_result())
    uploaded = MagicMock(url="https://imagedelivery.net/acct/img/Full")
    with _patch_bounds(), patch(
        "mapgenerator.inpainting.get_generation_client", return_value=client
    ), patch(
        "mapgenerator.inpainting.publish_generated_image",
        AsyncMock(return_value=uploaded),
    ):
        result = await generate_inpainted_map(
            prompt="A forest clearing",
            mask_base64="data:image/png;base64,mask",
            base_image_base64="data:image/png;base64,image",
        )

    client.edit_image.assert_called_once()
    request = client.edit_image.call_args.args[0]
    assert isinstance(request, ImageRequest)
    assert request.model == "gpt-image-1.5"
    assert request.mask_base64 == "data:image/png;base64,mask"
    assert request.base_image_base64 == "data:image/png;base64,image"
    assert result == uploaded.url


@pytest.mark.asyncio
async def test_inpainting_propagates_generation_failure():
    from mapgenerator.inpainting import generate_inpainted_map

    client = MagicMock()
    client.edit_image = AsyncMock(side_effect=Exception("Generation failed"))
    with _patch_bounds(), patch(
        "mapgenerator.inpainting.get_generation_client", return_value=client
    ):
        with pytest.raises(Exception, match="Generation failed"):
            await generate_inpainted_map(
                prompt="A forest path",
                mask_base64="data:image/png;base64,mask",
                base_image_base64="data:image/png;base64,image",
            )


@pytest.mark.asyncio
async def test_inpainting_requires_mask_and_base():
    from mapgenerator.inpainting import InpaintingValidationError, generate_inpainted_map

    with pytest.raises(InpaintingValidationError):
        await generate_inpainted_map(prompt="x", mask_base64="", base_image_base64="data:image/png;base64,x")
    with pytest.raises(InpaintingValidationError):
        await generate_inpainted_map(prompt="x", mask_base64="data:image/png;base64,x", base_image_base64="")

