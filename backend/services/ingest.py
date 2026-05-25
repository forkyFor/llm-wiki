"""Ingest pipeline: raw file → OCR → LLM summary → wiki/sources/ + index + log."""
import asyncio
import logging
import re
from datetime import date
from pathlib import Path

import frontmatter

from backend.config import settings
from backend.services import ocr, llm, search
from backend.services.cache import _cosine

# Max chars per LLM call — ~12k tokens, safe for all Qwen3 variants
_CHUNK_SIZE = 50_000
_CHUNK_OVERLAP = 1_000   # reduced: 2000→1000 (saves ~12 tokens/chunk)
# Dedup: skip ingest if new doc is >95% similar to existing wiki page
_DEDUP_THRESHOLD = 0.95
_DEDUP_SAMPLE = 800      # chars to embed for similarity check

logger = logging.getLogger(__name__)
_processing: set[str] = set()

# ── Prompts (trimmed for faster prefill) ─────────────────────────────────────

SYSTEM_PROMPT = """Structured knowledge extractor. Given OCR text, produce a wiki page:

---
title: "Document Title"
type: source
tags: []
created: {date}
updated: {date}
authors: []
year: {year}
source_file: "{source_file}"
---

## Summary
[2-3 paragraphs of main content]

## Key claims
- claim 1
- claim 2

## Key entities
[[Entity1]], [[Entity2]]

## Key concepts
[[Concept1]], [[Concept2]]

## Notable quotes
> most relevant quote

## Source file
`raw/{source_file}`

Respond ONLY with markdown above, no preamble."""

CHUNK_SUMMARY_PROMPT = """Extract from this document section: main topics, key claims, entities, concepts, notable quotes. Markdown bullets. No preamble."""

MERGE_PROMPT = """Merge these partial summaries into one wiki page:

---
title: "Document Title"
type: source
tags: []
created: {date}
updated: {date}
authors: []
year: {year}
source_file: "{source_file}"
---

## Summary
[2-3 paragraphs]

## Key claims
- claim 1

## Key entities
[[Entity1]]

## Key concepts
[[Concept1]]

## Notable quotes
> quote

## Source file
`raw/{source_file}`

Respond ONLY with markdown above, no preamble."""


def _slug(filename: str) -> str:
    stem = Path(filename).stem
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return slug[:60]


def _find_wiki_source_for(raw_filename: str) -> list[Path]:
    sources_dir = settings.wiki_dir / "sources"
    if not sources_dir.exists():
        return []
    matches = []
    for md in sources_dir.glob("*.md"):
        try:
            post = frontmatter.load(str(md))
            if post.metadata.get("source_file") == raw_filename:
                matches.append(md)
        except Exception:  # nosec B110
            pass
    return matches


async def _is_duplicate(text: str) -> bool:
    """
    Embed first _DEDUP_SAMPLE chars of new doc, compare with existing wiki pages.
    Returns True if similarity > _DEDUP_THRESHOLD (content already in wiki).
    Non-fatal: returns False on any error.
    """
    sources_dir = settings.wiki_dir / "sources"
    if not sources_dir.exists():
        return False
    pages = list(sources_dir.glob("*.md"))
    if not pages:
        return False
    try:
        from backend.services import embeddings as emb
        new_emb = await emb.embed(text[:_DEDUP_SAMPLE])
        for md in pages:
            existing = md.read_text(encoding="utf-8")[:_DEDUP_SAMPLE]
            existing_emb = await emb.embed(existing)
            sim = _cosine(new_emb, existing_emb)
            if sim >= _DEDUP_THRESHOLD:
                logger.info("Duplicato rilevato (similarity=%.3f, ref=%s) — skip ingest", sim, md.name)
                return True
    except Exception as exc:
        logger.warning("Dedup check fallito (non-fatal): %s", exc)
    return False


async def ingest_file(raw_path: Path) -> bool:
    filename = raw_path.name
    if filename in _processing:
        logger.info("Already processing %s, skipping", filename)
        return False
    _processing.add(filename)
    try:
        return await _do_ingest(raw_path)
    finally:
        _processing.discard(filename)


