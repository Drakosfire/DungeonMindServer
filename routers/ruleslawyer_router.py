from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional
from pydantic import BaseModel
import logging
from ruleslawyer.ruleslawyer_helper import EmbeddingLoader
from openai import OpenAI
import os
from pathlib import Path

router = APIRouter()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the base directory for ruleslawyer files
# __file__ is routers/ruleslawyer_router.py, so we need to go up one level and into ruleslawyer/
RULESLAWYER_DIR = Path(__file__).parent.parent / "ruleslawyer"

# Global variables for single embedding set
current_embeddings = None
current_pages_and_chunks = None
openai_client = OpenAI()
SYSTEM_PROMPT = """You are a friendly and technical answering system, answering questions with accurate, grounded, descriptive, clear, and specific responses. ALWAYS provide a page number citation. Provide a story example. Avoid extraneous details and focus on direct answers. Use the examples provided as a guide for style and brevity. When responding:

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
    try:
        loader = rules_lawyer_service.get_loader()
        
        async def generate_stream():
            """Generator function that streams the LLM response"""
            try:
                # Get relevant context
                scores, indices = loader.print_top_results_and_scores(query=request.message)
                context_items = [loader.pages_and_chunks[i] for i in indices]
                prompt = loader.format_prompt(query=request.message, context_items=context_items)
                
                # Prepare messages for OpenAI
                messages = [{"role": "user", "content": f"{SYSTEM_PROMPT} {prompt}"}]
                
                # Stream from OpenAI
                stream = openai_client.chat.completions.create(
                    model="gpt-4",
                    messages=messages,
                    temperature=1,
                    max_tokens=512,
                    top_p=1,
                    frequency_penalty=0,
                    presence_penalty=0,
                    stream=True  # Enable streaming
                )
                
                # Forward tokens as they arrive
                for chunk in stream:
                    if chunk.choices[0].delta.content is not None:
                        content = chunk.choices[0].delta.content
                        # Format as SSE: data: <content>\n\n
                        # Frontend expects raw text, not JSON-encoded
                        yield f"data: {content}\n\n"
                
                # Send completion signal
                yield "data: [DONE]\n\n"
                
            except Exception as e:
                logger.error(f"Error in stream generation: {str(e)}")
                yield f"data: [ERROR]{str(e)}\n\n"
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process query")