"""Integration tests for /api/chat SSE endpoint."""
import io
import json
import time

import pytest

SAMPLE_CONTENT = b"Python is a great programming language for data science."


def parse_sse(text: str) -> list[dict]:
    """Parse SSE response text into list of event dicts."""
    events = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


def chat(client, message="What is Python?", history=None):
    return client.post(
        "/api/chat",
        json={"message": message, "history": history or []},
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_chat_returns_sse_content_type(app_client):
    r = chat(app_client)
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")


def test_chat_events_are_valid_json(app_client):
    r = chat(app_client)
    events = parse_sse(r.text)
    assert len(events) > 0, "No SSE events found"


def test_chat_final_event_has_done_true(app_client):
    r = chat(app_client)
    events = parse_sse(r.text)
    done_events = [e for e in events if e.get("done") is True]
    assert len(done_events) == 1


def test_chat_sources_in_final_event(app_client):
    r = chat(app_client)
    events = parse_sse(r.text)
    done_event = next(e for e in events if e.get("done") is True)
    assert "sources" in done_event
    assert isinstance(done_event["sources"], list)


def test_chat_token_events_have_token_key(app_client):
    r = chat(app_client)
    events = parse_sse(r.text)
    token_events = [e for e in events if "token" in e]
    assert len(token_events) > 0


def test_chat_with_wiki_context_returns_sources(app_client, tmp_dirs, monkeypatch):
    """After ingesting a file, chat should return sources."""
    import backend.services.search as search_mod
    raw, wiki = tmp_dirs
    from datetime import date
    today = date.today().isoformat()

    # Need 3+ docs for non-zero BM25 IDF scores
    (wiki / "sources" / f"{today}_python-doc.md").write_text(
        "---\ntitle: Python Doc\ntype: source\nsource_file: python.txt\n---\n\nPython is a programming language used for scripting.\n",
        encoding="utf-8",
    )
    (wiki / "sources" / f"{today}_sql-doc.md").write_text(
        "---\ntitle: SQL Doc\ntype: source\nsource_file: sql.txt\n---\n\nSQL databases store relational tabular data.\n",
        encoding="utf-8",
    )
    (wiki / "sources" / f"{today}_docker-doc.md").write_text(
        "---\ntitle: Docker Doc\ntype: source\nsource_file: docker.txt\n---\n\nDocker containers virtualization deployment.\n",
        encoding="utf-8",
    )

    search_mod.rebuild_index()

    r = chat(app_client, message="What is Python?")
    events = parse_sse(r.text)
    done_event = next(e for e in events if e.get("done") is True)
    assert "python.txt" in done_event["sources"]
