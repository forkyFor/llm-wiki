"""
End-to-end test: upload file → wait for ingest → chat → verify sources cited.

Uses TestClient with background task polling.
The ingest mock (chat_once + extract_text) runs synchronously-fast,
so the background task completes within a few event-loop ticks.
"""
import io
import json
import time

import pytest


FILENAME = "e2e_document.txt"
CONTENT = b"Python is a powerful programming language used in data science."


def parse_sse_sources(text: str) -> list[str]:
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("data: "):
            try:
                evt = json.loads(line[6:])
                if evt.get("done"):
                    return evt.get("sources", [])
            except json.JSONDecodeError:
                pass
    return []


def test_upload_ingest_chat_pipeline(app_client, tmp_dirs):
    raw, wiki = tmp_dirs
    from datetime import date
    import backend.services.search as search_mod

    today = date.today().isoformat()

    # Pre-populate 2 unrelated wiki pages so BM25 IDF is non-zero after ingest adds a third
    (wiki / "sources" / f"{today}_sql-doc.md").write_text(
        "---\ntitle: SQL\ntype: source\nsource_file: sql.txt\n---\n\nSQL databases store relational data.\n",
        encoding="utf-8",
    )
    (wiki / "sources" / f"{today}_docker-doc.md").write_text(
        "---\ntitle: Docker\ntype: source\nsource_file: docker.txt\n---\n\nDocker containers virtualization deployment cloud.\n",
        encoding="utf-8",
    )

    # Step 1: Upload file
    r = app_client.post(
        "/api/files",
        files={"file": (FILENAME, io.BytesIO(CONTENT), "text/plain")},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "pending"

    # Step 2: Poll until ingest completes (mocked, should be fast)
    done = False
    match = None
    for _ in range(30):
        time.sleep(0.3)
        r = app_client.get("/api/files")
        files = r.json()
        match = next((f for f in files if f["name"] == FILENAME), None)
        if match and match["status"] in ("done", "error"):
            done = True
            break

    assert done, "Ingest did not complete within timeout"
    assert match["status"] == "done", f"Ingest ended with status: {match['status']}"

    # Rebuild search index to include the newly ingested page
    search_mod.rebuild_index()

    # Step 3: Chat and verify sources
    r = app_client.post(
        "/api/chat",
        json={"message": "What is Python programming?", "history": []},
    )
    assert r.status_code == 200

    sources = parse_sse_sources(r.text)
    assert FILENAME in sources, f"Expected {FILENAME} in sources, got: {sources}"
