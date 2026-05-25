"""LLM inference via Ollama native API (/api/chat).

Uses /api/chat (not /v1/chat/completions) because:
- think=false is actually honored here (OpenAI compat endpoint ignores it)
- keep_alive param works on native endpoints
"""
import asyncio
import json
import logging
from typing import AsyncIterator

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

_client = httpx.AsyncClient(
    timeout=httpx.Timeout(connect=10, read=1800, write=60, pool=10),
    limits=httpx.Limits(max_keepalive_connections=4, keepalive_expiry=300),
)


def _add_no_think(messages: list[dict]) -> list[dict]:
    msgs = list(messages)
    for i, m in enumerate(msgs):
        if m.get("role") == "user":
            if "/no_think" not in m["content"]:
                msgs[i] = {**m, "content": "/no_think " + m["content"]}
            break
    return msgs


async def chat_stream(
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 800,
) -> AsyncIterator[str]:
    """Yield text tokens from Ollama streaming chat."""
    payload = {
        "model": model or settings.chat_model_name,
        "messages": _add_no_think(messages),
        "stream": True,
        "think": False,
        "keep_alive": "30m",
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.7,
        },
    }
    async with _client.stream(
        "POST", f"{settings.ollama_url}/api/chat", json=payload
    ) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
                token = chunk.get("message", {}).get("content", "")
                if token:
                    yield token
                if chunk.get("done"):
                    break
            except (json.JSONDecodeError, KeyError):
                continue


async def chat_once(
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 1500,
) -> str:
    """Single blocking call — used for ingest summarization."""
    payload = {
        "model": model or settings.ingest_model_name,
        "messages": _add_no_think(messages),
        "stream": False,
        "think": False,
        "keep_alive": "30m",
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.3,
        },
    }
    resp = await _client.post(
        f"{settings.ollama_url}/api/chat", json=payload
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


async def warmup_chat_model() -> None:
    """Pre-load chat model into Ollama RAM + start keepalive loop."""
    try:
        logger.info("Warming up chat model %s ...", settings.chat_model_name)
        await _client.post(
            f"{settings.ollama_url}/api/generate",
            json={"model": settings.chat_model_name, "prompt": "", "keep_alive": "30m"},
        )
        logger.info("Chat model warm — TTFT cold-start eliminated")
    except Exception as exc:
        logger.warning("Model warmup failed (non-fatal): %s", exc)
        return
    await _keepalive_loop()


async def _keepalive_loop() -> None:
    """Ping Ollama every 25 min so chat model stays in RAM indefinitely."""
    while True:
        await asyncio.sleep(25 * 60)
        try:
            await _client.post(
                f"{settings.ollama_url}/api/generate",
                json={"model": settings.chat_model_name, "prompt": "", "keep_alive": "30m"},
            )
            logger.debug("Keepalive ping sent for %s", settings.chat_model_name)
        except Exception as exc:
            logger.warning("Keepalive ping failed: %s", exc)


async def is_llm_ready() -> bool:
    """Check if Ollama is running and both configured models are available."""
    try:
        r = await _client.get(f"{settings.ollama_url}/api/tags")
        if r.status_code != 200:
            return False
        installed = [m["name"] for m in r.json().get("models", [])]
        chat_ok = any(settings.chat_model_name in m for m in installed)
        ingest_ok = any(settings.ingest_model_name in m for m in installed)
        return chat_ok and ingest_ok
    except Exception:
        return False
