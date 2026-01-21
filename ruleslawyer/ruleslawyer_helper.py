import json
import os
import textwrap
import threading
import time
from datetime import datetime

import numpy as np
import pandas as pd
from openai import OpenAI
from sentence_transformers import SentenceTransformer
from ruleslawyer.hybrid_retriever import HybridRetriever

class EmbeddingLoader:
    def __init__(self, embeddings_file_path=None, enhanced_json_path=None, cached_data=None):
        """
        Initialize the EmbeddingLoader with paths or cached data.

        Args:
            embeddings_file_path (str, optional): Path to the embeddings CSV file.
            enhanced_json_path (str, optional): Path to the enhanced JSON file.
            cached_data (dict, optional): Preloaded embeddings and pages/chunks.
        """
        print("🔧 [EmbeddingLoader] Initializing SentenceTransformer model...")
        try:
            cache_folder = (
                os.getenv("EMBEDDING_MODEL_PATH")
                or os.getenv("HF_HOME")
                or os.getenv("HUGGINGFACE_HUB_CACHE")
                or os.getenv("SENTENCE_TRANSFORMERS_HOME")
            )
            if cache_folder:
                os.makedirs(cache_folder, exist_ok=True)
                print(f"📦 [EmbeddingLoader] Using cache folder: {cache_folder}")
                os.environ.setdefault("HF_HOME", cache_folder)
                os.environ.setdefault("HUGGINGFACE_HUB_CACHE", cache_folder)
                os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", cache_folder)
            else:
                default_cache = os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
                print(f"📦 [EmbeddingLoader] Using default cache folder: {default_cache}")
                cache_folder = default_cache

            expected_model_dir = os.path.join(cache_folder, "hub", "models--BAAI--bge-m3")
            if os.path.isdir(expected_model_dir):
                print(f"✅ [EmbeddingLoader] Found cached model directory: {expected_model_dir}")
            else:
                print(f"⚠️ [EmbeddingLoader] Cached model directory not found at: {expected_model_dir}")

            model_kwargs = {
                "model_name_or_path": "BAAI/bge-m3",
                "device": "cpu",
            }
            if cache_folder:
                model_kwargs["cache_folder"] = cache_folder

            self.embedding_model = SentenceTransformer(**model_kwargs)
            print("✅ [EmbeddingLoader] SentenceTransformer model loaded successfully")
        except Exception as e:
            error_msg = f"Failed to load SentenceTransformer model: {str(e)}"
            print(f"❌ [EmbeddingLoader] {error_msg}")
            raise Exception(error_msg)
        
        self.document_summary = None
        self.page_summaries = None

        if cached_data:
            self.pages_and_chunks, self.embeddings = cached_data
            print("✅ [EmbeddingLoader] Using cached embeddings data")
        else:
            self.embeddings_file_path = embeddings_file_path
            self.enhanced_json_path = enhanced_json_path
            print(f"📂 [EmbeddingLoader] Loading embeddings from: {embeddings_file_path}")
            self.pages_and_chunks, self.embeddings = self._load_embeddings()
            if enhanced_json_path:
                print(f"📄 [EmbeddingLoader] Loading enhanced JSON from: {enhanced_json_path}")
                self.document_summary, self.page_summaries = self._load_enhanced_json()
            print("✅ [EmbeddingLoader] Initialization complete")

    def _load_embeddings(self):
        """Load and process the embeddings CSV file."""
        print(f"Loading embeddings from: {self.embeddings_file_path}")
        try:
            # Load the CSV file
            df = pd.read_csv(self.embeddings_file_path)
            print("Embedding file loaded")

            # Convert stringified embeddings to numpy arrays
            df['embedding'] = df['embedding'].apply(lambda x: np.array(json.loads(x), dtype=np.float64))
            
            # Combine all embeddings into a single numpy array
            embeddings = np.vstack(df['embedding'].to_numpy())
            
            # Convert to list of dicts for pages and chunks
            pages_and_chunks = df.to_dict(orient="records")
            
            # Debug info
            # print("DataFrame columns:", df.columns)
            # print("\nFirst few rows of the DataFrame:")
            # print(df.head())
            
            return pages_and_chunks, embeddings  # `embeddings` is now a single numpy array
            
        except Exception as e:
            raise Exception(f"Failed to load embeddings: {str(e)}")


    def _load_enhanced_json(self):
        """Load and process the enhanced JSON file if provided."""
        try:
            with open(self.enhanced_json_path, 'r') as file:
                enhanced_data = json.load(file)
            # Print a sample of the enhanced data
            # print(f"Enhanced data sample: {enhanced_data}")
            return (
                enhanced_data.get('document_summary', 'No document summary available.'),
                {int(page): data['summary'] for page, data in enhanced_data.get('pages', {}).items()}
            )
        except Exception as e:
            print(f"Warning: Failed to load enhanced JSON: {str(e)}")
            return None, None

    def retrieve_relevant_resources(self, query: str, n_resources_to_return: int = 4):
        """Return top k resources using hybrid retrieval (lexical + semantic)."""
        search_start_time = time.time()
        print(f"🔍 [retrieve_relevant_resources] Starting: query_length={len(query)}, n_results={n_resources_to_return}")

        retriever = HybridRetriever(
            pages_and_chunks=self.pages_and_chunks,
            embeddings=self.embeddings,
            encode_fn=self.embedding_model.encode,
        )
        results = retriever.retrieve(query, top_k=n_resources_to_return)

        total_duration = (time.time() - search_start_time) * 1000
        print(f"✅ [retrieve_relevant_resources] Total search completed in {total_duration:.2f}ms")

        return results



    def print_top_results_and_scores(self, query: str, n_resources_to_return: int = 5):
        """Retrieves and prints most relevant resources."""
        print(f"Printing top results and scores for query: {query}")
        results = self.retrieve_relevant_resources(
            query=query,
            n_resources_to_return=n_resources_to_return
        )
        
        for i, result in enumerate(results):
            chunk = result["chunk"]
            chunk_text = chunk.get("content", "Chunk not found")
            score = result.get("score", 0)
            print(f"\nResult {i+1}: Score: {score:.4f}, Page: {chunk.get('page', 'Unknown')}")
            print(textwrap.fill(chunk_text[:200] + "..." if len(chunk_text) > 200 else chunk_text))
            
        return results

    def format_prompt(self, query: str, context_items: list[dict]) -> str:
        """Formats the prompt with context and query."""
        formatted_context = ""
        
        for item in context_items:
            page_number = item.get('page', 'Unknown')
            page_summary = self.page_summaries.get(page_number, '') if self.page_summaries else ''
            if page_summary:
                print(f"Page {page_number}: {page_summary}")
                formatted_context += f"Page {page_number}: {page_summary}\n\n"
            formatted_context += f"Content from page {page_number}: {item.get('content', '')}\n\n"

        return f"""Use the following context to answer the user query:

{formatted_context}

User query: {query}
Answer:"""

