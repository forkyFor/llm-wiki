"""In-memory log capture → SSE stream for the frontend log panel."""
import asyncio
import collections
import json
import logging
import time
from typing import AsyncIterator

MAX_QUEUE = 200
REPLAY_LINES = 50

_replay: collections.deque[dict] = collections.deque(maxlen=REPLAY_LINES)
_clients: set[asyncio.Queue] = set()
_loop: asyncio.AbstractEventLoop | None = None


def _make_record(record: logging.LogRecord) -> dict:
    return {
        "ts": time.strftime("%H:%M:%S", time.localtime(record.created)),
        "level": record.levelname,
        "name": record.name,
        "msg": record.getMessage(),
    }


class _SSELogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        d = _make_record(record)
        _replay.append(d)
        if _loop is not None and _loop.is_running():
            _loop.call_soon_threadsafe(self._broadcast, d)

    def _broadcast(self, d: dict) -> None:
        for q in list(_clients):
            if q.qsize() >= MAX_QUEUE:
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(d)
            except Exception:  # nosec B110
                pass


def install(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop
    handler = _SSELogHandler()
    handler.setLevel(logging.DEBUG)
    logging.root.addHandler(handler)


async def log_stream() -> AsyncIterator[str]:
    q: asyncio.Queue = asyncio.Queue()
    _clients.add(q)
    try:
        for record in list(_replay):
            yield f"data: {json.dumps(record)}\n\n"
        while True:
            record = await q.get()
            yield f"data: {json.dumps(record)}\n\n"
    finally:
        _clients.discard(q)
