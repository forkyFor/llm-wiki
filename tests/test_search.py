"""Unit tests for BM25 search service."""
import pytest
from pathlib import Path

import backend.services.search as search_mod
import backend.config as cfg


def make_md(directory: Path, stem: str, content: str, source_file: str = "") -> Path:
    """Helper: write a markdown file with frontmatter."""
    path = directory / f"{stem}.md"
    path.write_text(
        f"---\ntitle: \"{stem}\"\ntype: source\nsource_file: \"{source_file}\"\n---\n\n{content}",
        encoding="utf-8",
    )
    return path


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_empty_wiki_returns_empty_index(tmp_dirs, monkeypatch):
    raw, wiki = tmp_dirs
    monkeypatch.setattr(cfg.settings, "wiki_dir", wiki)

    search_mod.rebuild_index()

    assert search_mod._index is None
    assert search_mod._docs == []


def test_rebuild_with_markdown_files(tmp_dirs, monkeypatch):
    raw, wiki = tmp_dirs
    monkeypatch.setattr(cfg.settings, "wiki_dir", wiki)

    make_md(wiki / "sources", "doc1", "Python programming language tutorial", "file1.txt")
    make_md(wiki / "sources", "doc2", "Database SQL queries data storage", "file2.txt")

    search_mod.rebuild_index()

    assert search_mod._index is not None
    assert len(search_mod._docs) == 2


def test_search_finds_relevant_document(tmp_dirs, monkeypatch):
    raw, wiki = tmp_dirs
    monkeypatch.setattr(cfg.settings, "wiki_dir", wiki)

    # Need 3+ docs so BM25 IDF is non-zero for terms appearing in 1 doc
    make_md(wiki / "sources", "python-doc", "Python is a great programming language for ML", "python.txt")
    make_md(wiki / "sources", "sql-doc", "SQL databases store relational data", "db.txt")
    make_md(wiki / "sources", "docker-doc", "Docker containers virtualization deployment", "docker.txt")

    search_mod.rebuild_index()
    results = search_mod.search("Python programming")

    assert len(results) > 0
    assert results[0].score > 0
    top = results[0].wiki_path.stem
    assert "python" in top


def test_search_returns_source_file(tmp_dirs, monkeypatch):
    raw, wiki = tmp_dirs
    monkeypatch.setattr(cfg.settings, "wiki_dir", wiki)

    # Need 3+ docs for non-zero BM25 IDF
    make_md(wiki / "sources", "my-doc", "content about Python programming", "myfile.pdf")
    make_md(wiki / "sources", "other1", "SQL databases store relational data", "other1.txt")
    make_md(wiki / "sources", "other2", "Docker containers virtualization", "other2.txt")

    search_mod.rebuild_index()
    results = search_mod.search("Python")

    assert len(results) > 0
    assert results[0].source_file == "myfile.pdf"


def test_search_top_k_limit(tmp_dirs, monkeypatch):
    raw, wiki = tmp_dirs
    monkeypatch.setattr(cfg.settings, "wiki_dir", wiki)

    for i in range(10):
        make_md(wiki / "sources", f"doc-{i}", f"Python tutorial number {i} for learning", f"f{i}.txt")

    search_mod.rebuild_index()
    results = search_mod.search("Python tutorial", top_k=3)

    assert len(results) <= 3


def test_search_filters_zero_scores(tmp_dirs, monkeypatch):
    raw, wiki = tmp_dirs
    monkeypatch.setattr(cfg.settings, "wiki_dir", wiki)

    make_md(wiki / "sources", "doc1", "Python programming language", "f.txt")

    search_mod.rebuild_index()
    results = search_mod.search("xyzzy irrelevant nonsense qwerty")

    for r in results:
        assert r.score > 0


def test_search_auto_rebuild_on_first_call(tmp_dirs, monkeypatch):
    raw, wiki = tmp_dirs
    monkeypatch.setattr(cfg.settings, "wiki_dir", wiki)

    # Need 3+ docs for non-zero BM25 IDF
    make_md(wiki / "sources", "auto-doc", "Python auto rebuild test programming", "auto.txt")
    make_md(wiki / "sources", "other1", "SQL databases store relational data", "other1.txt")
    make_md(wiki / "sources", "other2", "Docker containers virtualization deployment", "other2.txt")

    # Don't call rebuild_index manually — search() should auto-rebuild
    assert search_mod._index is None
    results = search_mod.search("Python")

    assert search_mod._index is not None
    assert len(results) > 0


def test_search_passage_truncated_to_800(tmp_dirs, monkeypatch):
    raw, wiki = tmp_dirs
    monkeypatch.setattr(cfg.settings, "wiki_dir", wiki)

    long_content = "Python " * 500  # ~3500 chars
    make_md(wiki / "sources", "long-doc", long_content, "long.txt")

    search_mod.rebuild_index()
    results = search_mod.search("Python")

    if results:
        assert len(results[0].passage) <= 800
