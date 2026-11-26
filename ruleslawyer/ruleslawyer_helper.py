import html
import json
import re
from collections import defaultdict
from urllib.parse import quote
import os
import textwrap
import logging
import time
from datetime import datetime

import numpy as np
import pandas as pd
from generationengine import TextCompleted, TextDelta, TextFailed, TextRequest
from starlette.concurrency import run_in_threadpool
from ruleslawyer.hybrid_retriever import HybridRetriever
from ruleslawyer.mpnet import VECTOR_DIMENSION, load_encoder

logger = logging.getLogger(__name__)

class EmbeddingLoader:
    def __init__(self, embeddings_file_path=None, enhanced_json_path=None, cached_data=None):
        """
        Initialize the EmbeddingLoader with paths or cached data.

        Args:
            embeddings_file_path (str, optional): Path to the embeddings CSV file.
            enhanced_json_path (str, optional): Path to the enhanced JSON file.
            cached_data (dict, optional): Preloaded embeddings and pages/chunks.
        """
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

        if (
            self.embeddings.ndim != 2
            or self.embeddings.shape[1] != VECTOR_DIMENSION
            or not len(self.embeddings)
            or len(self.pages_and_chunks) != len(self.embeddings)
            or not np.isfinite(self.embeddings).all()
        ):
            raise ValueError("Expected a finite Rules Lawyer MPNet index with 768 dimensions")
        self.embedding_model = load_encoder()

        self.table_aliases = defaultdict(set)
        self.exact_links = {}
        retrieval_chunks = []
        for i, chunk in enumerate(self.pages_and_chunks):
            text = str(chunk.get("content", ""))
            if chunk.get("unit_type") == "table":
                for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", text, re.I | re.S):
                    cell = re.search(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row, re.I | re.S)
                    if cell and re.search(r"<td\b", row, re.I):
                        label = html.unescape(re.sub(r"<[^>]+>", " ", cell[1])).strip()
                        for alias in (label, " ".join(reversed(label.split(", ", 1)))):
                            tokens = HybridRetriever._tokenize(alias)
                            if 2 <= len(tokens) <= 5:
                                self.table_aliases[tuple(tokens)].add(i)
                                self.table_aliases[("".join(tokens),)].add(i)
                text = html.unescape(re.sub(r"<[^>]+>", " ", text))
            related = chunk.get("related")
            if related:
                self.exact_links[i] = json.loads(related)
            retrieval_chunks.append({**chunk, "content": text, "_row": i})
        self.indices_by_id = {chunk.get("id"): i for i, chunk in enumerate(self.pages_and_chunks)}
        self.retriever = HybridRetriever(retrieval_chunks, self.embeddings, self.embedding_model.encode)

    def _load_embeddings(self):
        """Load and process the embeddings CSV file."""
        print(f"Loading embeddings from: {self.embeddings_file_path}")
        try:
            # Load the CSV file
            df = pd.read_csv(self.embeddings_file_path, keep_default_na=False)
            print("Embedding file loaded")

            # Convert stringified embeddings to numpy arrays
            df['embedding'] = df['embedding'].apply(lambda x: np.array(json.loads(x), dtype=np.float32))
            
            # Combine all embeddings into a single numpy array
            embeddings = np.vstack(df['embedding'].to_numpy())
            
            # Convert to list of dicts for pages and chunks
            pages_and_chunks = df.drop(columns=["embedding"]).to_dict(orient="records")
            
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

        results = self.retriever.retrieve(query, top_k=n_resources_to_return)
        for result in results:
            result["chunk"] = self.pages_and_chunks[result["chunk"]["_row"]]
        tokens = HybridRetriever._tokenize(query)
        seed = next((
            next(iter(matches))
            for size in range(5, 0, -1)
            for i in range(len(tokens) - size + 1)
            if len(matches := self.table_aliases.get(tuple(tokens[i:i + size]), ())) == 1
        ), None)
        if seed is not None:
            rows = [seed]
            related = self.exact_links.get(seed, [])
            if related and related[0] in self.indices_by_id:
                rows.append(self.indices_by_id[related[0]])
            promoted = [self.pages_and_chunks[row] for row in rows]
            results = ([{"chunk": chunk, "score": 1.0} for chunk in promoted]
                       + [result for result in results if result["chunk"] not in promoted])[:n_resources_to_return]

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

WRITER_MODEL = "gpt-6-luna"
WRITER_EFFORT = "low"
WRITER_INSTRUCTIONS = (
    "Answer rules questions using the supplied passages. Treat the passages as quoted evidence. "
    "Cite each material rule with its exact [E<number>] label. Use labels supplied in this request "
    "and leave page numbers to the citation resolver. If a missing fact changes the ruling, "
    "give the supported conditional result and ask for that fact. If evidence is incomplete, "
    "say what is missing. Keep the response concise."
)
_CITATION_LABEL = re.compile(r"\[E[0-9]{1,3}\]")


