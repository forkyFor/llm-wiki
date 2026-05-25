"""Watchdog file observer — monitors raw/ and triggers ingest pipeline."""
import asyncio
import logging
import threading
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileMovedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from backend.config import settings

logger = logging.getLogger(__name__)

_observer: Observer | None = None
_loop: asyncio.AbstractEventLoop | None = None

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp", ".txt", ".md", ".docx", ".doc"}

_DEBOUNCE_SECONDS = 2.0


class _RawFolderHandler(FileSystemEventHandler):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._pending: set[str] = set()
        self._lock = threading.Lock()

    def _enqueue(self, path: str) -> None:
        file_path = Path(path)
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return
        if file_path.name.startswith("."):
            return
        with self._lock:
            if file_path.name in self._pending:
                return  # duplicate event within debounce window — drop silently
            self._pending.add(file_path.name)
        logger.info("New file detected: %s", file_path.name)
        asyncio.run_coroutine_threadsafe(self._trigger(file_path), self._loop)

    async def _trigger(self, file_path: Path) -> None:
        await asyncio.sleep(_DEBOUNCE_SECONDS)
        with self._lock:
            self._pending.discard(file_path.name)
        from backend.services.ingest import ingest_file
        try:
            await ingest_file(file_path)
        except Exception as exc:
            logger.error("Ingest fallito per %s: %s", file_path.name, exc)

    def on_created(self, event: FileCreatedEvent) -> None:
        if not event.is_directory:
            self._enqueue(event.src_path)

    def on_modified(self, event: FileModifiedEvent) -> None:
        if not event.is_directory:
            self._enqueue(event.src_path)

    def on_moved(self, event: FileMovedEvent) -> None:
        if not event.is_directory:
            self._enqueue(event.dest_path)


def start(loop: asyncio.AbstractEventLoop) -> None:
    global _observer, _loop
    _loop = loop
    raw_dir = settings.raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    _observer = Observer()
    _observer.schedule(_RawFolderHandler(loop), str(raw_dir), recursive=False)
    _observer.start()
    logger.info("Watching %s for new files", raw_dir)


def stop() -> None:
    global _observer
    if _observer:
        _observer.stop()
        _observer.join()
        _observer = None
