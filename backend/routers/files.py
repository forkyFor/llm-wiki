"""File management endpoints — supports nested folders under raw/."""
import asyncio
import logging
import shutil
from pathlib import Path

import aiofiles
from fastapi import APIRouter, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.config import settings
from backend.services import ingest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])
folders_router = APIRouter(prefix="/api/folders", tags=["folders"])

ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp",
    ".txt", ".md", ".docx", ".doc",
}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

# Status keyed by relative path from raw_dir using forward slashes, e.g. "reports/q1.pdf"
_status: dict[str, str] = {}


# ── Path helpers ──────────────────────────────────────────────────────────────

def _safe_relpath(relpath: str) -> Path:
    """Resolve a user-supplied relative path inside raw_dir. Raises on traversal or hidden components."""
    clean = relpath.strip("/").replace("\\", "/")
    if not clean:
        raise HTTPException(400, "Invalid path")
    candidate = (settings.raw_dir / clean).resolve()
    raw_resolved = settings.raw_dir.resolve()
    try:
        rel = candidate.relative_to(raw_resolved)
    except ValueError:
        raise HTTPException(403, "Access denied")
    for part in rel.parts:
        if part.startswith("."):
            raise HTTPException(400, "Invalid path component")
    return candidate


def _relstr(path: Path) -> str:
    """Relative path string from raw_dir (forward slashes)."""
    return str(path.relative_to(settings.raw_dir.resolve())).replace("\\", "/")


def _file_status(relpath: str) -> str:
    return _status.get(relpath, "ready")


# ── Tree builder ──────────────────────────────────────────────────────────────

def _build_tree(directory: Path) -> list:
    """Recursively build a file/folder tree. Folders first, then files, both alphabetical."""
    raw_resolved = settings.raw_dir.resolve()
    directory = directory.resolve()
    try:
        entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return []
    items = []
    for p in entries:
        if p.name.startswith("."):
            continue
        rel = str(p.relative_to(raw_resolved)).replace("\\", "/")
        if p.is_dir():
            items.append({
                "type": "folder",
                "name": p.name,
                "path": rel,
                "children": _build_tree(p),
            })
        elif p.is_file():
            items.append({
                "type": "file",
                "name": p.name,
                "path": rel,
                "size": p.stat().st_size,
                "status": _file_status(rel),
            })
    return items


# ── Files router ──────────────────────────────────────────────────────────────

@router.get("")
async def list_files():
    """Return recursive file/folder tree rooted at raw/."""
    settings.raw_dir.mkdir(parents=True, exist_ok=True)
    return _build_tree(settings.raw_dir)


@router.post("")
async def upload_file(file: UploadFile, folder: str = Query(default="")):
    """Upload a file to raw/ (or a subfolder via ?folder=path) and trigger OCR ingest."""
    safe_name = Path(file.filename or "").name
    if not safe_name or safe_name.startswith("."):
        raise HTTPException(400, "Invalid filename")
    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type '{ext}' not supported")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File too large (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB)")

    target_dir = _safe_relpath(folder) if folder else settings.raw_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / safe_name

    async with aiofiles.open(dest, "wb") as out:
        await out.write(content)

    rel = _relstr(dest)
    _status[rel] = "pending"
    asyncio.create_task(_run_ingest(dest, rel))
    return {"name": safe_name, "path": rel, "status": "pending"}


async def _run_ingest(path: Path, relpath: str) -> None:
    _status[relpath] = "processing"
    try:
        ok = await ingest.ingest_file(path)
        _status[relpath] = "done" if ok else "error"
    except Exception as exc:
        logger.error("Ingest error for %s: %s", path.name, exc)
        _status[relpath] = "error"


@router.get("/{file_path:path}")
async def get_file(file_path: str):
    """Download/preview a file (path may contain subdirectory segments)."""
    path = _safe_relpath(file_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(str(path), filename=path.name)


@router.delete("/{file_path:path}")
async def delete_file(file_path: str):
    """Delete a file and cascade-remove its wiki pages."""
    path = _safe_relpath(file_path)
    if not path.exists():
        raise HTTPException(404, "File not found")
    if path.is_dir():
        raise HTTPException(400, "Use DELETE /api/folders/{path} to delete folders")
    rel = _relstr(path)
    result = await ingest.remove_file(path)
    _status.pop(rel, None)
    return result


# ── Folders router ────────────────────────────────────────────────────────────

class FolderCreate(BaseModel):
    path: str


@folders_router.post("")
async def create_folder(body: FolderCreate):
    """Create a folder (and intermediate parents) under raw/."""
    folder_path = body.path.strip().strip("/").replace("\\", "/")
    if not folder_path:
        raise HTTPException(400, "path required")
    for part in Path(folder_path).parts:
        if part.startswith(".") or part in ("..", "/", "\\"):
            raise HTTPException(400, f"Invalid folder name: {part!r}")
    target = _safe_relpath(folder_path)
    if target.exists():
        if target.is_dir():
            return {"path": folder_path, "created": False}
        raise HTTPException(400, "A file already exists at that path")
    target.mkdir(parents=True, exist_ok=True)
    return {"path": folder_path, "created": True}


@folders_router.delete("/{folder_path:path}")
async def delete_folder(folder_path: str):
    """Delete a folder with all its contents, cascading wiki page removal."""
    target = _safe_relpath(folder_path)
    if not target.exists():
        raise HTTPException(404, "Folder not found")
    if not target.is_dir():
        raise HTTPException(400, "Not a folder — use DELETE /api/files/{path}")

    deleted_wiki: list[str] = []
    for f in sorted(target.rglob("*")):
        if f.is_file() and not f.name.startswith("."):
            rel = _relstr(f)
            result = await ingest.remove_file(f)
            deleted_wiki.extend(result.get("deleted_wiki_pages", []))
            _status.pop(rel, None)

    shutil.rmtree(target)
    return {"deleted_folder": folder_path, "deleted_wiki_pages": deleted_wiki}
