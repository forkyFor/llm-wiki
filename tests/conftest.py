"""Shared fixtures for LLM Wiki test suite."""
import asyncio
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# ── Fake data ─────────────────────────────────────────────────────────────────

TODAY = date.today().isoformat()

FAKE_WIKI_PAGE = f"""---
title: "Test Document"
type: source
tags: []
created: {TODAY}
updated: {TODAY}
authors: []
year: 2026
source_file: "test.txt"
---

## Summary
This is a test document about Python programming and machine learning.

## Key claims
- Python is a programming language
- Machine learning uses data

## Key entities
[[Python]]

## Key concepts
[[Machine Learning]]

## Notable quotes
> Python is great

## Contradictions / tensions
None identified

## Source file
`raw/test.txt`
"""

FAKE_WIKI_PAGE_2 = f"""---
title: "Second Document"
type: source
tags: []
created: {TODAY}
updated: {TODAY}
source_file: "second.txt"
---

## Summary
This document is about databases and SQL queries for data storage.

## Source file
`raw/second.txt`
"""


async def fake_stream(messages, **kwargs):
    """Async generator that yields fake LLM tokens."""
    for token in ["This ", "is ", "a ", "test ", "answer."]:
        yield token


# ── Directory fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def tmp_dirs(tmp_path):
    """Create temp raw/ and wiki/ dirs with expected subdirs."""
    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    (wiki / "sources").mkdir()
    (wiki / "entities").mkdir()
    (wiki / "concepts").mkdir()
    return raw, wiki


# ── Module-state reset ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_module_globals():
    """Reset module-level globals between tests to avoid state leakage."""
    import backend.services.search as search_mod
    import backend.services.ingest as ingest_mod
    import backend.services.cache as cache_mod

    search_mod._index = None
    search_mod._docs = []
    ingest_mod._processing.clear()
    cache_mod.semantic_cache._entries.clear()

    yield

    search_mod._index = None
    search_mod._docs = []
    ingest_mod._processing.clear()
    cache_mod.semantic_cache._entries.clear()


# ── App client fixture ────────────────────────────────────────────────────────

@pytest.fixture
def app_client(tmp_dirs, monkeypatch):
    """
    FastAPI TestClient with:
    - settings pointing to tmp dirs
    - OCR mocked (no model needed)
    - LLM mocked (no Ollama needed)
    """
    raw, wiki = tmp_dirs

    import backend.config as cfg
    import backend.services.ocr as ocr_mod
    import backend.services.llm as llm_mod
    import backend.routers.files as files_mod

    monkeypatch.setattr(cfg.settings, "raw_dir", raw)
    monkeypatch.setattr(cfg.settings, "wiki_dir", wiki)

    # Reset file status map for each test
    files_mod._status.clear()

    monkeypatch.setattr(
        ocr_mod,
        "extract_text",
        lambda path: f"Sample extracted text about Python from {path.name}",
    )
    monkeypatch.setattr(llm_mod, "chat_once", AsyncMock(return_value=FAKE_WIKI_PAGE))
    monkeypatch.setattr(llm_mod, "chat_stream", fake_stream)

    from fastapi.testclient import TestClient
    from backend.main import app

    with TestClient(app, raise_server_exceptions=True) as client:
        yield client

    files_mod._status.clear()
