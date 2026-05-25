"""Unit tests for ingest pipeline and delete cascade."""
import asyncio
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import frontmatter
import pytest

import backend.config as cfg
import backend.services.ingest as ingest_mod
import backend.services.search as search_mod

TODAY = date.today().isoformat()

FAKE_WIKI = f"""---
title: "Test Doc"
type: source
tags: []
created: {TODAY}
updated: {TODAY}
source_file: "PLACEHOLDER"
---

## Summary
Content about Python programming.
"""


def make_fake_llm(source_file: str):
    return AsyncMock(return_value=FAKE_WIKI.replace("PLACEHOLDER", source_file))


def fake_ocr(path):
    return f"Text from {path.name}"


def patch_deps(monkeypatch, raw, wiki, source_file="test.txt"):
    monkeypatch.setattr(cfg.settings, "raw_dir", raw)
    monkeypatch.setattr(cfg.settings, "wiki_dir", wiki)
    monkeypatch.setattr("backend.services.ocr.extract_text", fake_ocr)
    monkeypatch.setattr("backend.services.llm.chat_once", make_fake_llm(source_file))
    monkeypatch.setattr("backend.services.search.rebuild_index", lambda: None)


# ── Ingest tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_txt_creates_wiki_page(tmp_dirs, monkeypatch):
    raw, wiki = tmp_dirs
    patch_deps(monkeypatch, raw, wiki, "test.txt")

    raw_file = raw / "test.txt"
    raw_file.write_text("Hello world", encoding="utf-8")

    result = await ingest_mod.ingest_file(raw_file)

    assert result is True
    sources = list((wiki / "sources").glob("*.md"))
    assert len(sources) == 1


@pytest.mark.asyncio
async def test_ingest_frontmatter_has_source_file(tmp_dirs, monkeypatch):
    raw, wiki = tmp_dirs
    patch_deps(monkeypatch, raw, wiki, "test.txt")

    raw_file = raw / "test.txt"
    raw_file.write_text("Content", encoding="utf-8")

    await ingest_mod.ingest_file(raw_file)

    sources = list((wiki / "sources").glob("*.md"))
    post = frontmatter.load(str(sources[0]))
    assert post.metadata.get("source_file") == "test.txt"


@pytest.mark.asyncio
async def test_ingest_updates_index(tmp_dirs, monkeypatch):
    raw, wiki = tmp_dirs
    patch_deps(monkeypatch, raw, wiki, "test.txt")

    raw_file = raw / "test.txt"
    raw_file.write_text("Content", encoding="utf-8")

    await ingest_mod.ingest_file(raw_file)

    index = (wiki / "index.md").read_text(encoding="utf-8")
    assert "Sources" in index
    assert "test" in index.lower()


@pytest.mark.asyncio
async def test_ingest_appends_log(tmp_dirs, monkeypatch):
    raw, wiki = tmp_dirs
    patch_deps(monkeypatch, raw, wiki, "test.txt")

    raw_file = raw / "test.txt"
    raw_file.write_text("Content", encoding="utf-8")

    await ingest_mod.ingest_file(raw_file)

    log = (wiki / "log.md").read_text(encoding="utf-8")
    assert "INGEST" in log
    assert "test.txt" in log


@pytest.mark.asyncio
async def test_ingest_duplicate_skipped(tmp_dirs, monkeypatch):
    raw, wiki = tmp_dirs
    patch_deps(monkeypatch, raw, wiki, "test.txt")

    raw_file = raw / "test.txt"
    raw_file.write_text("Content", encoding="utf-8")

    first = await ingest_mod.ingest_file(raw_file)
    second = await ingest_mod.ingest_file(raw_file)

    assert first is True
    assert second is False
    assert len(list((wiki / "sources").glob("*.md"))) == 1


def test_ingest_slug_special_chars():
    slug = ingest_mod._slug("My Doc (v2).pdf")
    assert slug == "my-doc-v2"
    assert " " not in slug
    assert "(" not in slug
    assert ")" not in slug


def test_ingest_slug_truncates_long_name():
    long_name = "a" * 100 + ".txt"
    slug = ingest_mod._slug(long_name)
    assert len(slug) <= 60


@pytest.mark.asyncio
async def test_ingest_slug_collision(tmp_dirs, monkeypatch):
    raw, wiki = tmp_dirs

    # File 1: "test.txt"
    patch_deps(monkeypatch, raw, wiki, "test.txt")
    f1 = raw / "test.txt"
    f1.write_text("Content 1", encoding="utf-8")
    await ingest_mod.ingest_file(f1)

    # File 2: another file that produces same slug
    patch_deps(monkeypatch, raw, wiki, "test.md")
    monkeypatch.setattr("backend.services.llm.chat_once", make_fake_llm("test.md"))
    f2 = raw / "test.md"
    f2.write_text("Content 2", encoding="utf-8")
    await ingest_mod.ingest_file(f2)

    sources = list((wiki / "sources").glob("*.md"))
    assert len(sources) == 2


# ── Remove / cascade tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_remove_deletes_raw_file(tmp_dirs, monkeypatch):
    raw, wiki = tmp_dirs
    patch_deps(monkeypatch, raw, wiki, "test.txt")

    raw_file = raw / "test.txt"
    raw_file.write_text("Content", encoding="utf-8")
    await ingest_mod.ingest_file(raw_file)

    result = await ingest_mod.remove_file(raw_file)

    assert result["deleted_raw"] is True
    assert not raw_file.exists()


@pytest.mark.asyncio
async def test_remove_cascades_wiki_page(tmp_dirs, monkeypatch):
    raw, wiki = tmp_dirs
    patch_deps(monkeypatch, raw, wiki, "test.txt")

    raw_file = raw / "test.txt"
    raw_file.write_text("Content", encoding="utf-8")
    await ingest_mod.ingest_file(raw_file)

    sources_before = list((wiki / "sources").glob("*.md"))
    assert len(sources_before) == 1

    await ingest_mod.remove_file(raw_file)

    sources_after = list((wiki / "sources").glob("*.md"))
    assert len(sources_after) == 0


@pytest.mark.asyncio
async def test_remove_updates_index_and_log(tmp_dirs, monkeypatch):
    raw, wiki = tmp_dirs
    patch_deps(monkeypatch, raw, wiki, "test.txt")

    raw_file = raw / "test.txt"
    raw_file.write_text("Content", encoding="utf-8")
    await ingest_mod.ingest_file(raw_file)

    # Verify index has entry before removal
    index_before = (wiki / "index.md").read_text(encoding="utf-8")
    assert "test" in index_before.lower()

    await ingest_mod.remove_file(raw_file)

    log = (wiki / "log.md").read_text(encoding="utf-8")
    assert "REMOVE" in log
    assert "test.txt" in log
