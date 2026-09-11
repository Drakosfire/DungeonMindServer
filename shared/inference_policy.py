"""DungeonMindServer product action → GenerationEngine profile mapping.

This is product policy, not a second model catalog. Provider/model resolution
belongs to GenerationEngine. Explicit catalog ids are used only where the
measured before-state would otherwise silently change under a generic profile default.
"""

from __future__ import annotations

from dataclasses import dataclass

from generationengine import InferenceProfile


@dataclass(frozen=True)
class ActionInference:
    profile: InferenceProfile
    model: str | None = None


ACTION_INFERENCE: dict[str, ActionInference] = {
    "map_spec_generation": ActionInference(InferenceProfile.STRUCTURED_LOW_COST),
    "svg_mask_generation": ActionInference(InferenceProfile.TEXT_FAST),
    "pcg_preference_generation": ActionInference(InferenceProfile.TEXT_FAST),
    "card_item_generation": ActionInference(InferenceProfile.STRUCTURED_LOW_COST, "gpt-4o"),
    "statblock_definition_generation": ActionInference(
        InferenceProfile.STRUCTURED_HIGH_RELIABILITY
    ),
    "map_image_generation": ActionInference(InferenceProfile.IMAGE_HIGH_QUALITY, "gpt-image-1.5"),
    "map_image_edit": ActionInference(InferenceProfile.IMAGE_EDIT_HIGH_QUALITY, "gpt-image-1.5"),
    "card_core_image_generation": ActionInference(
        InferenceProfile.IMAGE_HIGH_QUALITY, "nano-banana-pro"
    ),
    "card_i2i_generation": ActionInference(InferenceProfile.IMAGE_HIGH_QUALITY, "flux-lora-i2i"),
    "user_selected_image_generation": ActionInference(InferenceProfile.IMAGE_HIGH_QUALITY),
}


def inference_for(action: str) -> ActionInference:
    try:
        return ACTION_INFERENCE[action]
    except KeyError as exc:
        raise KeyError(f"Unknown inference action {action!r}") from exc


def profile_for(action: str) -> InferenceProfile:
    return inference_for(action).profile
