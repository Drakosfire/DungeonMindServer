from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional
from pydantic import BaseModel
import logging
from ruleslawyer.ruleslawyer_helper import EmbeddingLoader, generate_bot_response_stream
from models.ruleslawyer_models import (
    RulesQueryRequest,
    RulebookRefreshRequest,
    SaveRuleRequest,
    UpdateSavedRuleRequest,
)
from dependencies import get_current_user, get_ruleslawyer_db
from security_limits.demo_quota import require_demo_quota_ruleslawyer
from security_limits.input_limits import (
    enforce_max_chars,
    MAX_CHAT_HISTORY_MESSAGES,
    MAX_CHAT_MESSAGE_CHARS,
    MAX_PROMPT_CHARS,
)
from firestore.firebase_config import db as firestore_db
from ruleslawyer.ruleslawyer_registry import RulesLawyerRegistry
from ruleslawyer.ruleslawyer_saved_rules import RulesLawyerSavedRulesRepository
from openai import AsyncOpenAI
import os
from pathlib import Path
from generationengine.services.text_service import TextGenerationService
from generationengine.models.requests import TextGenerationRequest, TextModel

router = APIRouter()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the base directory for ruleslawyer files
# __file__ is routers/ruleslawyer_router.py, so go up one level to DungeonMindServer, then into ruleslawyer/
DEFAULT_RULESLAWYER_DIR = Path(__file__).parent.parent / "ruleslawyer"
RULESLAWYER_DATA_DIR = Path(
    os.getenv("RULESLAWYER_DATA_DIR", str(DEFAULT_RULESLAWYER_DIR))
).resolve()

# Global variables for single embedding set
current_embeddings = None
current_pages_and_chunks = None
openai_client = AsyncOpenAI()
SYSTEM_PROMPT = """You are a friendly and technical answering system, answering questions with accurate, grounded, descriptive, clear, and specific responses. ALWAYS provide a page number citation. Provide a story example. Avoid extraneous details and focus on direct answers. Format every response using Markdown so the UI can render it properly. Follow these Markdown rules:

    • Start with a succinct sentence that answers the question.
    • Use headings (## or ###) for sections such as "Explanation", "Example", or "References".
    • CRITICAL: Always start headings on a NEW LINE. Use a blank line before ## or ###.
    • Use bullet lists for steps, rulings, or options.
    • CRITICAL: Always start list items on a NEW LINE. Use a blank line before - or *.
    • Use inline code (`like this`) or fenced code blocks for dice expressions or formulas when helpful.
    • End with "Citations: p.XX" (or multiple pages) on its own line, followed by "What else can I help with?"

IMPORTANT MARKDOWN FORMATTING RULES:
    - Headers MUST be on their own line with a blank line before them: "\n\n## Explanation\n"
    - List items MUST be on their own line with a blank line before them: "\n\n- Item 1\n- Item 2\n"
    - NEVER concatenate markdown syntax directly after text: WRONG: "text.## Header" CORRECT: "text.\n\n## Header"
    - Always use proper line breaks (\n) between paragraphs, headers, and list items.

When responding:

    1. Identify the key point of the query.
    2. Provide a straightforward answer, omitting the thought process.
    3. Avoid additional advice or extended explanations.
    4. Answer in an informative manner, aiding the user's understanding without overwhelming them or quoting the source.
    5. DO NOT SUMMARIZE YOURSELF. DO NOT REPEAT YOURSELF. 
    6. End with page citations, a line break and "What else can I help with?" 

    Example:
    Query: Explain how the player should think about balance and lethality in this game. Explain how the game master should think about balance and lethality?
    Answer: In "Swords & Wizardry: WhiteBox," players and the game master should consider balance and lethality from different perspectives. For players, understanding that this game encourages creativity and flexibility is key. The rules are intentionally streamlined, allowing for a potentially high-risk environment where player decisions significantly impact outcomes. The players should think carefully about their actions and strategy, knowing that the game can be lethal, especially without reliance on intricate rules for safety. Page 33 discusses the possibility of characters dying when their hit points reach zero, although alternative, less harsh rules regarding unconsciousness and recovery are mentioned.

For the game master (referred to as the Referee), balancing the game involves providing fair yet challenging scenarios. The role of the Referee isn't to defeat players but to present interesting and dangerous challenges that enhance the story collaboratively. Page 39 outlines how the Referee and players work together to craft a narrative, with the emphasis on creating engaging and potentially perilous experiences without making it a zero-sum competition. Referees can choose how lethal the game will be, considering their group's preferred play style, including implementing house rules to soften deaths or adjust game balance accordingly.

Pages: 33, 39

Use the context provided to answer the user's query concisely. """

