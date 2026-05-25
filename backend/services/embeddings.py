"""Embedding service via Ollama /api/embed."""
import logging

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

_client = httpx.AsyncClient(
    timeout=httpx.Timeout(connect=10, read=60, write=10, pool=10),
    limits=httpx.Limits(max_keepalive_connections=2, keepalive_expiry=300),
)


async def embed(text: str) -> list[float]:
    """Return embedding vector for text. Raises on failure."""
    resp = await _client.post(
        f"{settings.ollama_url}/api/embed",
        json={"model": settings.embed_model_name, "input": text},
    )
    resp.raise_for_status()
    data = resp.json()
    return data["embeddings"][0]


async def warmup_embed_model() -> None:
    """Pre-load embed model into Ollama RAM."""
    try:
        await _client.post(
            f"{settings.ollama_url}/api/embed",
            json={"model": settings.embed_model_name, "input": "warmup", "keep_alive": "30m"},
        )
        logger.info("Embed model warm: %s", settings.embed_model_name)
    except Exception as exc:
        logger.warning("Embed model warmup failed (non-fatal): %s", exc)
