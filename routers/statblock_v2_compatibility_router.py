"""Historical command-board v2 compatibility routes for DungeonBuddy.

These routes preserve the pre-v1 producer contract.  DungeonBuddy's active
authoritative statblock API is implemented by ``statblocks_v1``; retain this
router only for established v2 consumers while they migrate deliberately.
"""

from datetime import datetime
import logging
import os

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from .internal_auth import require_dungeonbuddy_internal_key
from statblockgenerator.models.command_board_contract_models import (
    ContractError,
    DraftIntent,
    StatBlockDraftRenderRequest,
    StatBlockDraftRequest,
    StatBlockDraftResponse,
)
from statblockgenerator.services.statblock_draft_adapter import (
    build_draft,
    build_generation_request,
)
from statblockgenerator.statblock_generator import StatBlockGenerator


logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/statblockgenerator",
    tags=["statblockgenerator-v2-compatibility"],
)
statblock_generator = StatBlockGenerator()


@router.get("/v2/health", dependencies=[Depends(require_dungeonbuddy_internal_key)])
async def v2_health_check():
    """Return the historical command-board v2 health payload."""
    return {
        "status": "ok",
        "service": "statblockgenerator",
        "contract": "command_board_draft_v2",
        "version": "0.1.0",
        "generator_ready": statblock_generator is not None,
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "supports": ["generate-draft", "render-draft"],
        "timestamp": datetime.now().isoformat(),
    }


@router.post(
    "/v2/generate-draft",
    response_model=StatBlockDraftResponse,
    dependencies=[Depends(require_dungeonbuddy_internal_key)],
)
async def generate_statblock_draft(request: StatBlockDraftRequest):
    """Generate a command-board-ready v2 draft without persisting it."""
    if request.mode in {"generate_from_source_statblock", "revise_existing", "render_existing"}:
        response = StatBlockDraftResponse(
            success=False,
            error=ContractError(
                code="not_implemented",
                message=f"Mode '{request.mode}' is accepted by the contract but not implemented in this v2 slice.",
                details={"mode": request.mode},
            ),
        )
        return JSONResponse(status_code=501, content=response.model_dump(mode="json"))

    try:
        generation_request = build_generation_request(request)
        success, result = await statblock_generator.generate_creature(generation_request)

        if not success:
            response = StatBlockDraftResponse(
                success=False,
                error=ContractError(
                    code="generation_failed",
                    message=result.get("error", "Generation failed"),
                    details={key: value for key, value in result.items() if key != "error"},
                ),
            )
            return JSONResponse(status_code=400, content=response.model_dump(mode="json"))

        draft = build_draft(
            request=request,
            statblock_data=result.get("statblock", result),
            generation_info=result.get("generation_info", {}),
        )
        return StatBlockDraftResponse(success=True, draft=draft)

    except Exception as exc:
        logger.error("v2 draft generation failed: %s", exc)
        response = StatBlockDraftResponse(
            success=False,
            error=ContractError(
                code="draft_adapter_failed",
                message="Draft generation failed while adapting generator output.",
                details={"error": str(exc)},
            ),
        )
        return JSONResponse(status_code=500, content=response.model_dump(mode="json"))


@router.post(
    "/v2/render-draft",
    response_model=StatBlockDraftResponse,
    dependencies=[Depends(require_dungeonbuddy_internal_key)],
)
async def render_statblock_draft(request: StatBlockDraftRenderRequest):
    """Render an existing statblock into the historical v2 draft envelope."""
    try:
        adapter_request = StatBlockDraftRequest(
            request_id=request.request_id,
            mode="render_existing",
            intent=DraftIntent(summary=f"Render existing statblock: {request.statblock.name}"),
            source_statblock=request.statblock,
            source_refs=request.source_refs,
            output_options=request.output_options,
        )
        draft = build_draft(
            request=adapter_request,
            statblock_data=request.statblock,
            generation_info={"source": "render-draft", "generated": False},
            generator="statblock_draft_adapter.render_existing",
        )
        return StatBlockDraftResponse(success=True, draft=draft)

    except Exception as exc:
        logger.error("v2 draft rendering failed: %s", exc)
        response = StatBlockDraftResponse(
            success=False,
            error=ContractError(
                code="draft_render_failed",
                message="Draft rendering failed while adapting the provided statblock.",
                details={"error": str(exc)},
            ),
        )
        return JSONResponse(status_code=500, content=response.model_dump(mode="json"))
