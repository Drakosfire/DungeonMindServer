from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional
from pydantic import BaseModel
import logging
from ruleslawyer.ruleslawyer_helper import EmbeddingLoader
import os
from pathlib import Path
from generationengine.services.text_service import TextGenerationService
from generationengine.models.requests import TextGenerationRequest, TextModel

router = APIRouter()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the base directory for ruleslawyer files
# __file__ is routers/ruleslawyer_router.py, so we need to go up one level and into ruleslawyer/
RULESLAWYER_DIR = Path(__file__).parent.parent / "ruleslawyer"

# Global variables for single embedding set
current_embeddings = None
current_pages_and_chunks = None

# Initialize TextGenerationService for OpenAI Responses API
text_generation_service = TextGenerationService()
SYSTEM_PROMPT = """You are a friendly and technical answering system, answering questions with accurate, grounded, descriptive, clear, and specific responses. ALWAYS provide a page number citation. Provide a story example. Avoid extraneous details and focus on direct answers. Format every response using Markdown so the UI can render it properly. Follow these Markdown rules:

    • Start with a succinct sentence that answers the question.
    • Use headings (## or ###) for sections such as "Explanation", "Example", or "References".
    • Use bullet lists for steps, rulings, or options.
    • Use inline code (`like this`) or fenced code blocks for dice expressions or formulas when helpful.
    • End with "Citations: p.XX" (or multiple pages) on its own line, followed by "What else can I help with?"

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

class QueryRequest(BaseModel):
    message: str
    chat_history: list = []

class RulesLawyerService:
    def __init__(self):
        self.loader: Optional[EmbeddingLoader] = None
    
    def load_embeddings(self, embeddings_file_path: str, enhanced_json_path: str) -> None:
        self.loader = EmbeddingLoader(
            embeddings_file_path=os.path.join(RULESLAWYER_DIR, embeddings_file_path.lstrip('./')),
            enhanced_json_path=os.path.join(RULESLAWYER_DIR, enhanced_json_path.lstrip('./'))
        )
    
    def get_loader(self) -> EmbeddingLoader:
        if not self.loader:
            raise HTTPException(status_code=400, detail="No embeddings loaded")
        return self.loader

# Create a single instance of the service
rules_lawyer_service = RulesLawyerService()

# Health Check
@router.get("/health")
async def health():
    return {"status": "ok"}

# Status endpoint to check if embeddings are loaded
@router.get("/status")
async def get_status():
    """Check if embeddings are currently loaded."""
    return {
        "embeddings_loaded": rules_lawyer_service.loader is not None,
        "current_embedding": None  # Could track this if needed
    }

@router.post("/loadembeddings")
async def load_embedding(request: EmbeddingRequest):
    logger.info(f"🔄 [RulesLawyer] Loading embedding: {request.embedding}")
    logger.info(f"📁 [RulesLawyer] Request paths - CSV: {request.embeddings_file_path}, JSON: {request.enhanced_json_path}")
    
    try:
        # Construct full paths for logging
        embeddings_full_path = os.path.join(RULESLAWYER_DIR, request.embeddings_file_path.lstrip('./'))
        json_full_path = os.path.join(RULESLAWYER_DIR, request.enhanced_json_path.lstrip('./'))
        
        logger.info(f"🔍 [RulesLawyer] Resolved paths:")
        logger.info(f"   Embeddings: {embeddings_full_path}")
        logger.info(f"   JSON: {json_full_path}")
        logger.info(f"   RULESLAWYER_DIR: {RULESLAWYER_DIR}")
        logger.info(f"   Directory exists: {os.path.exists(RULESLAWYER_DIR)}")
        
        # Check if files exist before attempting to load
        if not os.path.exists(embeddings_full_path):
            error_msg = f"Embeddings file not found: {embeddings_full_path}"
            logger.error(f"❌ [RulesLawyer] {error_msg}")
            raise HTTPException(status_code=404, detail=error_msg)
        
        if not os.path.exists(json_full_path):
            error_msg = f"JSON file not found: {json_full_path}"
            logger.error(f"❌ [RulesLawyer] {error_msg}")
            raise HTTPException(status_code=404, detail=error_msg)
        
        logger.info(f"✅ [RulesLawyer] Files found, loading embeddings...")
        rules_lawyer_service.load_embeddings(
            embeddings_file_path=request.embeddings_file_path,
            enhanced_json_path=request.enhanced_json_path
        )
        logger.info(f"✅ [RulesLawyer] Embeddings loaded successfully")
        return {"message": "Embedding loaded successfully"}
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        error_detail = f"Failed to load embeddings: {str(e)}"
        logger.error(f"❌ [RulesLawyer] Error loading embeddings: {error_detail}")
        logger.exception(e)  # Log full traceback
        raise HTTPException(status_code=500, detail=error_detail)

@router.post("/query")
async def query_rules(request: QueryRequest):
    import time as time_module
    request_start_time = time_module.time()
    
    logger.info(f"🔵 [RulesLawyer] Query request received at {time_module.time()}: message_length={len(request.message)}, chat_history_length={len(request.chat_history)}")
    
    try:
        loader_start_time = time_module.time()
        loader = rules_lawyer_service.get_loader()
        loader_duration = (time_module.time() - loader_start_time) * 1000
        logger.info(f"⏱️ [RulesLawyer] Loader retrieved in {loader_duration:.2f}ms")
        
        async def generate_stream():
            """Generator function that streams the LLM response using GenerationEngine"""
            try:
                # Get relevant context
                search_start_time = time_module.time()
                scores, indices = loader.print_top_results_and_scores(query=request.message)
                search_duration = (time_module.time() - search_start_time) * 1000
                logger.info(f"🔍 [RulesLawyer] Semantic search completed in {search_duration:.2f}ms")
                
                context_items = [loader.pages_and_chunks[i] for i in indices]
                user_prompt = loader.format_prompt(query=request.message, context_items=context_items)
                
                # Create TextGenerationRequest for GenerationEngine
                # Note: max_tokens is not supported in Responses API streaming mode
                generation_request = TextGenerationRequest(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    model=TextModel.GPT_5_1,
                    temperature=1.0,
                    # max_tokens not supported in Responses API streaming - omitted
                )
                
                # Stream from GenerationEngine (Responses API)
                api_start_time = time_module.time()
                first_token_received = False
                first_token_time = None
                
                # Forward tokens as they arrive from GenerationEngine
                async for chunk in text_generation_service.generate_stream(generation_request):
                    # Track time to first token (TTFT)
                    if not first_token_received and chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
                        first_token_received = True
                        first_token_time = time_module.time()
                        ttft = (first_token_time - request_start_time) * 1000
                        logger.info(f"🚀 [RulesLawyer] First token received: {ttft:.2f}ms (TTFT)")
                    
                    # GenerationEngine already formats as SSE, so yield directly
                    yield chunk
                
                # Log completion
                total_duration = (time_module.time() - request_start_time) * 1000
                logger.info(f"✅ [RulesLawyer] Streaming completed in {total_duration:.2f}ms")
                
            except Exception as e:
                total_duration = (time_module.time() - request_start_time) * 1000
                logger.error(f"❌ [RulesLawyer] Error in stream generation after {total_duration:.2f}ms: {str(e)}", exc_info=True)
                yield f"data: [ERROR]{str(e)}\n\n"
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    except Exception as e:
        total_duration = (time_module.time() - request_start_time) * 1000
        logger.error(f"❌ [RulesLawyer] Error processing query after {total_duration:.2f}ms: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process query")