def _split_chunks(text: str) -> list[str]:
    if len(text) <= _CHUNK_SIZE:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + _CHUNK_SIZE
        chunks.append(text[start:end])
        start = end - _CHUNK_OVERLAP
    return chunks


async def _llm_call_with_retry(
    messages: list[dict],
    attempt_label: str,
    model: str | None = None,
    max_tokens: int = 800,
) -> str:
    for attempt in range(2):
        try:
            result = await llm.chat_once(messages, model=model, max_tokens=max_tokens)
            if result.strip():
                return result
            logger.warning("%s: LLM returned empty (attempt %d)", attempt_label, attempt + 1)
        except Exception as exc:
            logger.warning("%s: LLM error (attempt %d): %s", attempt_label, attempt + 1, exc)
            if attempt == 1:
                raise
        await asyncio.sleep(2)
    return ""


async def _llm_summarize(text: str, filename: str, today: str, year: int) -> str:
    """
    Summarize document text.
    Single doc  → ingest model, max_tokens=800 (quality).
    Long doc    → map with chat model (fast, 200 tok/chunk) + reduce with chat model (700 tok).
    """
    chunks = _split_chunks(text)

    if len(chunks) == 1:
        prompt = SYSTEM_PROMPT.format(date=today, year=year, source_file=filename)
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"OCR TEXT:\n\n{chunks[0]}"},
        ]
        return await _llm_call_with_retry(
            messages, filename,
            model=settings.ingest_model_name, max_tokens=800,
        )

    # Map phase: fast model, short output per chunk
    logger.info("%s: documento lungo (%d chunks), map-reduce", filename, len(chunks))
    chunk_summaries: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        logger.info("%s: chunk %d/%d", filename, i, len(chunks))
        messages = [
            {"role": "system", "content": CHUNK_SUMMARY_PROMPT},
            {"role": "user", "content": f"SECTION {i}/{len(chunks)}:\n\n{chunk}"},
        ]
        summary = await _llm_call_with_retry(
            messages, f"{filename} chunk {i}",
            model=settings.chat_model_name, max_tokens=200,
        )
        if summary:
            chunk_summaries.append(f"[Section {i}/{len(chunks)}]\n{summary}")

    if not chunk_summaries:
        return ""

    # Reduce phase: chat model (faster), concise output
    logger.info("%s: reduce — sintesi finale da %d sezioni", filename, len(chunk_summaries))
    merged = "\n\n---\n\n".join(chunk_summaries)
    prompt = MERGE_PROMPT.format(date=today, year=year, source_file=filename)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"PARTIAL SUMMARIES:\n\n{merged}"},
    ]
    return await _llm_call_with_retry(
        messages, f"{filename} merge",
        model=settings.chat_model_name, max_tokens=700,
    )


