from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional
from pydantic import BaseModel
import logging
from ruleslawyer.ruleslawyer_helper import EmbeddingLoader, generate_bot_response, generate_bot_response_stream
from openai import AsyncOpenAI
import os
from pathlib import Path

router = APIRouter()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the base directory for ruleslawyer files
# __file__ is routers/ruleslawyer_router.py, so go up one level to DungeonMindServer, then into ruleslawyer/
RULESLAWYER_DIR = Path(__file__).parent.parent / "ruleslawyer"

# Global variables for single embedding set
current_embeddings = None
current_pages_and_chunks = None
openai_client = AsyncOpenAI()
SYSTEM_PROMPT = """You are a friendly and technical answering system, answering questions with accurate, grounded, descriptive, clear, and specific responses. ALWAYS provide a page number citation. Provide a story example. Avoid extraneous details and focus on direct answers. Format every response using Markdown so the UI can render it properly. Follow these Markdown rules:

    • Start with a succinct sentence that answers the question.
    • Use headings (## or ###) for sections such as “Explanation”, “Example”, or “References”.
    • Use bullet lists for steps, rulings, or options.
    • Use inline code (`like this`) or fenced code blocks for dice expressions or formulas when helpful.
    • End with “Citations: p.XX” (or multiple pages) on its own line, followed by “What else can I help with?”

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
    logger.info(f"Loading embedding: {request}")
    logger.info(f"RULESLAWYER_DIR: {RULESLAWYER_DIR}")
    logger.info(f"Expected embeddings file: {RULESLAWYER_DIR / request.embeddings_file_path.lstrip('./')}")
    logger.info(f"Expected JSON file: {RULESLAWYER_DIR / request.enhanced_json_path.lstrip('./')}")
    
    try:
        rules_lawyer_service.load_embeddings(
            embeddings_file_path=request.embeddings_file_path,
            enhanced_json_path=request.enhanced_json_path
        )
        return {"message": "Embedding loaded successfully"}
    except FileNotFoundError as e:
        logger.error(f"File not found: {str(e)}")
        logger.error(f"Looking in directory: {RULESLAWYER_DIR}")
        logger.error(f"Files in directory: {list(RULESLAWYER_DIR.iterdir()) if RULESLAWYER_DIR.exists() else 'Directory does not exist'}")
        raise HTTPException(status_code=404, detail=f"Embedding file not found: {str(e)}. Checked in: {RULESLAWYER_DIR}")
    except Exception as e:
        logger.error(f"Error loading embeddings: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load embeddings: {str(e)}")

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
        
        # Use streaming response - await async function to get generator
        stream_generator, history = await generate_bot_response_stream(
            message=request.message,
            chat_history=request.chat_history,
            embeddings_loader=loader,
            client=openai_client,
            system_prompt=SYSTEM_PROMPT,
            request_start_time=request_start_time
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
    except Exception as e:
        total_duration = (time_module.time() - request_start_time) * 1000
        logger.error(f"❌ [RulesLawyer] Error processing query after {total_duration:.2f}ms: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process query")