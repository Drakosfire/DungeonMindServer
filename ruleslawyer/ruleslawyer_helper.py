import pandas as pd
import numpy as np
from openai import OpenAI
from sentence_transformers import util, SentenceTransformer
import torch
import time
from datetime import datetime
import textwrap
import json
import os

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
            # Use environment variable for cache folder if set, otherwise use default location
            # HF_HOME or HUGGINGFACE_HUB_CACHE env vars are respected by SentenceTransformer
            # If not set, SentenceTransformer uses default ~/.cache/huggingface
            cache_folder = os.getenv('HF_HOME') or os.getenv('HUGGINGFACE_HUB_CACHE')
            if cache_folder:
                print(f"📦 [EmbeddingLoader] Using cache folder from env: {cache_folder}")
            
            model_kwargs = {
                'model_name_or_path': 'BAAI/bge-m3',
                'device': 'cpu',
            }
            if cache_folder:
                model_kwargs['cache_folder'] = cache_folder
            
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
        """Embeds a query and returns top k scores and indices from embeddings."""
        import time as time_module
        
        search_start_time = time_module.time()
        print(f"🔍 [retrieve_relevant_resources] Starting: query_length={len(query)}, n_results={n_resources_to_return}")
        
        # Step 1: Encode query
        encode_start_time = time_module.time()
        query_embedding = self.embedding_model.encode(query, convert_to_tensor=False)
        encode_duration = (time_module.time() - encode_start_time) * 1000
        print(f"⏱️ [retrieve_relevant_resources] Query encoded in {encode_duration:.2f}ms: embedding_dim={len(query_embedding)}")
        
        # Step 2: Convert to tensors
        tensor_start_time = time_module.time()
        query_tensor = torch.tensor(np.array([query_embedding], dtype=np.float64), dtype=torch.float64).to('cpu')
        embeddings_tensor = torch.tensor(self.embeddings, dtype=torch.float64).to('cpu')
        tensor_duration = (time_module.time() - tensor_start_time) * 1000
        print(f"⏱️ [retrieve_relevant_resources] Tensors created in {tensor_duration:.2f}ms: embeddings_shape={embeddings_tensor.shape}")

        # Step 3: Calculate similarity scores
        similarity_start_time = time_module.time()
        dot_scores = util.dot_score(query_tensor, embeddings_tensor)[0]
        similarity_duration = (time_module.time() - similarity_start_time) * 1000
        print(f"⏱️ [retrieve_relevant_resources] Similarity scores calculated in {similarity_duration:.2f}ms: scores_shape={dot_scores.shape}")
        
        # Step 4: Get top k results
        topk_start_time = time_module.time()
        topk_result = torch.topk(input=dot_scores, k=n_resources_to_return)
        topk_duration = (time_module.time() - topk_start_time) * 1000
        print(f"⏱️ [retrieve_relevant_resources] Top-k retrieved in {topk_duration:.2f}ms")
        
        total_duration = (time_module.time() - search_start_time) * 1000
        print(f"✅ [retrieve_relevant_resources] Total search completed in {total_duration:.2f}ms")
        
        return topk_result



    def print_top_results_and_scores(self, query: str, n_resources_to_return: int = 5):
        """Retrieves and prints most relevant resources."""
        print(f"Printing top results and scores for query: {query}")
        scores, indices = self.retrieve_relevant_resources(
            query=query,
            n_resources_to_return=n_resources_to_return
        )
        
        for i, (score, index) in enumerate(zip(scores, indices)):
            chunk = self.pages_and_chunks[index]
            chunk_text = chunk.get("content", "Chunk not found")
            print(f"\nResult {i+1}: Score: {score:.4f}, Page: {chunk.get('page', 'Unknown')}")
            print(textwrap.fill(chunk_text[:200] + "..." if len(chunk_text) > 200 else chunk_text))
            
        return scores, indices

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

def generate_bot_response(message, chat_history, embeddings_loader, client, system_prompt):
    """Generate a response using the embedding loader and OpenAI."""
    import time as time_module
    
    total_start_time = time_module.time()
    print(f"🔵 [generate_bot_response] Starting: message_length={len(message)}, chat_history_length={len(chat_history)}")
    
    # Step 1: Semantic search
    search_start_time = time_module.time()
    scores, indices = embeddings_loader.print_top_results_and_scores(query=message)
    search_duration = (time_module.time() - search_start_time) * 1000
    print(f"⏱️ [generate_bot_response] Semantic search completed in {search_duration:.2f}ms: found {len(indices)} results")
    
    # Step 2: Get context items
    context_start_time = time_module.time()
    context_items = [embeddings_loader.pages_and_chunks[i] for i in indices]
    context_duration = (time_module.time() - context_start_time) * 1000
    print(f"⏱️ [generate_bot_response] Context items retrieved in {context_duration:.2f}ms: {len(context_items)} items")
    
    # Step 3: Format prompt
    prompt_start_time = time_module.time()
    prompt = embeddings_loader.format_prompt(query=message, context_items=context_items)
    prompt_duration = (time_module.time() - prompt_start_time) * 1000
    prompt_length = len(prompt)
    system_prompt_length = len(system_prompt)
    total_prompt_length = prompt_length + system_prompt_length
    print(f"⏱️ [generate_bot_response] Prompt formatted in {prompt_duration:.2f}ms: prompt_length={prompt_length}, system_prompt_length={system_prompt_length}, total={total_prompt_length}")
    
    # Step 4: OpenAI API call
    openai_start_time = time_module.time()
    print(f"🌐 [generate_bot_response] Calling OpenAI API: model=gpt-5-mini-2025-08-07, prompt_length={total_prompt_length}")
    bot_message = client.chat.completions.create(
        model="gpt-5-mini-2025-08-07",
        messages=[{"role": "user", "content": f"{system_prompt} {prompt}"}],
        temperature=1,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )
    openai_duration = (time_module.time() - openai_start_time) * 1000
    response_length = len(bot_message.choices[0].message.content) if bot_message.choices[0].message.content else 0
    print(f"⏱️ [generate_bot_response] OpenAI API call completed in {openai_duration:.2f}ms: response_length={response_length}")
    
    # Step 5: Extract response
    response = bot_message.choices[0].message.content
    chat_history.append((message, response))
    
    # REMOVED: time.sleep(2) - This was adding 2 seconds of artificial delay!
    
    total_duration = (time_module.time() - total_start_time) * 1000
    print(f"✅ [generate_bot_response] Total generation completed in {total_duration:.2f}ms")
    print(f"   Breakdown: search={search_duration:.2f}ms, context={context_duration:.2f}ms, prompt={prompt_duration:.2f}ms, openai={openai_duration:.2f}ms")
    
    return response, chat_history

