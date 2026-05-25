"""BM25 full-text search over wiki markdown files."""
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import frontmatter
from rank_bm25 import BM25Okapi

from backend.config import settings

logger = logging.getLogger(__name__)

_index: "BM25Okapi | None" = None
_docs: list["Doc"] = []


@dataclass
class Doc:
    wiki_path: Path
    source_file: str   # raw filename from frontmatter
    text: str
    tokens: list[str]


@dataclass
class SearchResult:
    wiki_path: Path
    source_file: str
    passage: str
    score: float


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def rebuild_index() -> None:
    global _index, _docs
    wiki_dir = settings.wiki_dir
    docs: list[Doc] = []
    for md_file in wiki_dir.rglob("*.md"):
        try:
            post = frontmatter.load(str(md_file))
            source_file = post.metadata.get("source_file", "")
            text = post.content
            if not text.strip():
                continue
            docs.append(Doc(
                wiki_path=md_file,
                source_file=str(source_file),
                text=text,
                tokens=_tokenize(text),
            ))
        except Exception as exc:
            logger.warning("Could not parse %s: %s", md_file, exc)

    if not docs:
        _index = None
        _docs = []
        return

    _docs = docs
    _index = BM25Okapi([d.tokens for d in docs])
    logger.info("BM25 index rebuilt: %d documents", len(docs))


def search(query: str, top_k: int = 3, passage_len: int = 500) -> list[SearchResult]:
    if _index is None or not _docs:
        rebuild_index()
    if _index is None:
        return []

    tokens = _tokenize(query)
    scores = _index.get_scores(tokens)
    ranked = sorted(zip(scores, _docs), key=lambda x: x[0], reverse=True)
    results = []
    for score, doc in ranked[:top_k]:
        if score <= 0:
            continue
        passage = doc.text[:passage_len].strip()
        results.append(SearchResult(
            wiki_path=doc.wiki_path,
            source_file=doc.source_file,
            passage=passage,
            score=score,
        ))
    return results