async def _do_ingest(raw_path: Path) -> bool:
    filename = raw_path.name
    today = date.today().isoformat()
    year = date.today().year

    # Check exact filename duplicate
    existing = _find_wiki_source_for(filename)
    if existing:
        logger.info("%s already ingested → %s", filename, existing[0])
        return False

    logger.info("Ingest avviato: %s", filename)

    # Step 1: OCR (parallel per pages if scanned PDF)
    loop = asyncio.get_event_loop()
    logger.info("OCR in corso: %s", filename)
    try:
        text = await loop.run_in_executor(None, ocr.extract_text, raw_path)
    except Exception as exc:
        logger.error("OCR fallito per %s: %s", filename, exc)
        return False

    if not text.strip():
        logger.warning("Nessun testo estratto da %s — ingest abortito", filename)
        return False
    logger.info("OCR completato: %s — %d chars", filename, len(text))

    # Step 2: Dedup check (content similarity via embeddings)
    if await _is_duplicate(text):
        logger.info("Documento già presente (contenuto duplicato) — skip: %s", filename)
        return False

    # Step 3: LLM summary
    logger.info("LLM summary: %s", filename)
    try:
        wiki_content = await _llm_summarize(text, filename, today, year)
    except Exception as exc:
        logger.error("LLM summary fallito per %s: %s", filename, exc)
        return False
    if not wiki_content:
        logger.error("LLM summary vuoto per %s", filename)
        return False

    # Step 4: Fix frontmatter
    try:
        post = frontmatter.loads(wiki_content)
        post.metadata["source_file"] = filename
        final_content = frontmatter.dumps(post)
    except Exception:
        final_content = (
            f"---\ntitle: \"{filename}\"\ntype: source\ntags: []\n"
            f"created: {today}\nupdated: {today}\nsource_file: \"{filename}\"\n---\n\n"
            + wiki_content
        )

    # Step 5: Write wiki/sources/
    sources_dir = settings.wiki_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    slug = _slug(filename)
    dest = sources_dir / f"{today}_{slug}.md"
    counter = 1
    while dest.exists():
        dest = sources_dir / f"{today}_{slug}-{counter}.md"
        counter += 1
    dest.write_text(final_content, encoding="utf-8")
    logger.info("Wiki page: %s", dest.name)

    _update_index(filename, dest)
    _append_log(today, filename, dest)
    search.rebuild_index()
    return True


def _update_index(raw_filename: str, wiki_page: Path) -> None:
    index_path = settings.wiki_dir / "index.md"
    entry = f"- [[{wiki_page.stem}]] — `raw/{raw_filename}`\n"
    if index_path.exists():
        content = index_path.read_text(encoding="utf-8")
        if wiki_page.stem in content:
            return
        if "## Sources" in content:
            content = content.replace("## Sources\n", f"## Sources\n{entry}")
        else:
            content += f"\n## Sources\n{entry}"
    else:
        content = f"# Wiki Index\n\n## Sources\n{entry}"
    index_path.write_text(content, encoding="utf-8")


def _append_log(today: str, raw_filename: str, wiki_page: Path) -> None:
    log_path = settings.wiki_dir / "log.md"
    entry = (
        f"\n## [{today}] INGEST | {raw_filename}\n"
        f"Auto-ingested via OCR pipeline. Source page: [[{wiki_page.stem}]].\n"
    )
    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8")
        log_path.write_text(existing + entry, encoding="utf-8")
    else:
        log_path.write_text(f"# Wiki Log\n{entry}", encoding="utf-8")


async def remove_file(raw_path: Path) -> dict:
    raw_filename = raw_path.name
    deleted_raw = False
    if raw_path.exists():
        raw_path.unlink()
        deleted_raw = True

    wiki_pages = _find_wiki_source_for(raw_filename)
    for page in wiki_pages:
        page.unlink()
        logger.info("Removed wiki page %s", page)

    if wiki_pages:
        _remove_from_index([p.stem for p in wiki_pages])

    today = date.today().isoformat()
    _append_removal_log(today, raw_filename, wiki_pages)
    search.rebuild_index()

    return {
        "deleted_raw": deleted_raw,
        "deleted_wiki_pages": [str(p) for p in wiki_pages],
    }


def _remove_from_index(stems: list[str]) -> None:
    index_path = settings.wiki_dir / "index.md"
    if not index_path.exists():
        return
    lines = index_path.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [l for l in lines if not any(stem in l for stem in stems)]
    index_path.write_text("".join(kept), encoding="utf-8")


def _append_removal_log(today: str, raw_filename: str, wiki_pages: list[Path]) -> None:
    log_path = settings.wiki_dir / "log.md"
    pages_str = ", ".join(f"[[{p.stem}]]" for p in wiki_pages) if wiki_pages else "none"
    entry = (
        f"\n## [{today}] REMOVE | {raw_filename}\n"
        f"File removed. Wiki pages deleted: {pages_str}.\n"
    )
    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8")
        log_path.write_text(existing + entry, encoding="utf-8")
    else:
        log_path.write_text(f"# Wiki Log\n{entry}", encoding="utf-8")