async def generate_bot_response_stream(message, chat_history, embeddings_loader, client, system_prompt, request_start_time=None):
    """Generate a streaming response using the embedding loader and OpenAI."""
    import time as time_module
    
    if request_start_time is None:
        request_start_time = time_module.time()
    
    total_start_time = time_module.time()
    preprocessing_duration = (total_start_time - request_start_time) * 1000
    print(f"🔵 [generate_bot_response_stream] Starting: message_length={len(message)}, chat_history_length={len(chat_history)}, preprocessing_took={preprocessing_duration:.2f}ms")
    
    # Step 1: Semantic search
    search_start_time = time_module.time()
    print(f"🔍 [generate_bot_response_stream] Starting semantic search at {search_start_time}")
    scores, indices = embeddings_loader.print_top_results_and_scores(query=message)
    search_end_time = time_module.time()
    search_duration = (search_end_time - search_start_time) * 1000
    print(f"⏱️ [generate_bot_response_stream] Semantic search completed in {search_duration:.2f}ms: found {len(indices)} results (ended at {search_end_time})")
    
    # Step 2: Get context items
    context_start_time = time_module.time()
    print(f"📚 [generate_bot_response_stream] Starting context retrieval at {context_start_time}")
    context_items = [embeddings_loader.pages_and_chunks[i] for i in indices]
    context_end_time = time_module.time()
    context_duration = (context_end_time - context_start_time) * 1000
    print(f"⏱️ [generate_bot_response_stream] Context items retrieved in {context_duration:.2f}ms: {len(context_items)} items (ended at {context_end_time})")
    
    # Step 3: Format prompt
    prompt_start_time = time_module.time()
    print(f"📝 [generate_bot_response_stream] Starting prompt formatting at {prompt_start_time}")
    prompt = embeddings_loader.format_prompt(query=message, context_items=context_items)
    prompt_end_time = time_module.time()
    prompt_duration = (prompt_end_time - prompt_start_time) * 1000
    prompt_length = len(prompt)
    system_prompt_length = len(system_prompt)
    total_prompt_length = prompt_length + system_prompt_length
    print(f"⏱️ [generate_bot_response_stream] Prompt formatted in {prompt_duration:.2f}ms: prompt_length={prompt_length}, system_prompt_length={system_prompt_length}, total={total_prompt_length} (ended at {prompt_end_time})")
    
    # Step 4: OpenAI API call with streaming (Responses API)
    openai_call_start_time = time_module.time()
    time_to_api_call = (openai_call_start_time - request_start_time) * 1000
    print(f"⏱️ [generate_bot_response_stream] Time from request received to API call initiation: {time_to_api_call:.2f}ms")
    print(f"🌐 [generate_bot_response_stream] Calling OpenAI Responses API with streaming: model=gpt-5-nano-2025-08-07, prompt_length={total_prompt_length}")
    
    full_response = ""
    http_request_start_time = time_module.time()
    time_before_api_call = (http_request_start_time - request_start_time) * 1000
    print(f"⏱️ [generate_bot_response_stream] About to call client.responses.stream() - time_from_request={time_before_api_call:.2f}ms (absolute_time={http_request_start_time})")
    print(f"⏱️ [generate_bot_response_stream] Client type: {type(client)}, Client ID: {id(client)}")
    
    import threading
    call_thread_id = threading.current_thread().ident
    print(f"🧵 [generate_bot_response_stream] Calling from thread ID: {call_thread_id}")
    
    responses_stream_manager = client.responses.stream(
        model="gpt-5-nano",
        instructions=system_prompt,
        input=prompt,
        temperature=1,
        top_p=1,
        store=False,
    )
    api_call_exit_time: float | None = None
    
    async def stream_generator():
        import asyncio
        nonlocal full_response, openai_call_start_time, time_to_api_call, request_start_time, api_call_exit_time
        
        try:
            yielded_count = 0
            token_count = 0
            first_token_time = None
            
            async with responses_stream_manager as response_stream:
                api_call_exit_time = time_module.time()
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
                            first_token_time = time_module.time()
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
            
            yield "data: [DONE]\n\n"
            
            chat_history.append((message, full_response))
            
            openai_duration = (time_module.time() - openai_call_start_time) * 1000
            total_duration = (time_module.time() - request_start_time) * 1000
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

