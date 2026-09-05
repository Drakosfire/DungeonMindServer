"""Architecture fitness for the GenerationEngine cutover.

Migrated inference modules must use the public GenerationEngine contract only.
"""

from __future__ import annotations

from pathlib import Path

FORBIDDEN_GE_IMPORTS = (
    "generationengine.services",
    "generationengine.models",
    "generationengine.providers",
    "generationengine.telemetry",
)
FORBIDDEN_SYMBOLS = (
    "TextGenerationService",
    "ImageService",
    "UploadService",
    "MetricsService",
    "TextModel",
    "ImageModel",
    "ImageSize",
)
MIGRATED_FILES = (
    "mapgenerator/prompt_compiler.py",
    "mapgenerator/svg_mask.py",
    "mapgenerator/inpainting.py",
    "playercharactergenerator/pcg_generator.py",
    "cardgenerator/services/card_generation_service.py",
    "routers/map_router.py",
    "routers/image_management_router.py",
    "routers/ruleslawyer_router.py",
    "shared/image_models.py",
    "statblocks_v1/infrastructure/ge_provider.py",
    "statblocks_v1/infrastructure/runtime.py",
    "statblocks_v1/application/settings.py",
)


def test_migrated_modules_do_not_import_legacy_generationengine() -> None:
    root = Path(__file__).resolve().parents[1]
    violations: list[str] = []
    for relative in MIGRATED_FILES:
        text = (root / relative).read_text(encoding="utf-8")
        for needle in FORBIDDEN_GE_IMPORTS + FORBIDDEN_SYMBOLS:
            if needle in text:
                violations.append(f"{relative}: {needle}")
    assert violations == []


def test_model_policy_json_is_gone() -> None:
    root = Path(__file__).resolve().parents[1]
    assert not (root / "MODEL_POLICY.json").exists()


def test_ruleslawyer_does_not_import_generationengine() -> None:
    text = (Path(__file__).resolve().parents[1] / "routers/ruleslawyer_router.py").read_text(
        encoding="utf-8"
    )
    assert "generationengine" not in text