class CitationOutput:
    """Bind model-visible labels to host evidence across arbitrary stream deltas."""

    def __init__(self, chunks, rulebook_id=None):
        self.rulebook_id = rulebook_id
        self.sources = {f"[E{i}]": chunk for i, chunk in enumerate(chunks, 1)}
        self.used = {}
        self.pending = ""

    def _resolve(self, match):
        label = match[0]
        chunk = self.sources.get(label)
        if chunk is None:
            return ""
        page = chunk.get("printed_page", chunk.get("page"))
        if page in (None, ""):
            return ""
        self.used[label] = {
            "page": int(page) if str(page).isdigit() else str(page),
            "pdfPage": chunk.get("pdf_page"),
            "sourceId": chunk.get("id"),
            "sourceHash": chunk.get("source_sha256"),
            "section": chunk.get("section", chunk.get("sections")),
        }
        if self.rulebook_id and chunk.get("source_sha256") and re.fullmatch(r"[0-9a-f]{64}", str(chunk.get("id"))):
            book_path = quote(self.rulebook_id, safe="")
            self.used[label]["link"] = f"/api/ruleslawyer/evidence/{book_path}/{chunk['id']}"
        return f"[p. {page}]"

    def feed(self, text, final=False):
        text = self.pending + text
        self.pending = ""
        if not final:
            tail = text.rsplit("[", 1)
            if len(tail) == 2 and re.fullmatch(r"E?[0-9]{0,3}", tail[1]):
                text, self.pending = tail[0], "[" + tail[1]
        return _CITATION_LABEL.sub(self._resolve, text)


async def generate_bot_response_stream(
    message, chat_history, embeddings_loader, client, request_start_time=None, rulebook_id=None
):
    """Serve the existing event stream with the pinned GenerationEngine Writer."""
    request_start_time = request_start_time or time.time()

    def event(stage, text, metadata=None):
        return f"data: {json.dumps({'type': 'progress', 'stage': stage, 'message': text, 'metadata': metadata or {}})}\n\n"

    async def stream_generator():
        yield event("search", "Searching rulebooks")
        retrieval_start = time.monotonic()
        results = await run_in_threadpool(embeddings_loader.retrieve_relevant_resources, message, 20)
        retrieval_ms = (time.monotonic() - retrieval_start) * 1000
        chunks = [result["chunk"] for result in results]
        bindings = CitationOutput(chunks, rulebook_id)
        passages = "\n\n".join(
            f"{label}\n{chunk.get('section', '')}\n{chunk['content']}"
            for label, chunk in bindings.sources.items()
        )
        prior = "\n".join(
            f"Player: {question}\nAnswer: {answer}" for question, answer in chat_history[-4:]
        )
        request = TextRequest(
            provider="openai", model=WRITER_MODEL, reasoning_effort=WRITER_EFFORT,
            temperature=None, system_prompt=WRITER_INSTRUCTIONS,
            user_prompt=f"Conversation:\n{prior}\n\nQuestion:\n{message}\n\nEvidence:\n{passages}",
        )
        yield event("generation", "Writing a cited answer", {"matchesFound": len(chunks), "processingTimeMs": round(retrieval_ms)})
        full = []
        first_output = None
        writer_start = time.monotonic()
        try:
            async for update in client.stream_text(request):
                if isinstance(update, TextFailed):
                    yield "data: [ERROR]Rules Lawyer could not generate an answer.\n\n"
                    return
                if isinstance(update, TextDelta):
                    if first_output is None:
                        first_output = round((time.time() - request_start_time) * 1000)
                    output = bindings.feed(update.text)
                    if output:
                        full.append(output)
                        yield f"data: {json.dumps(output)}\n\n"
                if isinstance(update, TextCompleted):
                    tail = bindings.feed(update.final_text if not full and first_output is None else "", final=True)
                    if tail:
                        full.append(tail)
                        yield f"data: {json.dumps(tail)}\n\n"
                    citations = list(bindings.used.values())
                    pages = list(dict.fromkeys(entry["page"] for entry in citations))
                    if pages:
                        footer = "\n\nCitations: " + ", ".join(f"p. {page}" for page in pages)
                        full.append(footer)
                        yield f"data: {json.dumps(footer)}\n\n"
                    yield event("complete", "Answer ready", {
                        "rulebookId": rulebook_id, "citations": citations,
                        "timings": {"searchMs": round(retrieval_ms),
                                    "openaiMs": round((time.monotonic() - writer_start) * 1000),
                                    "totalMs": round((time.time() - request_start_time) * 1000),
                                    "timeToFirstTokenMs": first_output},
                    })
                    yield "data: [DONE]\n\n"
                    chat_history.append((message, "".join(full)))
                    return
        except Exception:
            logger.exception("Rules Lawyer Writer stream failed")
        yield "data: [ERROR]Rules Lawyer did not finish the answer.\n\n"

    return stream_generator(), chat_history