async def generate_bot_response_stream(message, chat_history, embeddings_loader, client, system_prompt, request_start_time=None, rulebook_id: str | None = None):
    """Generate a streaming response using the embedding loader and OpenAI."""
    if request_start_time is None:
        request_start_time = time.time()
    
    total_start_time = time.time()
    preprocessing_duration = (total_start_time - request_start_time) * 1000
    print(f"🔵 [generate_bot_response_stream] Starting: message_length={len(message)}, chat_history_length={len(chat_history)}, preprocessing_took={preprocessing_duration:.2f}ms")
    
    def progress_event(stage: str, message_text: str, metadata: dict | None = None):
        payload = {"type": "progress", "stage": stage, "message": message_text}
        if metadata:
            payload["metadata"] = metadata
        return f"data: {json.dumps(payload)}\n\n"

    # Step 1: Hybrid search
    search_start_time = time.time()
    print(f"🔍 [generate_bot_response_stream] Starting semantic search at {search_start_time}")
    initial_metadata = {"chunksSearched": len(embeddings_loader.pages_and_chunks)}
    results = embeddings_loader.print_top_results_and_scores(query=message)
    search_end_time = time.time()
    search_duration = (search_end_time - search_start_time) * 1000
    print(f"⏱️ [generate_bot_response_stream] Hybrid search completed in {search_duration:.2f}ms: found {len(results)} results (ended at {search_end_time})")
    
    # Step 2: Get context items
    context_start_time = time.time()
    print(f"📚 [generate_bot_response_stream] Starting context retrieval at {context_start_time}")
    context_items = [result["chunk"] for result in results]
    context_end_time = time.time()
    context_duration = (context_end_time - context_start_time) * 1000
    print(f"⏱️ [generate_bot_response_stream] Context items retrieved in {context_duration:.2f}ms: {len(context_items)} items (ended at {context_end_time})")
    
    # Step 3: Format prompt
    prompt_start_time = time.time()
    print(f"📝 [generate_bot_response_stream] Starting prompt formatting at {prompt_start_time}")
    prompt = embeddings_loader.format_prompt(query=message, context_items=context_items)
    prompt_end_time = time.time()
    prompt_duration = (prompt_end_time - prompt_start_time) * 1000
    prompt_length = len(prompt)
    system_prompt_length = len(system_prompt)
    total_prompt_length = prompt_length + system_prompt_length
    print(f"⏱️ [generate_bot_response_stream] Prompt formatted in {prompt_duration:.2f}ms: prompt_length={prompt_length}, system_prompt_length={system_prompt_length}, total={total_prompt_length} (ended at {prompt_end_time})")

    debug_context_items = []
    context_chars = 0
    for result in results:
        chunk = result.get("chunk", {})
        chunk_content = chunk.get("content", "")
        context_chars += len(chunk_content)
        debug_context_items.append({
            "page": chunk.get("page"),
            "content": chunk_content,
            "source": chunk.get("source"),
            "section": chunk.get("section"),
            "score": result.get("score"),
            "lexicalScore": result.get("lexical_score"),
            "semanticScore": result.get("semantic_score"),
        })
    
    # Step 4: OpenAI API call with streaming (Responses API)
    openai_call_start_time = time.time()
    time_to_api_call = (openai_call_start_time - request_start_time) * 1000
    print(f"⏱️ [generate_bot_response_stream] Time from request received to API call initiation: {time_to_api_call:.2f}ms")
    print(f"🌐 [generate_bot_response_stream] Calling OpenAI Responses API with streaming: model=gpt-5-nano-2025-08-07, prompt_length={total_prompt_length}")
    
    full_response = ""
    http_request_start_time = time.time()
    time_before_api_call = (http_request_start_time - request_start_time) * 1000
    print(f"⏱️ [generate_bot_response_stream] About to call client.responses.stream() - time_from_request={time_before_api_call:.2f}ms (absolute_time={http_request_start_time})")
    print(f"⏱️ [generate_bot_response_stream] Client type: {type(client)}, Client ID: {id(client)}")
    
    call_thread_id = threading.current_thread().ident
    print(f"🧵 [generate_bot_response_stream] Calling from thread ID: {call_thread_id}")
    
    responses_stream_manager = client.responses.stream(
        model="gpt-5.2-chat-latest",
        instructions=system_prompt,
        input=prompt,
        temperature=1,
        # top_p=1,
        store=False,
    )
    api_call_exit_time: float | None = None
    
    async def stream_generator():
        nonlocal full_response, openai_call_start_time, time_to_api_call, request_start_time, api_call_exit_time
        
        try:
            # Emit progress stages before token streaming
            yield progress_event("search", "Searching rulebooks...", initial_metadata)
            if results:
                top_score = max(result.get("score", 0) for result in results)
            else:
                top_score = 0
            yield progress_event(
                "search",
                f"Found {len(results)} relevant sections",
                {
                    "matchesFound": len(results),
                    "topSimilarity": round(float(top_score), 4),
                    "processingTimeMs": int(search_duration),
                },
            )
            yield progress_event(
                "context",
                f"Building answer from top {min(len(results), 3)} sources...",
                {
                    "query": message,
                    "rulebookId": rulebook_id,
                    "systemPrompt": system_prompt,
                    "prompt": prompt,
                    "chunks": debug_context_items,
                    "sizes": {
                        "systemPromptChars": system_prompt_length,
                        "promptChars": prompt_length,
                        "totalPromptChars": total_prompt_length,
                        "contextChars": context_chars,
                        "chunkCount": len(debug_context_items),
                    },
                    "timings": {
                        "searchMs": int(search_duration),
                        "contextMs": int(context_duration),
                        "promptMs": int(prompt_duration),
                    }
                }
            )
            yield progress_event("generation", "Generating explanation...")

            yielded_count = 0
            token_count = 0
            first_token_time = None
            
            async with responses_stream_manager as response_stream:
                api_call_exit_time = time.time()
                time_to_stream_ready = (api_call_exit_time - request_start_time) * 1000
                print(f"⏱️ [stream_generator] Responses stream ready at {api_call_exit_time} (time_from_request={time_to_stream_ready:.2f}ms)")
                
                async for event in response_stream:
                    event_type = getattr(event, "type", None)
                    
                    if event_type == "response.output_text.delta":
                        content = getattr(event, "delta", "")
                        if not content:
                            continue
                        
                        token_count += 1
                        yielded_count += 1
                        full_response += content
                        
                        # Debug: Log full response state periodically
                        if token_count == 1 or token_count % 50 == 0:
                            print(f"📋 [stream_generator] Token #{token_count} - Full response state:")
                            print(f"   - Current delta: {repr(content)}")
                            print(f"   - Full response length: {len(full_response)}")
                            print(f"   - Last 200 chars: {repr(full_response[-200:])}")
                            print(f"   - Newline count: {full_response.count(chr(10))}")
                            print(f"   - Has markdown headers: {'##' in full_response or '###' in full_response}")
                        
                        if first_token_time is None:
                            first_token_time = time.time()
                            ttft = (first_token_time - request_start_time) * 1000
                            preview = content[:100] if len(content) > 100 else content
                            print(f"🚀 [TTFT] First token received and yielded: {ttft:.2f}ms")
                            print(f"🚀 [TTFT] First token content: {repr(preview)}")
                            print(f"🚀 [TTFT] First token raw bytes: {content.encode('utf-8')}")
                        
                        yield f"data: {json.dumps(content)}\n\n"
                    
                    elif event_type == "response.error":
                        error_message = getattr(getattr(event, "error", None), "message", "Unknown Responses error")
                        print(f"❌ [stream_generator] Responses error event: {error_message}")
                        yield f"data: [ERROR]{error_message}\n\n"
                        return
                    
                    elif event_type == "response.completed":
                        print("🏁 [stream_generator] Responses stream reported completion event")
            
            print(f"🏁 [stream_generator] Stream complete: {token_count} tokens processed, {yielded_count} tokens yielded")
            
            # Debug: Log final complete response
            print(f"📋 [stream_generator] FINAL COMPLETE RESPONSE:")
            print(f"   - Length: {len(full_response)}")
            print(f"   - Newline count: {full_response.count(chr(10))}")
            print(f"   - Has markdown headers (##): {full_response.count('##')}")
            print(f"   - Has markdown lists (-): {full_response.count(chr(10) + '-')}")
            print(f"   - Full content (first 500 chars): {repr(full_response[:500])}")
            print(f"   - Full content (last 500 chars): {repr(full_response[-500:])}")
            print(f"   - Full content (raw): {repr(full_response)}")
            
            openai_duration = (time.time() - openai_call_start_time) * 1000
            total_duration = (time.time() - request_start_time) * 1000
            ttft_value = int((first_token_time - request_start_time) * 1000) if first_token_time else None

            yield progress_event(
                "complete",
                "Answer ready",
                {
                    "timings": {
                        "openaiMs": int(openai_duration),
                        "totalMs": int(total_duration),
                        "timeToFirstTokenMs": ttft_value,
                    },
                    "sizes": {
                        "responseChars": len(full_response),
                    },
                    "tokenCount": token_count,
                    "yieldedCount": yielded_count,
                }
            )
            yield "data: [DONE]\n\n"

            chat_history.append((message, full_response))
            print(f"✅ [generate_bot_response_stream] Streaming completed in {openai_duration:.2f}ms: response_length={len(full_response)}")
            print(f"✅ [generate_bot_response_stream] Total generation completed in {total_duration:.2f}ms")
            print("📊 [generate_bot_response_stream] Timing breakdown:")
            print(f"   - Request received → API call initiated: {time_to_api_call:.2f}ms")
            if api_call_exit_time:
                print(f"   - Request received → Responses stream ready: {(api_call_exit_time - request_start_time) * 1000:.2f}ms")
            if first_token_time:
                ttft = (first_token_time - request_start_time) * 1000
                print(f"   - Request received → First token: {ttft:.2f}ms (TTFT)")
        except Exception as e:
            print(f"❌ [generate_bot_response_stream] Streaming error: {str(e)}")
            yield f"data: [ERROR]{str(e)}\n\n"
            raise
    
    return stream_generator(), chat_history

