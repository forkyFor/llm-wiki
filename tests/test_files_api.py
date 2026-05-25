"""Integration tests for /api/files endpoints."""
import io
import time

import pytest


SAMPLE_CONTENT = b"Hello, this is a test file about Python programming."
FILENAME = "test_upload.txt"


# ── Helpers ───────────────────────────────────────────────────────────────────

def upload(client, content=SAMPLE_CONTENT, filename=FILENAME):
    return client.post(
        "/api/files",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_list_empty(app_client):
    r = app_client.get("/api/files")
    assert r.status_code == 200
    assert r.json() == []


def test_upload_returns_pending(app_client):
    r = upload(app_client)
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == FILENAME
    assert body["status"] == "pending"


def test_upload_file_exists_on_disk(app_client, tmp_dirs):
    raw, wiki = tmp_dirs
    upload(app_client)
    assert (raw / FILENAME).exists()


def test_list_after_upload(app_client):
    upload(app_client)
    r = app_client.get("/api/files")
    assert r.status_code == 200
    names = [f["name"] for f in r.json()]
    assert FILENAME in names


def test_list_includes_size(app_client):
    upload(app_client)
    r = app_client.get("/api/files")
    files = r.json()
    match = next(f for f in files if f["name"] == FILENAME)
    assert match["size"] == len(SAMPLE_CONTENT)


def test_download_file(app_client):
    upload(app_client)
    r = app_client.get(f"/api/files/{FILENAME}")
    assert r.status_code == 200
    assert r.content == SAMPLE_CONTENT


def test_download_missing_returns_404(app_client):
    r = app_client.get("/api/files/does_not_exist.txt")
    assert r.status_code == 404


def test_delete_returns_deleted_raw_true(app_client):
    upload(app_client)
    r = app_client.delete(f"/api/files/{FILENAME}")
    assert r.status_code == 200
    assert r.json()["deleted_raw"] is True


def test_delete_missing_returns_404(app_client):
    r = app_client.delete("/api/files/ghost_file.txt")
    assert r.status_code == 404


def test_delete_file_gone_from_list(app_client):
    upload(app_client)
    app_client.delete(f"/api/files/{FILENAME}")
    r = app_client.get("/api/files")
    names = [f["name"] for f in r.json()]
    assert FILENAME not in names