class EmbeddingRequest(BaseModel):
    embedding: str
    embeddings_file_path: str
    enhanced_json_path: str

def _to_chat_history_tuples(chat_history: list) -> list[tuple[str, str]]:
    tuples: list[tuple[str, str]] = []
    current_user_msg: str | None = None

    for turn in chat_history:
        role = getattr(turn, "role", None) or turn.get("role")
        content = getattr(turn, "content", None) or turn.get("content")
        if role == "user":
            current_user_msg = content
        elif role == "assistant" and current_user_msg is not None:
            tuples.append((current_user_msg, content))
            current_user_msg = None

    return tuples

class RulesLawyerService:
    def __init__(self):
        self.loader: Optional[EmbeddingLoader] = None
        self.active_rulebook_id: str | None = None
    
    def load_embeddings(self, embeddings_file_path: str, enhanced_json_path: str, rulebook_id: str | None = None) -> None:
        self.loader = EmbeddingLoader(
            embeddings_file_path=os.path.join(RULESLAWYER_DATA_DIR, embeddings_file_path.lstrip('./')),
            enhanced_json_path=os.path.join(RULESLAWYER_DATA_DIR, enhanced_json_path.lstrip('./'))
        )
        if rulebook_id:
            self.active_rulebook_id = rulebook_id
    
    def get_loader(self) -> EmbeddingLoader:
        if not self.loader:
            raise HTTPException(status_code=400, detail="No embeddings loaded")
        return self.loader

# Create a single instance of the service
rules_lawyer_service = RulesLawyerService()


def get_ruleslawyer_registry(db=Depends(get_ruleslawyer_db)) -> RulesLawyerRegistry:
    return RulesLawyerRegistry(db)


def get_saved_rules_repo() -> RulesLawyerSavedRulesRepository:
    return RulesLawyerSavedRulesRepository(firestore_db)

# Health Check
@router.get("/health")
async def health():
    return {"status": "ok"}

# Status endpoint to check if embeddings are loaded
@router.get("/status")
async def get_status():
    """Check if embeddings are currently loaded."""
    return {
        "embeddingsLoaded": rules_lawyer_service.loader is not None,
        "activeRulebookId": rules_lawyer_service.active_rulebook_id
    }


