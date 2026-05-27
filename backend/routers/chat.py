"""Chat endpoint — RAG over wiki + streaming SSE response with source attribution."""
import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.services import embeddings, llm, search
from backend.services.cache import semantic_cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])

SYSTEM_PROMPT = (
    "You are the assistant of an offline personal wiki. "
    "The system automatically indexes documents (PDF, images, DOCX) uploaded by the user. "
    "Answer ONLY using the wiki context provided below. Always cite the source file. "
    "If the context is empty or says 'No wiki content': tell the user they need to upload files "
    "via the interface (drag or click Upload in the left panel) — "
    "the system will process them automatically with OCR and make them searchable. "
    "If the question is not covered by the available context, say so explicitly. "
    "No hallucinations, no external knowledge."
)


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


@router.post("")
async def chat(req: ChatRequest):
    """
    Stream a chat response using BM25 wiki search for context.
    Checks semantic cache first (no-history queries only).
    SSE format: data: <json>\n\n
    Final event: data: {"sources": [...], "done": true}\n\n
    """
    # Semantic cache — only for fresh conversations (history changes context)
    if not req.history:
        try:
            query_emb = await embeddings.embed(req.message)
            hit = semantic_cache.get(query_emb)
            if hit:
                cached_response, cached_sources = hit
                return StreamingResponse(
                    _stream_cached(cached_response, cached_sources),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )
        except Exception as exc:
            logger.warning("Cache lookup failed (non-fatal): %s", exc)
            query_emb = None
    else:
        query_emb = None

    results = search.search(req.message, top_k=3, passage_len=300)

    context_parts = []
    sources: list[str] = []
    seen_sources: set[str] = set()
    for r in results:
        context_parts.append(f"[From: {r.source_file or r.wiki_path.name}]\n{r.passage}")
        if r.source_file and r.source_file not in seen_sources:
            seen_sources.add(r.source_file)
            sources.append(r.source_file)

    context = "\n\n---\n\n".join(context_parts) if context_parts else "No wiki content available yet."

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"WIKI CONTEXT:\n{context}\n\nQUESTION: {req.message}"},
    ]
    if req.history:
        messages = messages[:1] + req.history[-4:] + messages[1:]

    return StreamingResponse(
        _stream(messages, sources, query_emb),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_cached(response: str, sources: list[str]):
    """Yield a cached response instantly as a single SSE token."""
    yield f"data: {json.dumps({'token': response, 'cached': True})}\n\n"
    yield f"data: {json.dumps({'sources': sources, 'done': True, 'cached': True})}\n\n"


async def _stream(messages: list[dict], sources: list[str], query_emb: list[float] | None):
    """Stream LLM response, accumulate tokens, store in semantic cache on completion."""
    tokens: list[str] = []
    try:
        async for token in llm.chat_stream(messages, max_tokens=800):
            yield f"data: {json.dumps({'token': token})}\n\n"
            tokens.append(token)
    except Exception as exc:
        logger.error("LLM stream error: %s", exc)
        yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    if query_emb and tokens:
        try:
            semantic_cache.set(query_emb, "".join(tokens), sources)
        except Exception as exc:
            logger.warning("Cache store failed (non-fatal): %s", exc)

    yield f"data: {json.dumps({'sources': sources, 'done': True})}\n\n"


@router.delete("/cache")
async def clear_cache():
    """Clear the semantic response cache."""
    size = semantic_cache.size
    semantic_cache.clear()
    return {"cleared": size}


@router.get("/cache/stats")
async def cache_stats():
    """Return semantic cache statistics."""
    return {
        "entries": semantic_cache.size,
        "max_entries": semantic_cache.max_entries,
        "threshold": semantic_cache.threshold,
    }
