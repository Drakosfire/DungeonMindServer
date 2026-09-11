from shared.inference_policy import inference_for
from generationengine import InferenceProfile


def test_card_item_generation_keeps_gpt_4o() -> None:
    action = inference_for("card_item_generation")
    assert action.profile is InferenceProfile.STRUCTURED_LOW_COST
    assert action.model == "gpt-4o"


def test_map_image_generation_keeps_gpt_image() -> None:
    action = inference_for("map_image_generation")
    assert action.model == "gpt-image-1.5"


def test_statblock_uses_high_reliability_profile() -> None:
    action = inference_for("statblock_definition_generation")
    assert action.profile is InferenceProfile.STRUCTURED_HIGH_RELIABILITY
    assert action.model is None