@router.get("/rulebooks")
async def list_rulebooks(
    registry: RulesLawyerRegistry = Depends(get_ruleslawyer_registry),
):
    try:
        return {"rulebooks": registry.list_rulebooks()}
    except Exception as e:
        logger.error("❌ [RulesLawyer] Failed to list rulebooks", exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to load rulebooks right now.") from e


@router.post("/rulebooks/refresh")
async def refresh_rulebooks(
    request: RulebookRefreshRequest,
    registry: RulesLawyerRegistry = Depends(get_ruleslawyer_registry),
):
    try:
        return registry.refresh_rulebooks(request.rulebookIds, request.reason)
    except Exception as e:
        logger.error("❌ [RulesLawyer] Failed to refresh rulebooks", exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to refresh rulebooks right now.") from e


@router.get("/saved-rules")
async def list_saved_rules(
    repo: RulesLawyerSavedRulesRepository = Depends(get_saved_rules_repo),
    current_user=Depends(get_current_user)
):
    user_id = current_user.get("sub") if isinstance(current_user, dict) else getattr(current_user, "sub", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return {"rules": repo.list_by_user(user_id)}
    except Exception as e:
        logger.error("❌ [RulesLawyer] Failed to list saved rules", exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to load saved rules right now.") from e


@router.post("/saved-rules")
async def save_rule(
    request: SaveRuleRequest,
    repo: RulesLawyerSavedRulesRepository = Depends(get_saved_rules_repo),
    current_user=Depends(get_current_user)
):
    user_id = current_user.get("sub") if isinstance(current_user, dict) else getattr(current_user, "sub", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return repo.save_rule(user_id, request.model_dump())
    except Exception as e:
        logger.error("❌ [RulesLawyer] Failed to save rule", exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to save rule right now.") from e


@router.put("/saved-rules/{rule_id}")
async def update_rule(
    rule_id: str,
    request: UpdateSavedRuleRequest,
    repo: RulesLawyerSavedRulesRepository = Depends(get_saved_rules_repo),
    current_user=Depends(get_current_user),
):
    user_id = current_user.get("sub") if isinstance(current_user, dict) else getattr(current_user, "sub", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = request.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No update fields provided")

    try:
        updated = repo.update_rule(user_id, rule_id, payload)
        if not updated:
            raise HTTPException(status_code=404, detail="Saved rule not found")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        logger.error("❌ [RulesLawyer] Failed to update saved rule", exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to update saved rule right now.") from e


@router.delete("/saved-rules/{rule_id}")
async def delete_rule(
    rule_id: str,
    repo: RulesLawyerSavedRulesRepository = Depends(get_saved_rules_repo),
    current_user=Depends(get_current_user),
):
    user_id = current_user.get("sub") if isinstance(current_user, dict) else getattr(current_user, "sub", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        deleted = repo.delete_rule(user_id, rule_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Saved rule not found")
        return {"success": True, "id": rule_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("❌ [RulesLawyer] Failed to delete saved rule", exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to delete saved rule right now.") from e

@router.post("/loadembeddings")
async def load_embedding(request: EmbeddingRequest):
    logger.info(f"Loading embedding: {request}")
    logger.info(f"RULESLAWYER_DATA_DIR: {RULESLAWYER_DATA_DIR}")
    logger.info(f"Expected embeddings file: {RULESLAWYER_DATA_DIR / request.embeddings_file_path.lstrip('./')}")
    logger.info(f"Expected JSON file: {RULESLAWYER_DATA_DIR / request.enhanced_json_path.lstrip('./')}")
    
    try:
        rules_lawyer_service.load_embeddings(
            embeddings_file_path=request.embeddings_file_path,
            enhanced_json_path=request.enhanced_json_path,
            rulebook_id=request.embedding
        )
        logger.info(f"✅ [RulesLawyer] Embeddings loaded successfully")
        return {"message": "Embedding loaded successfully"}
    except FileNotFoundError as e:
        logger.error(f"File not found: {str(e)}")
        logger.error(f"Looking in directory: {RULESLAWYER_DATA_DIR}")
        logger.error(
            f"Files in directory: {list(RULESLAWYER_DATA_DIR.iterdir()) if RULESLAWYER_DATA_DIR.exists() else 'Directory does not exist'}"
        )
        raise HTTPException(status_code=404, detail="Embedding file not found. Please verify rulebook data is available.") from e
    except Exception as e:
        logger.error(f"Error loading embeddings: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load embeddings. Please try again later.") from e

@router.post("/query")
async def query_rules(
    request: RulesQueryRequest,
    _demo_quota=Depends(require_demo_quota_ruleslawyer),
):
    import time as time_module
    request_start_time = time_module.time()

    enforce_max_chars(request.message, field="message", limit=MAX_PROMPT_CHARS)
    if len(request.chatHistory or []) > MAX_CHAT_HISTORY_MESSAGES:
        raise HTTPException(
            status_code=422,
            detail=f"chatHistory cannot exceed {MAX_CHAT_HISTORY_MESSAGES} messages",
        )
    for i, msg in enumerate(request.chatHistory or []):
        content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else "")
        if content:
            enforce_max_chars(str(content), field=f"chatHistory[{i}]", limit=MAX_CHAT_MESSAGE_CHARS)
    
    logger.info(f"🔵 [RulesLawyer] Query request received at {time_module.time()}: message_length={len(request.message)}, chat_history_length={len(request.chatHistory)}")
    
    try:
        loader_start_time = time_module.time()
        loader = rules_lawyer_service.get_loader()
        loader_duration = (time_module.time() - loader_start_time) * 1000
        logger.info(f"⏱️ [RulesLawyer] Loader retrieved in {loader_duration:.2f}ms")
        
        # Use streaming response - await async function to get generator
        chat_history = _to_chat_history_tuples(request.chatHistory)
        stream_generator, history = await generate_bot_response_stream(
            message=request.message,
            chat_history=chat_history,
            embeddings_loader=loader,
            client=openai_client,
            system_prompt=SYSTEM_PROMPT,
            request_start_time=request_start_time,
            rulebook_id=request.rulebookId
        )
        
        return StreamingResponse(
            stream_generator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    except HTTPException as e:
        logger.warning(f"⚠️ [RulesLawyer] Query rejected: {e.detail}")
        raise
    except Exception as e:
        total_duration = (time_module.time() - request_start_time) * 1000
        logger.error(f"❌ [RulesLawyer] Error processing query after {total_duration:.2f}ms: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process query")