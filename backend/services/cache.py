"""Semantic response cache using cosine similarity on query embeddings."""
import logging
import math
from dataclasses import dataclass

from backend.config import settings

logger = logging.getLogger(__name__)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@dataclass
class _Entry:
    embedding: list[float]
    response: str
    sources: list[str]


class SemanticCache:
    """
    In-memory cache: stores (embedding, response, sources) per query.
    On hit (cosine similarity >= threshold), returns cached response
    without calling the LLM — TTFT drops to ~0ms.
    """

    def __init__(self) -> None:
        self._entries: list[_Entry] = []

    @property
    def threshold(self) -> float:
        return settings.cache_similarity_threshold

    @property
    def max_entries(self) -> int:
        return settings.cache_max_entries

    def get(self, embedding: list[float]) -> tuple[str, list[str]] | None:
        best_score = 0.0
        best_entry: _Entry | None = None
        for entry in self._entries:
            score = _cosine(embedding, entry.embedding)
            if score > best_score:
                best_score = score
                best_entry = entry
        if best_entry and best_score >= self.threshold:
            logger.info("Cache HIT (similarity=%.3f, entries=%d)", best_score, len(self._entries))
            return best_entry.response, best_entry.sources
        return None

    def set(self, embedding: list[float], response: str, sources: list[str]) -> None:
        if len(self._entries) >= self.max_entries:
            self._entries.pop(0)
        self._entries.append(_Entry(embedding=embedding, response=response, sources=sources))
        logger.debug("Cache stored (entries=%d)", len(self._entries))

    def clear(self) -> None:
        self._entries.clear()
        logger.info("Semantic cache cleared")

    @property
    def size(self) -> int:
        return len(self._entries)


semantic_cache = SemanticCache()
